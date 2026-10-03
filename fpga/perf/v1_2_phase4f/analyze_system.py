"""Independently audit the complete Phase 4F eight-frame system run.

This is an evidence reader, not a simulator or optimizer.  A performance FAIL
still produces the complete report and never changes RTL or invokes tools.
"""
import argparse
import csv
import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path


FRAMES = 8
BUDGET = 3333333
CLOCK_HZ = 100000000
STAGE_NAMES = {0: "CNN", 1: "Bilinear", 2: "Curve"}
SCALARS = {0: 19080, 1: 2747520, 2: 2747520}
CONFIG = dict(FRAMES=8, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2,
              DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128)
REFERENCE = {0: 3301639, 1: 3100554, 2: 2919395}
BUFFER_NAMES = {0: "A_low", 1: "A_full", 2: "enhanced", 3: "cnn_input", 4: "model_input"}


class EvidenceError(ValueError):
    """Incomplete or inconsistent run evidence must never become a PASS."""


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def records(text, prefix):
    return [dict((k, int(v)) for k, v in re.findall(r"(\w+)=(-?\d+)", line))
            for line in text.splitlines() if line.startswith(prefix + " ")]


def one_record(text, prefix):
    rows = records(text, prefix)
    require(len(rows) == 1, f"Expected one {prefix} record, observed {len(rows)}")
    return rows[0]


def describe(values):
    values = list(values)
    if not values:
        return dict(samples=0, min=None, mean=None, max=None, sum=0)
    return dict(samples=len(values), min=min(values), mean=statistics.mean(values),
                max=max(values), sum=sum(values))


def audit_configuration(run, manifest, text):
    config = manifest.get("config")
    require(config is not None, "run_manifest.json has no runtime config")
    require(all(config.get(k) == v for k, v in CONFIG.items()),
            f"Runtime config must be exactly {CONFIG}; observed {config}")
    require(config.get("CLOCK_MHZ") == 100, "Manifest does not prove CLOCK_MHZ=100")
    require(set(config) == set(CONFIG) | {"CLOCK_MHZ"}, "Unexpected runtime configuration key")
    for key in ("clock_hz", "frequency_hz"):
        if key in manifest:
            require(manifest[key] == CLOCK_HZ, f"Manifest {key} is not 100 MHz")
    tb = (run / "system_tb.sv").read_text()
    require(re.search(r"always\s+#5\s+ap_clk\s*=\s*~ap_clk\s*;", tb) is not None,
            "Generated TB has no 100 MHz (#5 ns half-period) clock evidence")
    require("`timescale 1ns/1ps" in tb, "Generated TB timescale is not 1 ns")
    launches = [line for line in text.splitlines()
                if line.startswith("# xsim ") and "-testplusarg " in line]
    require(len(launches) == 1, "Expected one recorded xsim launch")
    for key, value in CONFIG.items():
        require(re.findall(r"-testplusarg " + key + r"=(\d+)(?:\s|$)", launches[0]) == [str(value)],
                f"xsim command does not prove {key}={value}")
    runtime = one_record(text, "DDR_V2")
    require(runtime == dict(READ_OUTSTANDING=2, WRITE_OUTSTANDING=2),
            "DDR runtime outstanding limits differ from O=2")
    shared = one_record(text, "DDR_SHARED")
    require(shared["PERIOD"] == 1 and shared["DELAY"] == 16,
            "DDR runtime service period or delay differs from fixed config")
    return dict(config=CONFIG, clock_hz=CLOCK_HZ, clock_evidence="system_tb.sv: #5 ns half-period",
                runtime=runtime, shared=shared)


def audit_frozen_evidence(run, manifest, termination):
    frozen = manifest["original_source_manifest"]
    for item in frozen["source_files"]:
        require(sha(Path(item["path"])) == item["sha256"], f"Frozen source changed: {item['path']}")
    require(len(manifest["substitutions"]) == 3, "Expected the three Phase 4E scheduling overlay files")
    for item in manifest["substitutions"]:
        require(sha(Path(item["candidate"])) == item["candidate_sha256"],
                f"Phase 4E candidate changed: {item['candidate']}")
    for name, digest in manifest["protected_copies"].items():
        require(sha(run / name) == digest, f"Protected input/model/DDR/wrapper copy changed: {name}")
    require(sha(run / "system_tb.sv") == manifest["generated_tb_sha256"], "Generated TB changed after prepare")
    require(termination.get("status") == "TERMINAL", "Simulation status is not naturally terminal")
    require(sha(run / "xsim.dir/phase4f_system/xsimk.exe") == termination["kernel_sha256"],
            "Simulation kernel does not match the executed kernel hash")
    require(termination.get("config") == manifest["config"], "Terminal record config differs from manifest")
    return dict(original_sources=len(frozen["source_files"]), overlay_substitutions=3,
                protected_copies=len(manifest["protected_copies"]), generated_tb="PASS", executed_kernel="PASS")


