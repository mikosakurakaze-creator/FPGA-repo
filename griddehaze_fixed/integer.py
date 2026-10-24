"""Exact, CPU-only integer execution of the exported GridDehazeNet DAG.

The public boundary is contiguous NCHW, batch one, signed int16.  There are no
floating-point operations in either execution backend.  ``numpy`` uses windowed
integer matrix products; ``direct`` uses SciPy's direct integer correlation and
an independent transposed-convolution scatter implementation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np

FORMAT_VERSION = "griddehaze-fixed-v1"
I64_MAX = (1 << 63) - 1
I16_MIN, I16_MAX = -(1 << 15), (1 << 15) - 1
DTYPES = {"int8": np.dtype("i1"), "int16": np.dtype("<i2"), "int64": np.dtype("<i8")}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pair(value, name: str) -> tuple[int, int]:
    values = (value, value) if isinstance(value, int) else tuple(value)
    if len(values) != 2 or any(type(v) is not int for v in values):
        raise ValueError(f"{name} must be an integer or two integers")
    return values


def _as_integer(values) -> np.ndarray:
    array = np.asarray(values)
    if array.dtype.kind != "i":
        raise ValueError("integer arithmetic requires signed integer arrays")
    return array.astype(np.int64, copy=False)


def round_shift(values: np.ndarray, shift: int) -> np.ndarray:
    """Divide by 2**shift, round ties away from zero, without INT64 overflow.

    Negative shifts are checked integer left shifts.  Decomposing quotient and
    remainder avoids ``abs(INT64_MIN)`` and overflow from adding a rounding bias.
    """
    values = _as_integer(values)
    if not isinstance(shift, (int, np.integer)) or not -62 <= int(shift) <= 62:
        raise ValueError("shift must be an integer in [-62, 62]")
    shift = int(shift)
    if shift == 0:
        return values.copy()
    if shift < 0:
        multiplier = 1 << -shift
        lo = -((1 << 63) // multiplier)
        hi = I64_MAX // multiplier
        if values.size and (int(values.min()) < lo or int(values.max()) > hi):
            raise OverflowError("INT64 overflow in left shift")
        return values * np.int64(multiplier)
    quotient = values >> shift
    remainder = values & np.int64((1 << shift) - 1)
    half = np.int64(1 << (shift - 1))
    increment = (remainder > half) | ((remainder == half) & (values >= 0))
    return quotient + increment.astype(np.int64)


def _saturate(values: np.ndarray) -> tuple[np.ndarray, dict]:
    values = _as_integer(values)
    low = int(np.count_nonzero(values < I16_MIN))
    high = int(np.count_nonzero(values > I16_MAX))
    result = np.clip(values, I16_MIN, I16_MAX).astype(np.int16)
    return result, {"saturated_low": low, "saturated_high": high}


def requantize(values: np.ndarray, shifts) -> tuple[np.ndarray, dict]:
    """Requantize a CHW accumulator with a shift per output channel."""
    values = _as_integer(values)
    if values.ndim != 3:
        raise ValueError("requantization expects a CHW accumulator")
    shifts = [int(shifts)] * values.shape[0] if isinstance(shifts, (int, np.integer)) else list(shifts)
    if len(shifts) != values.shape[0]:
        raise ValueError("one weight fractional-bit count is required per output channel")
    rounded = np.empty_like(values)
    for channel, shift in enumerate(shifts):
        rounded[channel] = round_shift(values[channel], shift)
    return _saturate(rounded)


def _conv_arguments(x, weight, bias, stride, padding, dilation, transpose=False):
    x, weight, bias = _as_integer(x), _as_integer(weight), _as_integer(bias)
    stride, padding, dilation = (_pair(v, n) for v, n in ((stride, "stride"), (padding, "padding"), (dilation, "dilation")))
    if x.ndim != 3 or weight.ndim != 4 or bias.ndim != 1 or any(v <= 0 for v in x.shape + weight.shape):
        raise ValueError("convolution expects nonempty CHW, OIHW/IOHW and O arrays")
    if any(v < 1 for v in stride + dilation) or any(v < 0 for v in padding):
        raise ValueError("stride/dilation must be positive and padding nonnegative")
    cin, cout = (weight.shape[0], weight.shape[1]) if transpose else (weight.shape[1], weight.shape[0])
    if cin != x.shape[0] or cout != bias.size:
        raise ValueError("convolution channel/bias shape mismatch")
    # Proof applies also to every partial sum and prevents silent NumPy wrap.
    max_input = max(-int(x.min()), int(x.max()))
    for channel in range(cout):
        kernel = weight[:, channel] if transpose else weight[channel]
        kernel_l1 = sum(abs(int(v)) for v in kernel.flat)
        bound = max_input * kernel_l1 + abs(int(bias[channel]))
        if bound > I64_MAX:
            raise OverflowError("convolution accumulator cannot be proved safe in INT64")
    return x, weight, bias, stride, padding, dilation


def conv2d_accumulate(x, weight, bias, stride=(1, 1), padding=(0, 0), dilation=(1, 1), backend="numpy"):
    """Exact CHW cross correlation; weight layout OIHW; result is INT64."""
    x, weight, bias, stride, padding, dilation = _conv_arguments(x, weight, bias, stride, padding, dilation)
    kh, kw = weight.shape[-2:]
    eh, ew = (kh - 1) * dilation[0] + 1, (kw - 1) * dilation[1] + 1
    padded = np.pad(x, ((0, 0), (padding[0], padding[0]), (padding[1], padding[1])))
    oh = (padded.shape[1] - eh) // stride[0] + 1
    ow = (padded.shape[2] - ew) // stride[1] + 1
    if min(oh, ow) <= 0:
        raise ValueError("convolution kernel exceeds padded input")
    result = np.empty((weight.shape[0], oh, ow), dtype=np.int64)
    if backend == "numpy":
        windows = np.lib.stride_tricks.sliding_window_view(padded, (eh, ew), axis=(1, 2))
        windows = windows[:, ::stride[0], ::stride[1], ::dilation[0], ::dilation[1]]
        # Row chunks avoid constructing a full-resolution im2col tensor.
        rows_per_chunk = max(1, 262144 // max(1, ow * x.shape[0] * kh * kw))
        flat_weights = weight.reshape(weight.shape[0], -1)
        for row in range(0, oh, rows_per_chunk):
            stop = min(oh, row + rows_per_chunk)
            matrix = windows[:, row:stop].transpose(1, 2, 0, 3, 4).reshape(-1, flat_weights.shape[1])
            result[:, row:stop] = (matrix @ flat_weights.T).T.reshape(weight.shape[0], stop - row, ow)
    elif backend == "direct":
        from scipy.signal import correlate
        result.fill(0)
        for co in range(weight.shape[0]):
            for ci in range(x.shape[0]):
                kernel = np.zeros((eh, ew), dtype=np.int64)
                kernel[::dilation[0], ::dilation[1]] = weight[co, ci]
                result[co] += correlate(padded[ci], kernel, mode="valid", method="direct")[::stride[0], ::stride[1]]
    else:
        raise ValueError(f"unknown integer backend {backend!r}")
    result += bias[:, None, None]
    return result


def deconv2d_accumulate(x, weight, bias, stride=(1, 1), padding=(0, 0), dilation=(1, 1), output_shape=None, backend="numpy"):
    """Exact transposed convolution; native PyTorch IOHW weights.

    ``output_shape`` supplies the official graph's dynamic output_size.  Each
    requested dimension must be between the minimum size and minimum+stride-1.
    """
    x, weight, bias, stride, padding, dilation = _conv_arguments(x, weight, bias, stride, padding, dilation, True)
    kh, kw = weight.shape[-2:]
    minimum = tuple((x.shape[1 + d] - 1) * stride[d] - 2 * padding[d] + dilation[d] * (weight.shape[2 + d] - 1) + 1 for d in range(2))
    target = minimum if output_shape is None else tuple(int(v) for v in output_shape[-2:])
    if len(target) != 2 or min(target) <= 0 or any(not minimum[d] <= target[d] < minimum[d] + stride[d] for d in range(2)):
        raise ValueError(f"invalid transposed-convolution output size {target}; minimum={minimum}, stride={stride}")
    result = np.zeros((weight.shape[1],) + target, dtype=np.int64)
    if backend not in ("numpy", "direct"):
        raise ValueError(f"unknown integer backend {backend!r}")
    # Scatter each kernel tap.  The direct implementation explicitly loops over
    # input/output channels and spatial samples, independent of matrix products.
    for ky in range(kh):
        y_positions = np.arange(x.shape[1]) * stride[0] - padding[0] + ky * dilation[0]
        ys = np.flatnonzero((y_positions >= 0) & (y_positions < target[0]))
        if not ys.size:
            continue
        dy = y_positions[ys]
        for kx in range(kw):
            x_positions = np.arange(x.shape[2]) * stride[1] - padding[1] + kx * dilation[1]
            xs = np.flatnonzero((x_positions >= 0) & (x_positions < target[1]))
            if not xs.size:
                continue
            dx = x_positions[xs]
            source = x[:, ys[:, None], xs[None, :]]
            if backend == "numpy":
                contribution = weight[:, :, ky, kx].T @ source.reshape(x.shape[0], -1)
                result[:, dy[:, None], dx[None, :]] += contribution.reshape(weight.shape[1], ys.size, xs.size)
            else:
                for co in range(weight.shape[1]):
                    tile = np.zeros((ys.size, xs.size), dtype=np.int64)
                    for ci in range(x.shape[0]):
                        tile += source[ci] * weight[ci, co, ky, kx]
                    result[co, dy[:, None], dx[None, :]] += tile
    result += bias[:, None, None]
    return result


def _safe_member(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()) or path == directory.resolve():
        raise ValueError("manifest path escapes the delivery directory")
    return path


def load_package(directory: str | Path) -> tuple[dict, dict, dict[str, np.ndarray]]:
    """Load and verify graph, aligned binary tensors and producer identities."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported fixed-point package format/version")
    from .fetch import COMMIT, WEIGHT_SHA256
    identity = manifest.get("identity", {})
    if identity.get("model") != "GridDehazeNet" or identity.get("source_commit") != COMMIT or identity.get("weight_sha256") != WEIGHT_SHA256:
        raise ValueError("model/source/weight identity differs from the pinned task version")
    identity_without_id = {k: v for k, v in identity.items() if k != "bundle_id"}
    identity_payload = dict(identity=identity_without_id, quantization=manifest.get("quantization"),
                            code_hashes=manifest.get("export_code_hashes"), graph_sha256=manifest.get("graph_sha256"),
                            blob_sha256=manifest.get("blob_sha256"))
    canonical = (json.dumps(identity_payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != identity.get("bundle_id"):
        raise ValueError("bundle identity mismatch: configuration, code, graph or parameter identity changed")
    quant = manifest.get("quantization", {})
    expected = {"activation_bits": 16, "accumulator_bits": 64, "rounding": "half_away_from_zero", "saturation": "signed_clamp"}
    for key, value in expected.items():
        if quant.get(key) != value:
            raise ValueError(f"unsupported quantization {key}: {quant.get(key)!r}")
    if type(quant.get("activation_frac")) is not int or not 0 <= quant["activation_frac"] <= 15:
        raise ValueError("invalid activation fractional-bit count")
    if quant.get("weight_bits") not in (8, 16) or quant.get("coefficient_bits") != 16:
        raise ValueError("unsupported parameter bit widths")
    if type(quant.get("coefficient_frac")) is not int or not 0 <= quant["coefficient_frac"] <= 30:
        raise ValueError("invalid coefficient fractional-bit count")
    graph_path = _safe_member(directory, manifest.get("graph_file", "graph.json"))
    blob_path = _safe_member(directory, manifest.get("blob_file", "parameters.bin"))
    for path, field in ((graph_path, "graph_sha256"), (blob_path, "blob_sha256")):
        if sha256(path) != manifest.get(field):
            raise ValueError(f"SHA-256 mismatch: {path.name}")
    code_hashes = manifest.get("export_code_hashes", {})
    if not {"export.py", "fetch.py", "integer.py"}.issubset(code_hashes):
        raise ValueError("producer code identities are incomplete")
    for basename, expected_sha in code_hashes.items():
        if Path(basename).name != basename:
            raise ValueError("invalid producer code basename")
        producer_path = Path(__file__).with_name(basename)
        if not producer_path.is_file() or sha256(producer_path) != expected_sha:
            raise ValueError(f"producer code identity mismatch: {basename}")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if manifest.get("scale_config_file") is not None:
        scale_path = _safe_member(directory, manifest["scale_config_file"])
        if sha256(scale_path) != manifest.get("scale_config_sha256") or manifest.get("scale_config_sha256") != identity.get("scale_config_sha256"):
            raise ValueError("calibration scale configuration SHA-256 mismatch")
        calibration = json.loads(scale_path.read_text(encoding="utf-8"))
        if calibration != manifest.get("calibration"):
            raise ValueError("embedded calibration differs from the original configuration")
        graph_fracs = {node["id"]: node.get("activation_frac", quant["activation_frac"]) for node in graph.get("nodes", [])}
        if calibration.get("node_fracs") != graph_fracs:
            raise ValueError("calibration/graph activation scale mismatch")
    blob = blob_path.read_bytes()
    if manifest.get("blob_nbytes") != len(blob):
        raise ValueError("parameter blob byte count mismatch")
    tensors, spans = {}, []
    for parameter in manifest.get("parameters", []):
        name, dtype = parameter.get("name"), DTYPES.get(parameter.get("dtype"))
        shape = parameter.get("shape")
        if not isinstance(name, str) or not name or name in tensors or dtype is None:
            raise ValueError("duplicate/invalid parameter name or dtype")
        if not isinstance(shape, list) or not shape or any(type(v) is not int or v < 1 for v in shape):
            raise ValueError(f"invalid parameter shape: {name}")
        offset, nbytes = parameter.get("offset"), parameter.get("nbytes")
        required = int(np.prod(shape, dtype=object)) * dtype.itemsize
        if type(offset) is not int or type(nbytes) is not int or offset < 0 or offset % 64 or nbytes != required or offset + nbytes > len(blob):
            raise ValueError(f"invalid parameter bounds/alignment: {name}")
        payload = blob[offset:offset + nbytes]
        if hashlib.sha256(payload).hexdigest() != parameter.get("sha256"):
            raise ValueError(f"parameter SHA-256 mismatch: {name}")
        spans.append((offset, offset + nbytes, name))
        tensor = np.frombuffer(payload, dtype=dtype).reshape(shape)
        tensor.flags.writeable = False
        tensors[name] = tensor
    for before, after in zip(sorted(spans), sorted(spans)[1:]):
        if before[1] > after[0]:
            raise ValueError(f"overlapping parameters: {before[2]}, {after[2]}")
    _validate_graph(graph, tensors, quant)
    descriptors = {p["name"]: p for p in manifest["parameters"]}
    activation_fracs = {node["id"]: node.get("activation_frac", quant["activation_frac"]) for node in graph["nodes"]}
    for node in graph["nodes"]:
        if node["op"] in {"conv", "deconv"}:
            weight, bias = descriptors[node["weight"]], descriptors[node["bias"]]
            expected_layout = "IOHW" if node["op"] == "deconv" else "OIHW"
            if weight.get("layout") != expected_layout or bias.get("layout") != "O":
                raise ValueError(f"parameter layout mismatch: {node['id']}")
            input_frac = activation_fracs[node["inputs"][0]]
            if weight.get("frac") != node["weight_frac"] or bias.get("frac") != [input_frac + f for f in node["weight_frac"]]:
                raise ValueError(f"parameter/graph scale mismatch: {node['id']}")
            shifts = [input_frac + f - activation_fracs[node["id"]] for f in node["weight_frac"]]
            if "requantization_shift" in node and node["requantization_shift"] != shifts:
                raise ValueError(f"recorded requantization shift mismatch: {node['id']}")
        elif node["op"] == "mulcoef":
            coefficient = descriptors[node["coefficient"]]
            if coefficient.get("layout") != "C" or coefficient.get("frac") != node["coefficient_frac"]:
                raise ValueError(f"coefficient layout/scale mismatch: {node['id']}")
    return manifest, graph, tensors


def _validate_graph(graph, tensors, quant):
    nodes = graph.get("nodes")
    if graph.get("format_version") != FORMAT_VERSION or not isinstance(nodes, list) or not nodes or graph.get("input") != "input":
        raise ValueError("invalid graph nodes/input")
    seen = set()
    counts = {"input": 0}
    for node in nodes:
        ident, op, inputs = node.get("id"), node.get("op"), node.get("inputs", [])
        if not isinstance(ident, str) or ident in seen or op not in {"input", "conv", "deconv", "relu", "cat", "add", "mulcoef"}:
            raise ValueError("invalid/duplicate graph id or unknown operation")
        if not isinstance(inputs, list) or any(v not in seen for v in inputs):
            raise ValueError(f"graph is not topologically ordered: {ident}")
        activation_frac = node.get("activation_frac", quant["activation_frac"])
        if type(activation_frac) is not int or not 0 <= activation_frac <= 14:
            raise ValueError(f"invalid per-node activation fractional bits: {ident}")
        if op == "input":
            counts["input"] += 1
            if ident != "input" or inputs:
                raise ValueError("invalid input node")
            if activation_frac != quant["activation_frac"]:
                raise ValueError("input node fractional bits must match the preprocessing scale")
        elif op in {"conv", "deconv"}:
            if len(inputs) != 1 or node.get("weight") not in tensors or node.get("bias") not in tensors:
                raise ValueError(f"missing convolution inputs/parameters: {ident}")
            weight, bias = tensors[node["weight"]], tensors[node["bias"]]
            if node.get("groups", 1) != 1:
                raise ValueError(f"grouped convolution is unsupported: {ident}")
            axis = 1 if op == "deconv" else 0
            shifts = node.get("weight_frac")
            if weight.ndim != 4 or weight.dtype.itemsize != quant["weight_bits"] // 8 or bias.dtype.itemsize != 8 or bias.shape != (weight.shape[axis],):
                raise ValueError(f"invalid convolution tensor shape/type: {ident}")
            if not isinstance(shifts, list) or len(shifts) != weight.shape[axis] or any(type(v) is not int or not -30 <= v <= 62 for v in shifts):
                raise ValueError(f"invalid weight fractional bits: {ident}")
            if op == "deconv" and node.get("output_like") not in seen:
                raise ValueError(f"missing transposed-convolution output reference: {ident}")
        elif op == "mulcoef":
            if len(inputs) != 1 or node.get("coefficient") not in tensors or tensors[node["coefficient"]].dtype.itemsize != 2:
                raise ValueError(f"invalid coefficient: {ident}")
            if node.get("coefficient_frac") != quant["coefficient_frac"]:
                raise ValueError(f"inconsistent coefficient fractional bits: {ident}")
        elif op in {"relu"} and len(inputs) != 1:
            raise ValueError(f"invalid unary input count: {ident}")
        elif op in {"add", "cat"} and len(inputs) != 2:
            raise ValueError(f"invalid binary input count: {ident}")
        if op == "cat" and node.get("axis", 1) != 1:
            raise ValueError(f"only NCHW channel concatenation is supported: {ident}")
        seen.add(ident)
    if counts["input"] != 1 or graph.get("output") not in seen:
        raise ValueError("invalid graph output/input count")
    output_node = next(node for node in nodes if node["id"] == graph["output"])
    output_frac = output_node.get("activation_frac", quant["activation_frac"])
    if "output_frac" in quant and quant["output_frac"] != output_frac:
        raise ValueError("output node fractional bits differ from the display/output scale")


def run(manifest_dir: str | Path, input_array: np.ndarray, backend: str = "numpy", observer: Callable | None = None) -> np.ndarray:
    """Execute a verified package and return signed INT16 NCHW, batch one.

    ``observer(node_id, array_nchw, statistics)`` is called for every node,
    including the input.  Arrays passed to it are read-only views.  ``direct``
    deliberately uses a separate operator implementation for cross checking.
    Every tensor's real value is its signed integer times 2**(-activation_frac),
    taken from that node or the legacy uniform manifest default.  Addition
    rescales both operands in INT64, then clamps only the final sum; concatenation
    rescales and clamps each operand before joining channels.
    """
    if backend not in {"numpy", "direct"}:
        raise ValueError("backend must be 'numpy' or 'direct'")
    array = np.asarray(input_array)
    if array.dtype != np.dtype(np.int16) or array.ndim != 4 or array.shape[0] != 1 or array.shape[1] != 3:
        raise ValueError("input must be signed INT16 NCHW with N=1, C=3")
    if min(array.shape[-2:]) < 4:
        raise ValueError("GridDehazeNet requires input height and width >= 4")
    if not array.flags.c_contiguous:
        raise ValueError("input must be C-contiguous NCHW")
    manifest, graph, parameters = load_package(manifest_dir)
    values, all_stats = {}, {}
    activation_fracs = {node["id"]: node.get("activation_frac", manifest["quantization"]["activation_frac"]) for node in graph["nodes"]}
    # Count remaining consumers so large feature maps can be released. Dynamic
    # deconvolution shape references also keep their source tensor alive.
    uses = {node["id"]: 0 for node in graph["nodes"]}
    for node in graph["nodes"]:
        for source in node.get("inputs", []) + ([node["output_like"]] if node.get("output_like") else []):
            uses[source] += 1
    uses[graph["output"]] += 1
    for node in graph["nodes"]:
        ident, op = node["id"], node["op"]
        sources = [values[name] for name in node.get("inputs", [])]
        output_frac = activation_fracs[ident]
        input_fracs = [activation_fracs[name] for name in node.get("inputs", [])]
        saturation = {"saturated_low": 0, "saturated_high": 0}
        if op == "input":
            result = array[0].copy()
        elif op in {"conv", "deconv"}:
            arguments = dict(stride=node.get("stride", [1, 1]), padding=node.get("padding", [0, 0]), dilation=node.get("dilation", [1, 1]), backend=backend)
            if op == "deconv":
                arguments["output_shape"] = values[node["output_like"]].shape[-2:]
            operator = deconv2d_accumulate if op == "deconv" else conv2d_accumulate
            accumulator = operator(sources[0], parameters[node["weight"]], parameters[node["bias"]], **arguments)
            shifts = [input_fracs[0] + f - output_frac for f in node["weight_frac"]]
            result, saturation = requantize(accumulator, shifts)
        elif op == "relu":
            aligned = round_shift(sources[0], input_fracs[0] - output_frac)
            result, saturation = _saturate(np.maximum(aligned, 0))
        elif op == "cat":
            if sources[0].shape[1:] != sources[1].shape[1:]:
                raise ValueError(f"concat spatial mismatch: {ident}")
            aligned = []
            for source, frac in zip(sources, input_fracs):
                value, stats = _saturate(round_shift(source, frac - output_frac))
                aligned.append(value)
                saturation = {key: saturation[key] + stats[key] for key in saturation}
            result = np.concatenate(aligned, axis=0)
        elif op == "add":
            if sources[0].shape != sources[1].shape:
                raise ValueError(f"add shape mismatch: {ident}")
            left = round_shift(sources[0], input_fracs[0] - output_frac)
            right = round_shift(sources[1], input_fracs[1] - output_frac)
            # Node fractional bits are restricted to [0,14], so each aligned
            # INT16 operand is <=2**29 in magnitude and their sum fits INT64.
            result, saturation = _saturate(left + right)
        elif op == "mulcoef":
            coefficient = parameters[node["coefficient"]]
            if coefficient.shape != (sources[0].shape[0],):
                raise ValueError(f"coefficient channel mismatch: {ident}")
            product = sources[0].astype(np.int64) * coefficient.astype(np.int64)[:, None, None]
            shift = input_fracs[0] + node["coefficient_frac"] - output_frac
            result, saturation = _saturate(round_shift(product, shift))
        else:
            raise ValueError(f"unsupported operation: {op}")
        values[ident] = result
        statistics = {"op": op, "activation_frac": output_frac, "shape": [1] + list(result.shape), "elements": int(result.size), "min": int(result.min()), "max": int(result.max()), **saturation}
        all_stats[ident] = statistics
        if observer is not None:
            view = result[None].view()
            view.flags.writeable = False
            observer(ident, view, statistics)
        for source in node.get("inputs", []) + ([node["output_like"]] if node.get("output_like") else []):
            uses[source] -= 1
            if uses[source] == 0:
                del values[source]
    return np.ascontiguousarray(values[graph["output"]][None])
