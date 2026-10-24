"""Compare headerless FPGA INT16 NCHW dumps with an identified integer Golden.

No candidate-side JSON or Python execution report is required. The declared
bundle ID must come from B's deployment record. This tool compares files only;
it cannot establish that a candidate actually came from a board.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from .integer import load_package
from .io import sha256


def _child(directory, name):
    directory = Path(directory).resolve()
    result = (directory / name).resolve()
    if not result.is_relative_to(directory) or result == directory:
        raise ValueError("Golden metadata path escapes its directory")
    return result


def _metadata(meta):
    shape = meta.get("shape")
    if not isinstance(shape, list) or len(shape) != 4 or shape[0] != 1 or any(type(v) is not int or v < 1 for v in shape):
        raise ValueError("Golden must describe nonempty NCHW batch-one tensors")
    if meta.get("dtype") != "<i2" or meta.get("layout", "NCHW") != "NCHW":
        raise ValueError("Golden tensor must be headerless little-endian signed INT16 NCHW")
    if meta.get("bytes") != int(np.prod(shape, dtype=object)) * 2:
        raise ValueError("Golden tensor byte count disagrees with shape")
    return tuple(shape)


def _raw_comparison(candidate, meta, expected_path=None):
    """Compare validated expected metadata against one raw candidate file."""
    shape = _metadata(meta)
    expected_sha = meta["sha256"]
    result = dict(exact=False, shape=list(shape), dtype="<i2", expected_bytes=meta["bytes"], expected_raw_sha256=expected_sha,
                  candidate_file=str(candidate))
    expected_bytes = None
    if expected_path is not None:
        expected_bytes = Path(expected_path).read_bytes()
        if len(expected_bytes) != meta["bytes"] or sha256(expected_path) != expected_sha:
            raise ValueError("Golden raw tensor length/hash mismatch: " + str(expected_path))
    actual_bytes = Path(candidate).read_bytes()
    result.update(actual_bytes=len(actual_bytes), actual_raw_sha256=sha256(candidate))
    if len(actual_bytes) != meta["bytes"]:
        result["reason"] = "candidate byte count mismatch (padding, packing or truncated dump)"
        return result
    actual = np.frombuffer(actual_bytes, dtype="<i2").reshape(shape)
    result.update(actual_min=int(actual.min()), actual_max=int(actual.max()))
    if expected_bytes is None:
        # Large cases retain all-node hashes, while small cases retain raw
        # intermediates. Hash-only comparison cannot identify a numeric sample.
        result.update(exact=result["actual_raw_sha256"] == expected_sha, comparison="sha256_only",
                      first_difference_nchw=None, max_abs_error=None, mean_abs_error=None)
        if not result["exact"]:
            result["reason"] = "node SHA-256 mismatch; use a small raw-node Golden for numeric localization"
        return result
    expected = np.frombuffer(expected_bytes, dtype="<i2").reshape(shape)
    difference = actual.astype(np.int64) - expected.astype(np.int64)
    mask = difference != 0
    count = int(np.count_nonzero(mask))
    first = list(np.unravel_index(int(np.argmax(mask)), shape)) if count else None
    first = [int(v) for v in first] if first is not None else None
    result.update(exact=count == 0, comparison="raw_elementwise", different_elements=count,
                  first_difference_nchw=first,
                  expected_at_first=int(expected[tuple(first)]) if first is not None else None,
                  actual_at_first=int(actual[tuple(first)]) if first is not None else None,
                  expected_min=int(expected.min()), expected_max=int(expected.max()),
                  max_abs_error=int(np.abs(difference).max()), mean_abs_error=float(np.abs(difference).mean()),
                  mean_signed_error=float(difference.mean()))
    return result


def compare(golden_dir, actual_output, package, bundle_id, actual_nodes=None, input_sha256=None, allow_partial_nodes=False):
    """Return a JSON-compatible comparison report; never touch candidate files."""
    golden_dir, actual_output = Path(golden_dir), Path(actual_output)
    result = dict(exact=False, hardware_test=False, comparison_scope="final_output_only" if actual_nodes is None else "final_output_and_nodes",
                  candidate_origin="external_raw_files_not_board_verified", errors=[], comparisons=[],
                  candidate_declared_bundle_id=bundle_id, candidate_declared_input_sha256=input_sha256,
                  candidate_input_identity_verified=False)
    try:
        manifest, graph, _ = load_package(package)
        report = json.loads((golden_dir / "report.json").read_text(encoding="utf-8"))
        expected_manifest_sha = sha256(Path(package) / "manifest.json")
        result.update(expected_bundle_id=manifest["identity"]["bundle_id"], expected_manifest_sha256=expected_manifest_sha,
                      golden_report_sha256=sha256(golden_dir / "report.json"))
        if report.get("manifest_sha256") != expected_manifest_sha:
            result["errors"].append("Golden run belongs to a different package manifest")
        if bundle_id != manifest["identity"]["bundle_id"]:
            result["errors"].append("candidate deployment bundle ID differs from the Golden package")
        input_meta = json.loads((golden_dir / "input.json").read_text(encoding="utf-8"))
        _metadata(input_meta)
        input_path = _child(golden_dir, input_meta["file"])
        if input_path.stat().st_size != input_meta["bytes"] or sha256(input_path) != input_meta["sha256"]:
            raise ValueError("Golden input length/hash mismatch")
        result["expected_input_sha256"] = input_meta["sha256"]
        if input_sha256 is not None:
            result["candidate_input_identity_verified"] = input_sha256 == input_meta["sha256"]
            if not result["candidate_input_identity_verified"]:
                result["errors"].append("candidate declared input SHA-256 differs from the Golden input")
        output_meta = json.loads((golden_dir / "output.json").read_text(encoding="utf-8"))
        _metadata(output_meta)
        if output_meta["shape"][1] != 3:
            raise ValueError("final Golden output must have three RGB channels")
        output_frac = next(n.get("activation_frac", manifest["quantization"]["activation_frac"]) for n in graph["nodes"] if n["id"] == graph["output"])
        if output_meta.get("activation_frac") != output_frac:
            raise ValueError("Golden output scale differs from the identified graph")
        if "output" in report:
            if any(report["output"].get(k) != output_meta.get(k) for k in ("file", "shape", "dtype", "bytes", "sha256", "activation_frac")):
                raise ValueError("Golden output metadata differs from its run report")
        result["activation_frac"] = output_frac
        result["actual_output_format"] = "headerless little-endian signed INT16, contiguous NCHW, no row/channel padding"
        node_results = []
        if actual_nodes is not None:
            declared = report.get("nodes", [])
            if [n.get("id") for n in declared] != [n["id"] for n in graph["nodes"]]:
                raise ValueError("Golden node coverage/order differs from the identified graph")
            missing, filenames = [], set()
            for node in declared:
                node_id = node["id"]
                filename = node.get("file", node_id.replace(".", "_") + ".raw")
                if filename in filenames:
                    raise ValueError("Golden node raw filenames collide")
                filenames.add(filename)
                candidate = _child(actual_nodes, filename)
                if not candidate.is_file():
                    missing.append(node_id)
                    continue
                meta = dict(node, dtype="<i2", layout="NCHW")
                expected_path = _child(golden_dir / "nodes", filename) if node.get("raw_intermediate_saved", True) else None
                comparison = _raw_comparison(candidate, meta, expected_path)
                comparison.update(tensor=node_id, activation_frac=node.get("activation_frac"))
                node_results.append(comparison)
            result.update(compared_nodes=len(node_results), total_nodes=len(declared), missing_nodes=missing,
                          node_coverage_complete=not missing, partial_nodes_explicitly_allowed=bool(allow_partial_nodes))
            if missing and not allow_partial_nodes:
                result["errors"].append(f"missing {len(missing)} candidate node dumps; use --allow-partial-nodes to explicitly limit scope")
            if not node_results:
                result["errors"].append("no candidate node dumps were compared")
        # Execution-order node results come before the final output, ensuring
        # the earliest available divergent node is reported, not lexical order.
        result["comparisons"].extend(node_results)
        final_comparison = _raw_comparison(actual_output, output_meta, _child(golden_dir, output_meta["file"]))
        final_comparison["tensor"] = "output"
        result["comparisons"].append(final_comparison)
        result["raw_output_exact"] = final_comparison["exact"]
        result["first_different_tensor"] = next((n for n in result["comparisons"] if not n["exact"]), None)
        result["exact"] = not result["errors"] and all(n["exact"] for n in result["comparisons"])
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        result["errors"].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--golden-dir", required=True)
    parser.add_argument("--actual-output", required=True)
    parser.add_argument("--package", required=True, help="package whose manifest produced this Golden")
    parser.add_argument("--bundle-id", required=True, help="candidate's deployed bundle ID, taken from B's run record")
    parser.add_argument("--input-sha256", help="optional candidate-declared input.raw SHA-256; absence is reported")
    parser.add_argument("--actual-nodes", help="directory of raw node dumps named exactly as Golden node files")
    parser.add_argument("--allow-partial-nodes", action="store_true", help="explicitly allow a subset of node dumps")
    parser.add_argument("--report", required=True, help="new JSON report path (existing evidence is never overwritten)")
    args = parser.parse_args()
    report_path = Path(args.report)
    if report_path.exists():
        print("Refusing to overwrite an existing comparison report", file=sys.stderr)
        raise SystemExit(1)
    result = compare(args.golden_dir, args.actual_output, args.package, args.bundle_id,
                     args.actual_nodes, args.input_sha256, args.allow_partial_nodes)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(exact=result["exact"], scope=result["comparison_scope"], errors=result["errors"], report=str(report_path))))
    raise SystemExit(0 if result["exact"] else 1)


if __name__ == "__main__":
    main()