def audit_stages(run, text):
    rows = records(text, "STAGE_FRAME")
    require(len(rows) == 24, f"Expected 24 complete numerical stage records, observed {len(rows)}")
    stages = {}
    for row in rows:
        key = row["STAGE"], row["FRAME"]
        require(key not in stages, f"Duplicate stage record {key}")
        stages[key] = dict(stage=key[0], name=STAGE_NAMES.get(key[0], "UNKNOWN"), frame=key[1],
                           start=row["START"], done=row["DONE"], cycles=row["CYCLES"],
                           scalars=row["SCALARS"], mismatches=row["MISMATCHES"])
    require(set(stages) == {(t, f) for t in range(3) for f in range(8)},
            "Stage records do not cover all three stages and all eight frames")
    rows = read_csv(run / "results/stage_events.csv")
    events = {}
    for row in rows:
        key = row["event"], int(row["stage"]), int(row["frame"])
        require(key not in events, f"Duplicate stage event {key}")
        events[key] = int(row["cycle"])
    expected = {(kind, t, f) for kind in ("START", "DONE") for t in range(3) for f in range(8)}
    expected |= {("HOST_RELEASE", 2, f) for f in range(8)}
    require(set(events) == expected, "Stage events are incomplete or include an unexpected event")
    for (t, f), stage in stages.items():
        require(stage["cycles"] == stage["done"] - stage["start"] > 0,
                f"Stage {t} frame {f} has inconsistent true RTL duration")
        require(stage["scalars"] == SCALARS[t] and stage["mismatches"] == 0,
                f"Stage {t} frame {f} lacks the full zero-mismatch numerical check")
        for kind, field in (("START", "start"), ("DONE", "done")):
            require(events[kind, t, f] == stage[field], f"CSV/log timing mismatch {kind} {t} {f}")
        if t:
            require(stage["start"] >= events["DONE", t-1, f], f"RAW dependency violation {t} {f}")
        if f:
            require(stage["start"] >= events["DONE", t, f-1], f"Stage instance overlap {t} {f}")
        if f >= 2:
            release = ("DONE", 1, f-2) if t == 0 else (("DONE", 2, f-2) if t == 1 else ("HOST_RELEASE", 2, f-2))
            require(stage["start"] >= events[release], f"Ping-pong slot reuse before consumer completes {t} {f}")
    for f in range(8):
        require(events["HOST_RELEASE", 2, f] >= events["DONE", 2, f],
                f"Enhanced host release precedes Curve completion frame {f}")
    final = one_record(text, "SYSTEM_FINAL")
    require(final["FRAMES"] == final["CHECKED"] == 8, "Run did not complete and check all eight frames")
    require(final["RAW_MISMATCHES"] == final["GUARD_ERRORS"] == final["HAZARD_ERRORS"] == 0,
            "Final raw, guard, or hazard count is nonzero")
    require("FULL_THREE_MODULE_NUMERICAL_PASS" in text, "Full three-module numerical completion marker is absent")
    return stages, events, final


def timing_metrics(stages, events):
    intervals = [dict(from_frame=f-1, to_frame=f,
                      cycles=events["DONE", 2, f] - events["DONE", 2, f-1]) for f in range(1, 8)]
    steady = [row for row in intervals if row["to_frame"] >= 4]
    stage_metrics = {}
    for t in range(3):
        starts = [dict(from_frame=f-1, to_frame=f,
                       cycles=events["START", t, f] - events["START", t, f-1]) for f in range(1, 8)]
        stage_metrics[STAGE_NAMES[t]] = dict(
            start_intervals=starts, all_start_interval=describe(row["cycles"] for row in starts),
            late_start_interval=describe(row["cycles"] for row in starts if row["to_frame"] >= 4),
            latency=describe(stages[t, f]["cycles"] for f in range(8)),
            late_latency=describe(stages[t, f]["cycles"] for f in range(4, 8)),
            isolated_reference_cycles=REFERENCE[t],
            per_frame_latency=[dict(frame=f, cycles=stages[t, f]["cycles"],
                                    over_budget=stages[t, f]["cycles"] > BUDGET,
                                    above_isolated_reference=stages[t, f]["cycles"] - REFERENCE[t]) for f in range(8)])
    triplets = []
    for f in range(6):
        start = max(events["START", 0, f+2], events["START", 1, f+1], events["START", 2, f])
        done = min(events["DONE", 0, f+2], events["DONE", 1, f+1], events["DONE", 2, f])
        triplets.append(dict(cnn_frame=f+2, bilinear_frame=f+1, curve_frame=f,
                             overlap_start=start, overlap_done=done,
                             overlap_cycles=max(0, done-start), actual_overlap=done > start))
    boundaries = defaultdict(list)
    for (t, f), stage in stages.items():
        boundaries[stage["start"]].append((True, t, f))
        boundaries[stage["done"]].append((False, t, f))
    active = set()
    timeline = []
    previous = None
    peak = 0
    for cycle, changes in sorted(boundaries.items()):
        if previous is not None and cycle > previous:
            timeline.append(dict(start=previous, done=cycle, cycles=cycle-previous,
                                 active=[dict(stage=t, name=STAGE_NAMES[t], frame=f) for t, f in sorted(active)],
                                 mask=sum(1 << t for t, f in active)))
        for entering, t, f in sorted(changes):
            if entering:
                require((t, f) not in active, "Duplicate stage activation in sweep")
                active.add((t, f))
            else:
                require((t, f) in active, "Missing stage activation in sweep")
                active.remove((t, f))
        peak = max(peak, len(active))
        previous = cycle
    require(not active, "Stage sweep has outstanding active stages")
    overlap = peak == 3 and any(row["actual_overlap"] for row in triplets)
    late = describe(row["cycles"] for row in steady)
    return dict(first_frame_latency_cycles=events["DONE", 2, 0] - events["START", 0, 0],
                first_frame_scope="Latency only; never used to judge FPS",
                curve_done_intervals=intervals, all_curve_intervals=describe(row["cycles"] for row in intervals),
                steady_curve_intervals=late, steady_scope="Curve output intervals ending at frames 4, 5, 6, 7",
                max_steady_interval_budget_cycles=BUDGET,
                fps_from_mean_steady_interval=CLOCK_HZ / late["mean"],
                fps_from_max_steady_interval=CLOCK_HZ / late["max"],
                interval_gate="PASS" if late["max"] <= BUDGET else "FAIL",
                stage_metrics=stage_metrics, triplet_overlap=triplets,
                stage_overlap_timeline=timeline, peak_concurrent_stages=peak,
                pipeline_overlap_gate="PASS" if overlap else "FAIL")


