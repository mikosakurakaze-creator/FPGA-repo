"""Deterministic pinned GridDehazeNet quantization and explicit operator DAG.

This module exports an A-group numerical proposal, not an accepted B-group ABI.
It neither imports old TinyRestore kernels nor changes the official network.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np

from .fetch import COMMIT, UPSTREAM, WEIGHT_NAME, WEIGHT_SHA256, sha256, verify_source

FORMAT_VERSION = "griddehaze-fixed-v1"
MODEL_ARGUMENTS = dict(in_channels=3, depth_rate=16, kernel_size=3, stride=2,
                       height=3, width=6, num_dense_layer=4, growth_rate=16,
                       attention=True)


def canonical_json(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def load_official(source_dir: str | Path):
    """Strict CPU load only after verifying every pinned executable source byte."""
    import torch

    source = Path(source_dir).resolve()
    verify_source(source)
    # Load the dependent module under its upstream name only during execution.
    # Restore sys.modules to avoid using/importing an unrelated local model.py.
    previous = sys.modules.get("residual_dense_block")
    residual_spec = importlib.util.spec_from_file_location("residual_dense_block", source / "residual_dense_block.py")
    residual = importlib.util.module_from_spec(residual_spec)
    try:
        sys.modules["residual_dense_block"] = residual
        residual_spec.loader.exec_module(residual)
        spec = importlib.util.spec_from_file_location("_griddehaze_pinned_model", source / "model.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop("residual_dense_block", None)
        else:
            sys.modules["residual_dense_block"] = previous
    model = module.GridDehazeNet(**MODEL_ARGUMENTS).cpu().eval()
    state = torch.load(source / WEIGHT_NAME, map_location="cpu", weights_only=True)
    # The pinned official checkpoint is DataParallel-wrapped. Remove this
    # uniform namespace only; strict=True still checks every key and shape.
    if not state or not all(name.startswith("module.") for name in state):
        raise ValueError("Pinned checkpoint must have the documented uniform DataParallel namespace")
    state = {name[len("module."):]: value for name, value in state.items()}
    model.load_state_dict(state, strict=True)
    if sum(p.numel() for p in model.parameters()) != 958051:
        raise ValueError("Unexpected official parameter count")
    if any(not torch.isfinite(p).all() for p in model.parameters()):
        raise ValueError("Non-finite official parameter")
    return model


def build_graph() -> dict:
    """Translate the pinned forward exactly, keeping all rounding boundaries.

    Names map to PyTorch named_modules/state_dict. The source's loop traversal,
    concatenation order, trained coefficients, and dynamic deconv output_size
    are represented explicitly and checked against official FP32 execution.
    """
    nodes = [{"id": "input", "op": "input", "inputs": []}]

    def node(identifier, op, inputs, **attributes):
        nodes.append(dict(id=identifier, op=op, inputs=list(inputs), **attributes))
        return identifier

    def conv(module, source, transpose=False, target=None):
        stride = 2 if (transpose or (module.startswith("downsample_module") and module.endswith("conv1"))) else 1
        result = node(module, "deconv" if transpose else "conv", [source], module=module,
                      weight=f"{module}.weight", bias=f"{module}.bias", stride=[stride, stride],
                      padding=[0, 0] if module.endswith("conv_1x1") else [1, 1], dilation=[1, 1], groups=1)
        if transpose:
            nodes[-1]["output_like"] = target
        return result

    def relu(source):
        return node(source + ".relu", "relu", [source])

    def rdb(module, source):
        out = source
        for index in range(4):
            dense = f"{module}.residual_dense_layers.{index}"
            activated = relu(conv(dense + ".conv", out))
            out = node(dense + ".cat", "cat", [out, activated], axis=1)
        out = conv(module + ".conv_1x1", out)
        return node(module + ".add", "add", [out, source])

    def down(module, source):
        return relu(conv(module + ".conv2", relu(conv(module + ".conv1", source))))

    def up(module, source, target):
        return relu(conv(module + ".conv", relu(conv(module + ".deconv", source, True, target))))

    def mix(i, j, left, right):
        channels = 16 * 2 ** i
        pieces = []
        for branch, source in enumerate((left, right)):
            identifier = f"coefficient.{i}.{j}.{branch}"
            pieces.append(node(identifier + ".mul", "mulcoef", [source], coefficient=identifier,
                               coefficient_frac=14, source_index=[i, j, branch], channels=channels))
        return node(f"grid.{i}.{j}.add", "add", pieces)

    inp = conv("conv_in", "input")
    grid = [[None] * 6 for _ in range(3)]
    grid[0][0] = rdb("rdb_in", inp)
    for j in range(1, 3):
        grid[0][j] = rdb(f"rdb_module.0_{j-1}", grid[0][j-1])
    for i in range(1, 3):
        grid[i][0] = down(f"downsample_module.{i-1}_0", grid[i-1][0])
    for i in range(1, 3):
        for j in range(1, 3):
            grid[i][j] = mix(i, j, rdb(f"rdb_module.{i}_{j-1}", grid[i][j-1]),
                              down(f"downsample_module.{i-1}_{j}", grid[i-1][j]))
    grid[2][3] = rdb("rdb_module.2_2", grid[2][2])
    for j in range(4, 6):
        grid[2][j] = rdb(f"rdb_module.2_{j-1}", grid[2][j-1])
    for i in (1, 0):
        grid[i][3] = mix(i, 3, rdb(f"rdb_module.{i}_2", grid[i][2]),
                           up(f"upsample_module.{i}_3", grid[i+1][3], grid[i][2]))
    for i in (1, 0):
        for j in range(4, 6):
            grid[i][j] = mix(i, j, rdb(f"rdb_module.{i}_{j-1}", grid[i][j-1]),
                               up(f"upsample_module.{i}_{j}", grid[i+1][j], grid[i][j-1]))
    result = relu(conv("conv_out", rdb("rdb_out", grid[0][5])))
    identifiers = [x["id"] for x in nodes]
    if len(set(identifiers)) != len(identifiers):
        raise AssertionError("Duplicate DAG node")
    return {"format_version": FORMAT_VERSION, "input": "input", "output": result, "nodes": nodes}


def round_half_away(array):
    """Use binary64 only during parameter conversion, never integer inference."""
    value = np.asarray(array, dtype=np.float64)
    return np.copysign(np.floor(np.abs(value) + 0.5), value)


def _quantize_weight(value, bits, axis):
    array = np.asarray(value, dtype=np.float64)
    reduce_axes = tuple(index for index in range(array.ndim) if index != axis)
    max_abs = np.max(np.abs(array), axis=reduce_axes)
    limit = (1 << (bits - 1)) - 1
    frac = np.array([math.floor(math.log2(limit / float(v))) if v else 0 for v in max_abs], dtype=np.int64)
    if np.any(frac < -30) or np.any(frac > 40):
        raise ValueError("Unsupported weight fraction; review integer shifting bounds")
    shape = [1] * array.ndim
    shape[axis] = array.shape[axis]
    converted = round_half_away(array * np.exp2(frac.reshape(shape)))
    if np.any(np.abs(converted) > limit):
        raise ValueError("Weight range proof failed")
    return converted.astype("<i1" if bits == 8 else "<i2"), frac


def export(source_dir: str | Path, out_dir: str | Path, activation_frac=10, weight_bits=8,
           scales_path: str | Path | None = None) -> dict:
    import torch

    if not isinstance(activation_frac, int) or not 0 <= activation_frac <= 14:
        raise ValueError("activation_frac must be an integer in [0,14]")
    if weight_bits not in (8, 16):
        raise ValueError("weight_bits must be 8 or 16")
    source = Path(source_dir)
    sources = verify_source(source)
    model = load_official(source)
    state = {name: tensor.detach().cpu().numpy() for name, tensor in model.state_dict().items()}
    graph = build_graph()
    calibration = None
    scales_sha256 = None
    if scales_path is not None:
        raw_scales = Path(scales_path).read_bytes()
        scales_sha256 = hashlib.sha256(raw_scales).hexdigest()
        calibration = json.loads(raw_scales)
        node_fracs = calibration['node_fracs']
        if set(node_fracs) != {node['id'] for node in graph['nodes']}:
            raise ValueError('Calibration must specify exactly all DAG node IDs')
        if any(type(frac) is not int or not 0 <= frac <= 14 for frac in node_fracs.values()):
            raise ValueError('Every calibrated activation fraction must be an integer in [0,14]')
    else:
        node_fracs = {node['id']: activation_frac for node in graph['nodes']}
    for node in graph['nodes']:
        node['activation_frac'] = node_fracs[node['id']]
    activation_frac = node_fracs[graph['input']]
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / name for name in ("manifest.json", "graph.json", "parameters.bin")]
    if calibration is not None:
        targets.append(output / 'scale_config.json')
    if any(target.exists() for target in targets):
        raise FileExistsError(f"Preserve previous export; choose a new output directory: {output}")
    payload = bytearray()
    parameters = []
    bounds = []

    def append(name, array, layout, **metadata):
        array = np.ascontiguousarray(array)
        raw = array.tobytes(order="C")
        padding = (-len(payload)) % 64
        payload.extend(b"\x00" * padding)
        descriptor = dict(name=name, shape=list(array.shape), dtype=array.dtype.name,
                          byte_order="little", layout=layout, offset=len(payload), nbytes=len(raw),
                          sha256=hashlib.sha256(raw).hexdigest(), **metadata)
        parameters.append(descriptor)
        payload.extend(raw)

    used_parameters = set()
    for item in graph["nodes"]:
        if item["op"] in ("conv", "deconv"):
            transpose = item["op"] == "deconv"
            axis = 1 if transpose else 0
            weight, frac = _quantize_weight(state[item["weight"]], weight_bits, axis)
            item["weight_frac"] = frac.tolist()
            item["kernel_size"] = list(weight.shape[2:])
            input_frac = node_fracs[item['inputs'][0]]
            output_frac = item['activation_frac']
            shifts = input_frac + frac - output_frac
            item['requantization_shift'] = shifts.tolist()
            bias_float = np.asarray(state[item["bias"]], np.float64) * np.exp2(input_frac + frac)
            if np.any(np.abs(bias_float) >= 2 ** 63 - 1024):
                raise ValueError("Bias outside signed INT64")
            bias = round_half_away(bias_float).astype("<i8")
            append(item["weight"], weight, "IOHW" if transpose else "OIHW", frac=frac.tolist(), quantization_axis=axis)
            append(item["bias"], bias, "O", frac=(input_frac + frac).tolist())
            used_parameters.update((item["weight"], item["bias"]))
            axes = tuple(index for index in range(4) if index != axis)
            sums = np.sum(np.abs(weight.astype(np.int64)), axis=axes, dtype=np.int64)
            accumulator = [32768 * int(s) + abs(int(b)) for s, b in zip(sums, bias)]
            # A negative weight frac requires exact left shift before clamping.
            rounding_temporaries = [bound + (1 << (int(shift)-1)) if shift > 0 else bound
                                    for bound, shift in zip(accumulator, shifts)]
            requant_bounds = [(bound + (1 << (int(shift)-1))) >> int(shift) if shift > 0
                             else bound << (-int(shift)) for bound, shift in zip(accumulator, shifts)]
            if max(accumulator + rounding_temporaries + requant_bounds) >= 2 ** 63:
                raise ValueError(f"INT64 bound failed: {item['id']}")
            item["accumulator_abs_bound"] = accumulator
            bounds.append(dict(node=item["id"], max_accumulator_abs_bound=max(accumulator),
                               maximum_terms=int(np.prod([weight.shape[index] for index in axes])),
                               max_rounding_temporary_abs_bound=max(rounding_temporaries),
                               max_preclamp_abs_bound=max(requant_bounds)))
        elif item["op"] == "mulcoef":
            i, j, branch = item["source_index"]
            values = state["coefficient"][i, j, branch, :item["channels"]]
            quantized = round_half_away(values.astype(np.float64) * (1 << 14))
            if np.any(quantized < -32768) or np.any(quantized > 32767):
                raise ValueError("Learned coefficient overflows Q14; requires explicit new scheme")
            append(item["coefficient"], quantized.astype("<i2"), "C", frac=14, source_index=item["source_index"])
    # Include the full tensor (including inactive slices) so every original
    # trainable parameter remains traceable rather than silently discarded.
    full_coefficient = round_half_away(state["coefficient"].astype(np.float64) * (1 << 14))
    if np.any(full_coefficient < -32768) or np.any(full_coefficient > 32767):
        raise ValueError("Full source coefficient tensor overflows Q14")
    append("coefficient.full", full_coefficient.astype("<i2"), "HWBC", frac=14, runtime_used=False)
    used_parameters.add("coefficient")
    if used_parameters != set(state):
        raise ValueError(f"State parameters not accounted for: {set(state) ^ used_parameters}")

    graph_bytes = canonical_json(graph)
    quantization = dict(activation_bits=16, activation_frac=activation_frac,
                        output_frac=node_fracs[graph['output']], weight_bits=weight_bits,
                        coefficient_bits=16, coefficient_frac=14, bias_bits=64, accumulator_bits=64,
                        rounding="half_away_from_zero", saturation="signed_clamp",
                        weight_scaling="per_output_channel_power_of_two", weight_zero_point=0,
                        activation_zero_point=0, saturation_boundary="every_node_output_except_input",
                        activation_scaling="explicit_per_node_power_of_two",
                        concat_alignment="round_each_source_to_output_frac_then_saturate_before_concat",
                        add_alignment="round_each_source_to_output_frac_int64_then_add_then_saturate",
                        coefficient_multiply="round_then_saturate_each_branch_before_add",
                        alignment_bytes=64)
    package = Path(__file__).parent
    code_hashes = {name: sha256(package / name) for name in ("export.py", "fetch.py", "integer.py", "io.py", "cli.py")
                   if (package / name).is_file()}
    identity = dict(model="GridDehazeNet", upstream=UPSTREAM, source_commit=COMMIT,
                    weight_file=WEIGHT_NAME, weight_sha256=WEIGHT_SHA256,
                    parameter_count=958051, model_arguments=MODEL_ARGUMENTS,
                    checkpoint_adapter="strip_uniform_DataParallel_module_prefix_then_strict_load",
                    scale_config_sha256=scales_sha256,
                    status="a_group_proposal_b_abi_and_visual_acceptance_pending")
    identity["bundle_id"] = hashlib.sha256(canonical_json(dict(identity=identity,
        quantization=quantization, code_hashes=code_hashes, graph_sha256=hashlib.sha256(graph_bytes).hexdigest(),
        blob_sha256=hashlib.sha256(payload).hexdigest()))).hexdigest()
    manifest = dict(format_version=FORMAT_VERSION, identity=identity, quantization=quantization,
                    source_files=sources, export_code_hashes=code_hashes,
                    calibration=calibration,
                    scale_config_file='scale_config.json' if calibration is not None else None,
                    scale_config_sha256=scales_sha256,
                    parameters=parameters, graph_file="graph.json", blob_file="parameters.bin",
                    graph_sha256=hashlib.sha256(graph_bytes).hexdigest(), blob_sha256=hashlib.sha256(payload).hexdigest(),
                    blob_nbytes=len(payload), overflow_proof=bounds,
                    environment=dict(python=sys.version.split()[0], numpy=np.__version__, torch=torch.__version__),
                    license=dict(status="no_license_file_in_pinned_upstream_tree", redistribution_permission="not_established"))
    # Exclusive opens: never replace prior numerical evidence.
    contents = [canonical_json(manifest), graph_bytes, payload]
    if calibration is not None:
        contents.append(raw_scales)
    for target, content in zip(targets, contents):
        with target.open("xb") as handle:
            handle.write(content)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--activation-frac", type=int, default=10)
    parser.add_argument("--weight-bits", type=int, choices=(8, 16), default=8)
    parser.add_argument("--scales", type=Path, help="Calibration JSON with exactly all DAG node_fracs")
    args = parser.parse_args()
    result = export(args.source_dir, args.out_dir, args.activation_frac, args.weight_bits, args.scales)
    print(json.dumps(dict(bundle_id=result["identity"]["bundle_id"], blob_nbytes=result["blob_nbytes"],
                          parameters=len(result["parameters"])), indent=2))