def audit_ddr(text, runtime):
    hp = {row["HP"]: row for row in records(text, "HP_STATS")}
    queues = {row["HP"]: row for row in records(text, "HP_QUEUE")}
    require(set(hp) == set(queues) == set(range(4)), "Missing HP0..HP3 statistics or queues")
    require(len(records(text, "HP_STATS")) == len(records(text, "HP_QUEUE")) == 4,
            "Duplicate DDR HP statistics")
    shared = runtime["shared"]
    require(sum(row["R"] + row["W"] for row in hp.values()) == shared["SERVED"],
            "Shared DDR served beats do not conserve R/W traffic")
    for port in range(4):
        stats, queue = hp[port], queues[port]
        require(all(v >= 0 for v in stats.values()) and all(v >= 0 for v in queue.values()),
                f"HP{port} contains a negative DDR counter")
        require(stats["AR"] == stats["FIRST_R_SAMPLES"] and stats["AW"] == stats["B_SAMPLES"],
                f"HP{port} responses are not fully sampled/drained")
        require(0 <= queue["READ_MAX"] <= 2 and 0 <= queue["WRITE_MAX"] <= 2,
                f"HP{port} occupancy exceeds O=2")
        require(queue["WRITE_OCCUPANCY_SUM"] == stats["B_LATENCY_SUM"],
                f"HP{port} AW-to-B occupancy integral does not equal drained response latency")
        stats["average_ar_to_first_r_cycles"] = stats["FIRST_R_SUM"] / stats["AR"] if stats["AR"] else None
        stats["average_ar_to_last_r_cycles"] = queue["READ_OCCUPANCY_SUM"] / stats["AR"] if stats["AR"] else None
        stats["average_aw_to_b_cycles"] = stats["B_LATENCY_SUM"] / stats["AW"] if stats["AW"] else None
    require(hp[1]["AW"] == hp[1]["W"] == 0, "Immutable CNN constants HP1 received writes")
    rw = re.findall(r"^DDR_V2_RW_CONCURRENT_CYCLES=(\d+)\s*$", text, re.M)
    require(len(rw) == 1, "Missing DDR read/write concurrent-cycle statistic")
    return dict(hp_stats=[hp[p] for p in range(4)], queues=[queues[p] for p in range(4)],
                shared=shared, rw_concurrent_cycles=int(rw[0]),
                response_drain_gate="PASS", note="Original DDR model counters; latencies are request-to-response, not additive stalls")


def audit_ownership(run, stages, events):
    transitions = [{k: int(v) for k, v in row.items()} for row in read_csv(run / "results/ownership_events.csv")]
    require(len(transitions) == 80, f"Expected 80 acquire/release transitions, observed {len(transitions)}")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(transitions, transitions[1:])),
            "Ownership transition file is not chronological")
    state = {(b, s): -1 for b in range(5) for s in range(2)}
    pending = {}
    lifetimes = {}
    for row in transitions:
        b, slot, previous, owner, cycle = (row[k] for k in ("buffer", "slot", "previous", "owner", "cycle"))
        require((b, slot) in state, f"Unknown ownership buffer/slot {b}/{slot}")
        require(state[b, slot] == previous, f"Owner transition previous value mismatch buffer {b} slot {slot}")
        require((previous == -1) != (owner == -1), f"Owner overwrite without explicit release buffer {b} slot {slot}")
        frame = owner if owner >= 0 else previous
        require(0 <= frame < 8 and frame % 2 == slot, f"Owner frame has wrong ping-pong slot buffer {b}")
        key = b, frame
        if owner >= 0:
            require(key not in pending and key not in lifetimes, f"Duplicate buffer acquisition {key}")
            pending[key] = cycle
        else:
            require(key in pending, f"Release has no acquisition {key}")
            acquire = pending.pop(key)
            require(cycle > acquire, f"Nonpositive owner lifetime {key}")
            lifetimes[key] = dict(buffer=b, name=BUFFER_NAMES[b], slot=slot, frame=frame,
                                  acquire=acquire, release=cycle, occupied_cycles=cycle-acquire)
        state[b, slot] = owner
    require(not pending and all(owner == -1 for owner in state.values()), "Run retains a buffer owner")
    require(set(lifetimes) == {(b, f) for b in range(5) for f in range(8)},
            "Ownership lifetimes do not cover every buffer and frame")
    producer = {0: 0, 1: 1, 2: 2, 3: 0, 4: 2}
    consumer = {0: 1, 1: 2, 2: 2, 3: 0, 4: 2}
    for (b, f), lifetime in lifetimes.items():
        p, c = producer[b], consumer[b]
        require(lifetime["acquire"] <= stages[p, f]["start"], f"Acquire follows producer start {b} {f}")
        require(lifetime["release"] >= stages[c, f]["done"], f"Release precedes consumer completion {b} {f}")
        require(lifetime["acquire"] <= stages[c, f]["start"] < stages[c, f]["done"] <= lifetime["release"],
                f"Consumer not wholly inside owner lifetime {b} {f}")
        if b in (1, 2, 4):
            require(abs(lifetime["release"] - events["HOST_RELEASE", 2, f]) <= 1,
                    f"Curve buffer release does not coincide with host release {b} {f}")
        if f >= 2:
            require(lifetime["acquire"] >= lifetimes[b, f-2]["release"], f"WAR/WAW slot reuse before release {b} {f}")
    occ_rows = [{k: int(v) for k, v in row.items()} for row in read_csv(run / "results/slot_occupancy.csv")]
    require(len(occ_rows) == 10 and {(r["buffer"], r["slot"]) for r in occ_rows} == set(state),
            "Missing or duplicate per-slot occupancy records")
    for row in occ_rows:
        b, slot = row["buffer"], row["slot"]
        integral = sum(lifetimes[b, f]["occupied_cycles"] for f in range(slot, 8, 2))
        require(integral == row["occupied_cycles"], f"Measured occupied-cycle integral differs from transitions {b}/{slot}")
        changes = [(r["acquire"], 1) for (bb, f), r in lifetimes.items() if bb == b]
        changes += [(r["release"], -1) for (bb, f), r in lifetimes.items() if bb == b]
        occupancy = peak = 0
        for cycle, delta in sorted(changes):
            occupancy += delta
            require(0 <= occupancy <= 2, f"Invalid simultaneous slot occupancy {b}")
            peak = max(peak, occupancy)
        require(occupancy == 0 and row["peak_slots"] == peak, f"Peak occupancy does not match transitions {b}")
        row["name"] = BUFFER_NAMES[b]
    waits = [{k: int(v) for k, v in row.items()} for row in read_csv(run / "results/wait_stats.csv")]
    require(len(waits) == 24 and {(r["stage"], r["frame"]) for r in waits} == set(stages),
            "Missing or duplicate 24 stage/frame wait records")
    for row in waits:
        require(all(row[k] >= 0 for k in ("dependency", "buffer", "both", "ready")), "Negative wait statistic")
        require(row["both"] <= min(row["dependency"], row["buffer"]), "Overlapping wait count exceeds component")
        require(row["stage"] != 0 or row["dependency"] == row["both"] == 0,
                "CNN unexpectedly has a producer dependency")
        row["union_blocked"] = row["dependency"] + row["buffer"] - row["both"]
        row["observed_idle_cycles"] = row["union_blocked"] + row["ready"]
    by_stage = {}
    for t in range(3):
        selected = [r for r in waits if r["stage"] == t]
        by_stage[STAGE_NAMES[t]] = {key: sum(r[key] for r in selected)
                                   for key in ("dependency", "buffer", "both", "ready", "union_blocked", "observed_idle_cycles")}
    return dict(gate="PASS", raw_war_waw_gate="PASS", final_owners_free=True,
                lifetime_boundary_scope="Owners sampled at negedge, up to one cycle after original stage/host events",
                lifetimes=[lifetimes[k] for k in sorted(lifetimes)], slot_occupancy=occ_rows,
                waits=dict(per_frame=waits, by_stage=by_stage,
                           dependency_wait_cycles=sum(r["dependency"] for r in waits),
                           buffer_wait_cycles=sum(r["buffer"] for r in waits),
                           overlapping_wait_cycles=sum(r["both"] for r in waits),
                           union_blocked_cycles=sum(r["union_blocked"] for r in waits),
                           scope="Idle stage with a pending next frame only; dep/buffer overlap must not be added twice; ready includes CSR/poll scheduling",
                           causal_scope="These are measured state waits, not an additive attribution of output latency"),
                immutable_constants="HP1 AW/W=0; all model/input copies hash verified",
                workspace="One serialized CNN instance; exclusive HP0 stage-drain checks at every frame completion")


def scheduling_readiness_metrics(stages, ownership, timing):
    """Separate observed prerequisites from post-ready control launch delay.

    The max boundary is a measured availability boundary, not a sum of waits
    and not a counterfactual diagnosis.  Producer and instance boundaries are
    true RTL DONE; slot boundaries use actual observer ownership RELEASE.
    """
    lifetimes = {(r["buffer"], r["frame"]): r for r in ownership["lifetimes"]}
    acquired_buffers = {0: (0, 3), 1: (1,), 2: (2, 4)}
    output_intervals = {row["to_frame"]: row["cycles"] for row in timing["curve_done_intervals"]}
    alignment = []
    for t in range(3):
        launches = []
        for f in range(8):
            stage = stages[t, f]
            boundaries = []
            prior_done = None
            if f:
                prior_done = stages[t, f-1]["done"]
                boundaries.append(dict(kind="previous_instance_done", stage=t, name=STAGE_NAMES[t],
                                       frame=f-1, cycle=prior_done))
            if t:
                boundaries.append(dict(kind="producer_done", stage=t-1, name=STAGE_NAMES[t-1],
                                       frame=f, cycle=stages[t-1, f]["done"]))
            if f >= 2:
                for b in acquired_buffers[t]:
                    boundaries.append(dict(kind="same_slot_previous_consumer_release", buffer=b,
                                           name=BUFFER_NAMES[b], slot=f % 2, frame=f-2,
                                           cycle=lifetimes[b, f-2]["release"]))
            ready = max((row["cycle"] for row in boundaries), default=None)
            launch_lag = stage["start"] - ready if ready is not None else None
            idle_gap = stage["start"] - prior_done if prior_done is not None else None
            if ready is not None:
                require(launch_lag >= 0, f"Stage {t} frame {f} launched before a measured prerequisite")
            record = dict(frame=f, previous_instance_done=prior_done,
                          previous_done_to_start_idle_cycles=idle_gap,
                          boundaries=boundaries, latest_ready_boundary=ready,
                          latest_ready_boundary_sources=[row for row in boundaries if row["cycle"] == ready],
                          start_after_ready_control_poll_lag_cycles=launch_lag,
                          prerequisites_after_previous_done_cycles=ready-prior_done if prior_done is not None else None)
            if f:
                start_interval = stage["start"] - stages[t, f-1]["start"]
                previous_duration = stages[t, f-1]["cycles"]
                require(start_interval == previous_duration + idle_gap,
                        "Start interval does not equal previous duration plus observed idle gap")
                record["start_interval_decomposition"] = dict(start_interval_cycles=start_interval,
                    previous_frame_duration_cycles=previous_duration, idle_gap_cycles=idle_gap,
                    prerequisite_gap_cycles=ready-prior_done, post_ready_launch_lag_cycles=launch_lag)
                if t == 2:
                    require(output_intervals[f] == stage["cycles"] + idle_gap,
                            "Curve output interval does not equal current latency plus previous-DONE-to-START gap")
                    record["curve_done_interval_decomposition"] = dict(interval_cycles=output_intervals[f],
                        current_curve_duration_cycles=stage["cycles"], idle_gap_cycles=idle_gap,
                        prerequisite_gap_cycles=ready-prior_done, post_ready_launch_lag_cycles=launch_lag)
            launches.append(record)
        metric = timing["stage_metrics"][STAGE_NAMES[t]]
        metric["launch_readiness"] = launches
        metric["previous_done_to_start_idle"] = describe(row["previous_done_to_start_idle_cycles"] for row in launches if row["frame"] >= 1)
        metric["late_previous_done_to_start_idle"] = describe(row["previous_done_to_start_idle_cycles"] for row in launches if row["frame"] >= 4)
        metric["late_post_ready_control_poll_lag"] = describe(row["start_after_ready_control_poll_lag_cycles"] for row in launches if row["frame"] >= 4)
    for f in range(1, 8):
        delta = output_intervals[f]
        comparison = {}
        for t in range(3):
            interval = stages[t, f]["start"] - stages[t, f-1]["start"]
            comparison[STAGE_NAMES[t]] = dict(start_interval_cycles=interval,
                output_interval_minus_start_interval_cycles=delta-interval,
                exact_interval_match=delta == interval,
                current_duration_cycles=stages[t, f]["cycles"],
                current_duration_over_budget=stages[t, f]["cycles"] > BUDGET,
                previous_duration_cycles=stages[t, f-1]["cycles"],
                previous_duration_over_budget=stages[t, f-1]["cycles"] > BUDGET)
        alignment.append(dict(from_frame=f-1, to_frame=f, late_steady=f >= 4,
                              curve_done_interval_cycles=delta, stages=comparison,
                              exact_cadence_match_candidates=[name for name, item in comparison.items() if item["exact_interval_match"]]))
    timing["output_cadence_stage_alignment"] = alignment
    timing["readiness_scope"] = (
        "Each launch compares its previous true RTL instance DONE, current producer true RTL DONE, "
        "and prior same-slot actual consumer RELEASE. START minus their maximum is observed CSR/poll/control lag. "
        "Ownership RELEASE has the documented one-cycle negedge sampling phase. First CNN launch has no prior measured boundary. "
        "Wait integrals are never added as causal latency; matching stage/output cadence is a candidate association, not a root-cause claim.")


def audit_observer_ddr(run, text, stages, ddr, ownership, timing):
    rows = [{k: int(v) for k, v in row.items()} for row in read_csv(run / "results/ddr_snapshots.csv")]
    require(len(rows) >= 8 and len(rows) % 4 == 0, "DDR snapshot rows are not complete four-port groups")
    snapshots = []
    for index in range(0, len(rows), 4):
        group = rows[index:index+4]
        require({r["hp"] for r in group} == set(range(4)), "Missing/duplicate snapshot HP")
        require(len({(r["cycle"], r["mask"]) for r in group}) == 1, "Snapshot ports have differing timestamps/masks")
        snapshots.append(dict(cycle=group[0]["cycle"], mask=group[0]["mask"], hp={r["hp"]: r for r in group}))
    require(snapshots[0]["mask"] == 0 and snapshots[-1]["mask"] == -1, "Missing reset/final DDR snapshot")
    require(all(0 <= snap["mask"] <= 7 for snap in snapshots[:-1]), "Unexpected active-stage mask")
    integral_fields = ("ar", "aw", "r", "w", "ar_stall", "aw_stall", "r_stall", "r_back", "w_stall", "b_wait",
                       "rq_sum", "wq_sum", "first_samples", "first_sum", "b_samples", "b_sum",
                       "served", "contested", "rw_concurrent")
    by_mask = {}
    segments = []
    for previous, current in zip(snapshots, snapshots[1:]):
        duration = current["cycle"] - previous["cycle"]
        require(duration >= 0, "DDR snapshots are not chronological")
        if previous["mask"] not in by_mask:
            by_mask[previous["mask"]] = dict(mask=previous["mask"], cycles=0, segments=0,
                                            hp={p: {k: 0 for k in integral_fields} for p in range(4)})
        aggregate = by_mask[previous["mask"]]
        aggregate["cycles"] += duration
        aggregate["segments"] += 1
        deltas = {}
        for p in range(4):
            deltas[p] = {k: current["hp"][p][k] - previous["hp"][p][k] for k in integral_fields}
            require(all(v >= 0 for v in deltas[p].values()), "Cumulative DDR observer counter decreased")
            for k, v in deltas[p].items():
                aggregate["hp"][p][k] += v
        segments.append(dict(start=previous["cycle"], done=current["cycle"], cycles=duration,
                             mask=previous["mask"], hp=deltas))
    triple = records(text, "PHASE4F_TRIPLE")
    require(len(triple) == 4 and {r["HP"] for r in triple} == set(range(4)), "Missing PHASE4F_TRIPLE counters")
    triple_aggregate = by_mask.get(7, dict(mask=7, cycles=0, segments=0,
                                          hp={p: {k: 0 for k in integral_fields} for p in range(4)},
                                          shared=dict(served=0, contested=0, rw_concurrent=0)))
    for row in triple:
        require(row["CYCLES"] == triple_aggregate["cycles"], "Mask7 segment sum differs from cycle observer")
        require(0 <= row["READ_MAX"] <= 2 and 0 <= row["WRITE_MAX"] <= 2, "Triple-active queue exceeds O=2")
        require(row["FIRST_R_MAX"] >= 0 and row["B_LATENCY_MAX"] >= 0, "Negative triple-active response latency maximum")
    observed_triple_segments = [s for s in segments if s["mask"] == 7]
    true_triple_segments = [s for s in timing["stage_overlap_timeline"] if s["mask"] == 7]
    require(len(observed_triple_segments) == len(true_triple_segments), "Mask7 segment count differs from true RTL sweep")
    for observed, true in zip(observed_triple_segments, true_triple_segments):
        require(abs(observed["start"] - true["start"]) <= 1 and abs(observed["done"] - true["done"]) <= 1,
                "Mask7 segment boundaries differ from actual RTL timing by more than one cycle")
    triple_sweep_cycles = sum(s["cycles"] for s in true_triple_segments)
    require(abs(triple_aggregate["cycles"] - triple_sweep_cycles) <= 1,
            "Mask7 cycle integral differs from true RTL overlap sweep by more than one cycle")
    hp_mapping = dict(ar="AR", aw="AW", r="R", w="W", ar_stall="AR_STALL", aw_stall="AW_STALL",
                      r_stall="R_STALL", r_back="R_BACK", w_stall="W_STALL", b_wait="B_WAIT",
                      first_samples="FIRST_R_SAMPLES", first_sum="FIRST_R_SUM", b_samples="B_SAMPLES", b_sum="B_LATENCY_SUM")
    for p in range(4):
        initial, final = snapshots[0]["hp"][p], snapshots[-1]["hp"][p]
        require(all(initial[k] == 0 for k in integral_fields), f"First HP{p} snapshot does not begin before traffic")
        for key, original in hp_mapping.items():
            require(final[key] == ddr["hp_stats"][p][original], f"Final observer HP{p} {key} differs from model")
        require(final["rq_sum"] == ddr["queues"][p]["READ_OCCUPANCY_SUM"] and
                final["wq_sum"] == ddr["queues"][p]["WRITE_OCCUPANCY_SUM"], f"Final queue occupancy integral differs HP{p}")
        require(final["rc"] == final["wc"] == 0, f"Final observer retains HP{p} queue entries")
        require(final["served"] == ddr["shared"]["SERVED"] and final["contested"] == ddr["shared"]["CONTESTED_CYCLES"] and
                final["rw_concurrent"] == ddr["rw_concurrent_cycles"], "Final observer shared counters differ from model")
    for mask, aggregate in by_mask.items():
        for p, row in aggregate["hp"].items():
            duration = aggregate["cycles"]
            row["average_read_queue"] = row["rq_sum"] / duration if duration else None
            row["average_write_queue"] = row["wq_sum"] / duration if duration else None
            row["average_completed_ar_to_first_r"] = row["first_sum"] / row["first_samples"] if row["first_samples"] else None
            row["average_completed_aw_to_b"] = row["b_sum"] / row["b_samples"] if row["b_samples"] else None
        for row in aggregate["hp"].values():
            require(row["served"] == aggregate["hp"][0]["served"] and
                    row["contested"] == aggregate["hp"][0]["contested"], "Snapshot shared counters disagree across HP")
        aggregate["shared"] = {k: aggregate["hp"][0][k] for k in ("served", "contested", "rw_concurrent")}
    drains = [{k: int(v) for k, v in row.items()} for row in read_csv(run / "results/writer_drains.csv")]
    require(len(drains) == 56 and [r["drain"] for r in drains] == list(range(1, 57)), "Missing or duplicated CNN block writer drains")
    require(all(a["cycle"] < b["cycle"] for a, b in zip(drains, drains[1:])),
            "Writer drains are not chronological")
    for f in range(8):
        frame_drains = [r for r in drains if r["frame"] == f]
        require(len(frame_drains) == 7, f"Frame {f} does not have seven CNN writer drains")
        for row in frame_drains:
            require(stages[0, f]["start"] <= row["cycle"] <= stages[0, f]["done"], f"Writer drain outside CNN invocation {f}")
            require(row["credit_ws"] == row["credit_out"] == row["ddr_wc"] == row["ddr_wp"] == 0,
                    f"Writer retains credits or write response frame {f}")
    stage_drains = [{k: int(v) for k, v in row.items()} for row in read_csv(run / "results/stage_drains.csv")]
    expected = {(t, f, p) for t in range(3) for f in range(8) for p in ((0, 1) if t == 0 else (t+1,))}
    require(len(stage_drains) == 32 and {(r["stage"], r["frame"], r["hp"]) for r in stage_drains} == expected,
            "Missing/duplicated per-stage HP drain proof")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(stage_drains, stage_drains[1:])),
            "Stage drain file is not chronological")
    for row in stage_drains:
        require(all(row[k] == 0 for k in ("rc", "wc", "wp", "rvalid", "bvalid")), "Responses cross stage/slot release")
        require(row["cycle"] >= stages[row["stage"], row["frame"]]["done"], "Stage drain precedes RTL completion")
        released_buffers = {0: (3,), 1: (0,), 2: (1, 2, 4)}[row["stage"]]
        lifetime_map = {(r["buffer"], r["frame"]): r for r in ownership["lifetimes"]}
        for b in released_buffers:
            require(row["cycle"] <= lifetime_map[b, row["frame"]]["release"],
                    "Stage response drain occurs after consumer buffer release")
    final = one_record(text, "PHASE4F_PASSIVE_FINAL")
    require(final == dict(WRITER_DRAINS=56, CREDIT_WS=0, CREDIT_OUT=0, OWNERS_RELEASED=1),
            "Passive observer final did not release all owners and CNN writer credits")
    return dict(mask_statistics=[by_mask[k] for k in sorted(by_mask)], segments=segments,
                triple_active=triple_aggregate, triple_queue_latency_max=[r for r in sorted(triple, key=lambda r: r["HP"])],
                true_rtl_triple_cycles=triple_sweep_cycles,
                observer_minus_true_rtl_triple_cycles=triple_aggregate["cycles"] - triple_sweep_cycles,
                writer_drains=drains, stage_drains=stage_drains, passive_final=final,
                triple_latency_scope="Response latency samples completed during mask7; request may have started before mask7. Occupancy integrals are time actually spent in mask7.",
                boundary_scope="negedge observer sees RTL monitoring transitions up to one cycle after recorded RTL START/DONE",
                response_endpoint_phase="Snapshot deltas cover (begin,end] counter updates; PHASE4F_TRIPLE latency maxima use the current active negedge mask. One boundary cycle may belong to different response-sample sets. Full-run model maxima are authoritative; mask means/maxima are not tested against each other.")


def audit_payload_traffic(run, manifest, ddr):
    cnn_path = Path(manifest["phase4e_reference"]) / "analysis.json"
    single_path = run.parent / "phase4c_01/single_o2/analysis.json"
    cnn = json.loads(cnn_path.read_text())
    single = json.loads(single_path.read_text())
    require(cnn["stage_gate"] == "CNN_SYSTEM_STAGE_30FPS_PASS" and cnn["numerical"]["raw_mismatch"] == 0,
            "CNN isolated reference did not pass full raw validation")
    require(single["gate"] == "PASS" and single["full_three_module_numerical"] == "PASS",
            "Bilinear/Curve isolated reference did not pass full numerical validation")
    references = {row["HP"]: row for row in cnn["hp_stats"] if row["HP"] <= 1}
    references.update({row["HP"]: row for row in single["hp"] if row["HP"] >= 2})
    require(set(references) == set(range(4)), "Isolated payload reference missing a port")
    checks = []
    for stats in ddr["hp_stats"]:
        p = stats["HP"]
        fields = {}
        for key in ("AR", "AW", "R", "W", "WRITE_BYTES"):
            expected = 8 * references[p][key]
            fields[key] = dict(observed=stats[key], expected=expected, match=stats[key] == expected,
                               gating=key in ("R", "W", "WRITE_BYTES"))
            if key in ("R", "W", "WRITE_BYTES"):
                require(stats[key] == expected, f"HP{p} {key} payload differs from eight complete frames")
        checks.append(dict(hp=p, fields=fields))
    return dict(gate="PASS", checks=checks,
                reference_sha256={cnn_path.as_posix(): sha(cnn_path), single_path.as_posix(): sha(single_path)},
                scope="R/W payload beats and useful write bytes must equal eight complete isolated frames. AR/AW burst segmentation is diagnostic.")


def fail_attribution(timing, ownership, ddr):
    categories = []
    evidence = []
    for t, label in ((0, "A"), (1, "B"), (2, "C")):
        late = timing["stage_metrics"][STAGE_NAMES[t]]["late_latency"]
        if late["max"] > BUDGET:
            categories.append(label)
            evidence.append(f"{STAGE_NAMES[t]} measured late-frame latency max {late['max']} exceeds {BUDGET}")
    if not categories and timing["interval_gate"] == "FAIL" and ddr["shared"]["CONTESTED_CYCLES"] > 0:
        categories.append("D")
        evidence.append("Measured output interval fails while all late stage durations fit; shared DDR contention exists. This identifies a candidate, not a measured counterfactual cause.")
    if timing["interval_gate"] == "FAIL" and timing["pipeline_overlap_gate"] == "FAIL":
        categories.append("E")
        evidence.append("The actual RTL sweep contains no requested CNN(N+2)/Bilinear(N+1)/Curve(N) overlap; scheduler concurrency is a candidate. Ownership passes, and legal buffer-wait cycles alone do not prove independent scheduler causation.")
    late_buffer_wait = sum(r["buffer"] for r in ownership["waits"]["per_frame"] if r["frame"] >= 4)
    return dict(categories=categories, evidence=evidence,
                measured_late_buffer_wait_cycles=late_buffer_wait,
                buffer_wait_causal_scope="A slower consumer can cause legal buffer waits. Wait count alone is not root-cause evidence.",
                scope="Measured candidate attribution only; no RTL optimization or counterfactual run")


def summary_markdown(result):
    lines = ["# Phase 4F independent short multi-frame analysis", "",
             f"Run: `{result['run']}`", "", f"Conclusion: **{result['conclusion']}**", ""]
    if result.get("errors"):
        lines += ["Evidence checks failed:", ""] + [f"- {error}" for error in result["errors"]]
        return "\n".join(lines) + "\n"
    timing = result["timing"]
    lines += ["FRAMES=8; O=2/2; DDR delay=16; service period=1; poll=128; clock=100 MHz.", "",
              "24 complete numerical checks: CNN 19,080; Bilinear 2,747,520; Curve 2,747,520 raw scalars/frame. Mismatch=0, guard=0, hazard=0; natural exit=0.", "",
              "| Frame | CNN start/done | Bilinear start/done | Curve start/done |", "|---:|---:|---:|---:|"]
    stages = {(s["stage"], s["frame"]): s for s in result["stages"]}
    for f in range(8):
        spans = [f"{stages[t, f]['start']} / {stages[t, f]['done']}" for t in range(3)]
        lines.append(f"| {f} | " + " | ".join(spans) + " |")
    lines += ["", "| Output frames | Curve done interval (cycles) |", "|---|---:|"]
    lines += [f"| {row['from_frame']} -> {row['to_frame']} | {row['cycles']} |" for row in timing["curve_done_intervals"]]
    for label, key in (("All seven intervals", "all_curve_intervals"), ("Late four steady intervals (ending frames 4..7)", "steady_curve_intervals")):
        stats = timing[key]
        lines += ["", f"{label}: min={stats['min']}, mean={stats['mean']:.3f}, max={stats['max']}; budget={BUDGET} cycles."]
    lines += ["", "| Stage | Late start interval min/mean/max | Late latency min/mean/max |", "|---|---:|---:|"]
    for name, metric in timing["stage_metrics"].items():
        a, b = metric["late_start_interval"], metric["late_latency"]
        lines.append(f"| {name} | {a['min']} / {a['mean']:.3f} / {a['max']} | {b['min']} / {b['mean']:.3f} / {b['max']} |")
    lines += ["", "| Stage start frames | CNN interval | Bilinear interval | Curve interval |", "|---|---:|---:|---:|"]
    for index in range(7):
        values = [timing["stage_metrics"][name]["start_intervals"][index]["cycles"] for name in STAGE_NAMES.values()]
        lines.append(f"| {index} -> {index+1} | " + " | ".join(map(str, values)) + " |")
    lines += ["", "| Stage | Frame | Previous DONE-to-START gap | Latest ready boundary | Post-ready launch lag | Latest prerequisite source |", "|---|---:|---:|---:|---:|---|"]
    for name, metric in timing["stage_metrics"].items():
        for row in metric["launch_readiness"]:
            sources = ", ".join(f"{item['kind']}:{item['name']}({item['frame']})" for item in row["latest_ready_boundary_sources"]) or "first launch"
            idle = row["previous_done_to_start_idle_cycles"]
            boundary = row["latest_ready_boundary"]
            lag = row["start_after_ready_control_poll_lag_cycles"]
            lines.append(f"| {name} | {row['frame']} | {idle if idle is not None else 'n/a'} | {boundary if boundary is not None else 'n/a'} | {lag if lag is not None else 'n/a'} | {sources} |")
    lines += ["", timing["readiness_scope"], ""]
    lines += ["", "| CNN frame | Bilinear frame | Curve frame | Actual overlap start/done | Cycles |", "|---:|---:|---:|---:|---:|"]
    lines += [f"| {row['cnn_frame']} | {row['bilinear_frame']} | {row['curve_frame']} | {row['overlap_start']} / {row['overlap_done']} | {row['overlap_cycles']} |" for row in timing["triplet_overlap"]]
    lines += ["", "| True RTL interval | Active stage(frame) | Mask |", "|---:|---|---:|"]
    for row in timing["stage_overlap_timeline"]:
        active = ", ".join(f"{item['name']}({item['frame']})" for item in row["active"]) or "idle"
        lines.append(f"| {row['start']} / {row['done']} | {active} | {row['mask']} |")
    lines += ["", "| Idle wait stage | Dependency | Buffer | Both | Union blocked | Ready (CSR/poll included) |", "|---|---:|---:|---:|---:|---:|"]
    for name, row in result["ownership"]["waits"]["by_stage"].items():
        lines.append(f"| {name} | {row['dependency']} | {row['buffer']} | {row['both']} | {row['union_blocked']} | {row['ready']} |")
    lines += ["", "| Buffer | Slot | Occupied cycles | Peak simultaneous slots |", "|---|---:|---:|---:|"]
    for row in result["ownership"]["slot_occupancy"]:
        lines.append(f"| {row['name']} | {row['slot']} | {row['occupied_cycles']} | {row['peak_slots']} |")
    ddr = result["ddr"]
    lines += ["", "| HP | AR | AW | R beats | W beats | Useful write bytes | R/W queue peak |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for p, row in enumerate(ddr["hp_stats"]):
        queue = ddr["queues"][p]
        lines.append(f"| {p} | {row['AR']} | {row['AW']} | {row['R']} | {row['W']} | {row['WRITE_BYTES']} | {queue['READ_MAX']} / {queue['WRITE_MAX']} |")
    lines += ["", "| HP | AR stall | AW stall | R wait | R backpressure | W wait | B wait |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in ddr["hp_stats"]:
        values = [row[k] for k in ("AR_STALL", "AW_STALL", "R_STALL", "R_BACK", "W_STALL", "B_WAIT")]
        lines.append(f"| {row['HP']} | " + " | ".join(map(str, values)) + " |")
    lines += ["", "| HP | AR-firstR mean/max | AR-lastR mean | AW-B mean/max | R/W occupancy sums |", "|---:|---:|---:|---:|---:|"]
    format_mean = lambda value: "n/a" if value is None else f"{value:.3f}"
    for p, row in enumerate(ddr["hp_stats"]):
        queue = ddr["queues"][p]
        lines.append(f"| {p} | {format_mean(row['average_ar_to_first_r_cycles'])} / {row['FIRST_R_MAX']} | {format_mean(row['average_ar_to_last_r_cycles'])} | {format_mean(row['average_aw_to_b_cycles'])} / {row['B_LATENCY_MAX']} | {queue['READ_OCCUPANCY_SUM']} / {queue['WRITE_OCCUPANCY_SUM']} |")
    triple = ddr["observer"]["triple_active"]
    lines += ["", f"Actual mask7 duration: {triple['cycles']} cycles; service={triple['shared']['served']}; contested={triple['shared']['contested']}; R/W concurrent={triple['shared']['rw_concurrent']}.", "",
              "| Mask7 HP | AR/AW | R/W beats | R/W mean queue | R/W queue peak | Completed firstR mean/max | Completed B mean/max |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for maxima in ddr["observer"]["triple_queue_latency_max"]:
        p = maxima["HP"]
        row = triple["hp"][p]
        lines.append(f"| {p} | {row['ar']} / {row['aw']} | {row['r']} / {row['w']} | {format_mean(row.get('average_read_queue'))} / {format_mean(row.get('average_write_queue'))} | {maxima['READ_MAX']} / {maxima['WRITE_MAX']} | {format_mean(row.get('average_completed_ar_to_first_r'))} / {maxima['FIRST_R_MAX']} | {format_mean(row.get('average_completed_aw_to_b'))} / {maxima['B_LATENCY_MAX']} |")
    lines += ["", "Mask7 stall counters and every ownership/drain event remain in `analysis.json`. Response latency belongs to responses completed in that mask; their request can start earlier.", "",
              f"Peak concurrent stages: {timing['peak_concurrent_stages']}; measured overlap gate: {timing['pipeline_overlap_gate']}.", "",
              f"Ownership gate: {result['ownership']['gate']}; DDR response drain gate: {result['ddr']['response_drain_gate']}.", "",
              "56 CNN writer block drains and 32 stage/HP drains have zero pending write credits and responses. Payload beats/bytes conserve eight complete isolated frames.", "",
              "Write-credit is an RTL scheduling overlay. This run does not establish a new HLS export/IP release, implementation, or board result.", "",
              "Stop after the eight-frame report/checkpoint. Further work requires a separate decision from Master."]
    return "\n".join(lines) + "\n"


def analyze(run):
    run = Path(run).resolve()
    result = dict(run=run.as_posix(), conclusion="INCOMPLETE", consistency_gate="FAIL")
    try:
        manifest = json.loads((run / "run_manifest.json").read_text())
        termination = json.loads((run / "exit_status.json").read_text())
        text = (run / "system.log").read_text()
        result.update(manifest=manifest, termination=termination)
        require(termination.get("exit_code") == 0, "Simulation did not naturally exit with code zero")
        require(not re.search(r"Fatal:|RAW_ERROR|\$fatal", text), "Fatal/numerical error appears in system log")
        runtime = audit_configuration(run, manifest, text)
        frozen_evidence = audit_frozen_evidence(run, manifest, termination)
        stages, events, final = audit_stages(run, text)
        timing = timing_metrics(stages, events)
        ddr = audit_ddr(text, runtime)
        result.update(runtime_config_verified=runtime, stages=[stages[k] for k in sorted(stages)],
                      frozen_evidence=frozen_evidence, final=final, numerical_gate="PASS", timing=timing, ddr=ddr,
                      numerical=dict(frames=8, stages=24, scalar_counts_per_frame={STAGE_NAMES[t]: SCALARS[t] for t in range(3)},
                                     scalar_counts_all_frames={STAGE_NAMES[t]: SCALARS[t]*8 for t in range(3)},
                                     raw_mismatches=0, guard_errors=0, hazard_errors=0))
        ownership = audit_ownership(run, stages, events)
        scheduling_readiness_metrics(stages, ownership, timing)
        ddr["observer"] = audit_observer_ddr(run, text, stages, ddr, ownership, timing)
        ddr["traffic_x8"] = audit_payload_traffic(run, manifest, ddr)
        result["ownership"] = ownership
        verdict = timing["interval_gate"]
        result.update(consistency_gate="PASS", conclusion=f"SHORT_MULTI_FRAME_30FPS_{verdict}",
                      validation_gate="PASS" if timing["pipeline_overlap_gate"] == "PASS" else "FAIL",
                      attribution=fail_attribution(timing, ownership, ddr) if verdict == "FAIL" else dict(categories=[], evidence=[]))
        evidence_files = ("system.log", "run_manifest.json", "exit_status.json", "system_tb.sv",
                          "results/stage_events.csv", "results/ownership_events.csv", "results/wait_stats.csv",
                          "results/slot_occupancy.csv", "results/ddr_snapshots.csv", "results/writer_drains.csv",
                          "results/stage_drains.csv")
        result["evidence_sha256"] = {name: sha(run / name) for name in evidence_files}
    except (EvidenceError, KeyError, ValueError, TypeError, OSError) as exc:
        result.update(conclusion="INCOMPLETE", consistency_gate="FAIL", errors=[str(exc)])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run)
    if "timing" in result:
        columns = ("start", "done", "cycles", "mask", "cnn_frame", "bilinear_frame", "curve_frame")
        with (args.run / "results/stage_overlap_timeline.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in result["timing"]["stage_overlap_timeline"]:
                frames = {item["stage"]: item["frame"] for item in row["active"]}
                writer.writerow(dict(start=row["start"], done=row["done"], cycles=row["cycles"], mask=row["mask"],
                                     cnn_frame=frames.get(0, ""), bilinear_frame=frames.get(1, ""), curve_frame=frames.get(2, "")))
    (args.run / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (args.run / "analysis_summary.md").write_text(summary_markdown(result), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("run", "conclusion", "consistency_gate")}))
    if result["consistency_gate"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
