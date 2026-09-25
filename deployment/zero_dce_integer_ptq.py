"""Integer-only inference prototype for the bundled Zero-DCE++ model.

Floating point is used only while calibrating/exporting weights, preparing
FP32 references, and computing comparison metrics. The quantized forward path
uses integer tensors for preprocessing, convolutions, Tanh lookup, bilinear
upsampling, and all eight enhancement iterations.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch import nn


HERE = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = HERE
Q15 = 1 << 15
Q14 = 1 << 14
INT16_MIN, INT16_MAX = -(1 << 15), (1 << 15) - 1
INT32_MAX = (1 << 31) - 1


def round_div(numerator, denominator):
    """Signed integer division, nearest with ties to even."""
    if isinstance(numerator, torch.Tensor):
        sign = torch.where(numerator < 0, -1, 1)
        absolute = numerator.abs()
        quotient = torch.div(absolute, denominator, rounding_mode="floor")
        remainder = absolute - quotient * denominator
        increase = (2 * remainder > denominator) | (
            (2 * remainder == denominator) & (quotient.remainder(2) == 1))
        return sign * (quotient + increase.to(quotient.dtype))
    sign = -1 if numerator < 0 else 1
    absolute = abs(int(numerator))
    quotient, remainder = divmod(absolute, int(denominator))
    return sign * (quotient + int(2 * remainder > denominator or
                                  (2 * remainder == denominator and quotient % 2 == 1)))


def rescale(value, old_frac, new_frac):
    value = value.to(torch.int64)
    difference = old_frac - new_frac
    if difference > 0:
        return round_div(value, 1 << difference)
    if difference < 0:
        return value * (1 << -difference)
    return value


def clamp_int16(value):
    return value.clamp(INT16_MIN, INT16_MAX).to(torch.int16)


def choose_frac(value_abs_max, bits=16):
    if value_abs_max <= 0:
        return 14
    return max(-8, min(24, math.floor(math.log2(((1 << (bits - 1)) - 1) /
                                             value_abs_max))))


def make_calibration_samples(reference):
    generator = torch.Generator().manual_seed(20260923)
    noise = torch.randn(reference.shape, generator=generator) * 0.025
    samples = {
        "dark_035": (reference * 0.35).clamp(0, 1),
        "very_dark_noisy": (reference * 0.15 + noise).clamp(0, 1),
        "bright_150": (reference * 1.5).clamp(0, 1),
        "low_contrast": ((reference - 0.5) * 0.55 + 0.5).clamp(0, 1),
    }
    samples["all_black"] = torch.zeros((1, 3, 144, 240), dtype=torch.float32)
    samples["all_white"] = torch.ones((1, 3, 144, 240), dtype=torch.float32)
    return samples


def collect_ranges(network, samples, predict_parameters):
    ranges = {}
    handles = []
    for name, module in network.named_modules():
        if not isinstance(module, nn.Conv2d):
            continue
        ranges[name] = {"input_abs_max": 0.0, "output_abs_max": 0.0}

        def before(_module, args, layer_name=name):
            ranges[layer_name]["input_abs_max"] = max(
                ranges[layer_name]["input_abs_max"], float(args[0].abs().max()))

        def after(_module, _args, result, layer_name=name):
            ranges[layer_name]["output_abs_max"] = max(
                ranges[layer_name]["output_abs_max"], float(result.abs().max()))

        handles.append(module.register_forward_pre_hook(before))
        handles.append(module.register_forward_hook(after))
    try:
        with torch.inference_mode():
            for sample in samples.values():
                predict_parameters(network, sample)
    finally:
        for handle in handles:
            handle.remove()
    return ranges


def quantize_weights(network, ranges):
    arrays, config = {}, {}
    for name, module in network.named_modules():
        if not isinstance(module, nn.Conv2d):
            continue
        input_frac = choose_frac(ranges[name]["input_abs_max"])
        output_frac = choose_frac(ranges[name]["output_abs_max"])
        weight = module.weight.detach().cpu()
        bias = module.bias.detach().cpu()
        weight_fracs = []
        weight_q = torch.empty_like(weight, dtype=torch.int8)
        bias_q = torch.empty_like(bias, dtype=torch.int32)
        mac_bounds = []
        for channel in range(weight.shape[0]):
            weight_frac = min(16, choose_frac(float(weight[channel].abs().max()), bits=8))
            while True:
                q = torch.round(weight[channel].to(torch.float64) * (2.0 ** weight_frac))
                q = q.clamp(-127, 127).to(torch.int8)
                qbias = round(float(bias[channel]) * (2.0 ** (input_frac + weight_frac)))
                mac_bound = 32768 * int(q.to(torch.int64).abs().sum())
                if abs(qbias) + mac_bound <= INT32_MAX:
                    break
                weight_frac -= 1
                if weight_frac < -32:
                    raise OverflowError("cannot represent bias/accumulator in INT32")
            weight_q[channel] = q
            bias_q[channel] = qbias
            weight_fracs.append(weight_frac)
            mac_bounds.append(mac_bound + abs(qbias))

        arrays[name + ".weight_int8"] = weight_q.numpy()
        arrays[name + ".bias_int32"] = bias_q.numpy()
        config[name] = {
            "input_frac": input_frac, "output_frac": output_frac,
            "weight_frac_per_output_channel": weight_fracs,
            "weight_shape_oihw": list(weight.shape), "groups": module.groups,
            "kernel_size": list(module.kernel_size), "stride": list(module.stride),
            "padding": list(module.padding),
            "int32_accumulator_worst_case_bound": max(mac_bounds),
            "calibration_input_abs_max": ranges[name]["input_abs_max"],
            "calibration_output_abs_max": ranges[name]["output_abs_max"],
        }
    return arrays, config


def conv_integer(x, input_frac, name, arrays, config):
    spec = config[name]
    x = clamp_int16(rescale(x, input_frac, spec["input_frac"]))
    weight = torch.from_numpy(arrays[name + ".weight_int8"]).to(torch.int64)
    bias = torch.from_numpy(arrays[name + ".bias_int32"]).to(torch.int64)
    kh, kw = spec["kernel_size"]
    ph, pw = spec["padding"]
    sh, sw = spec["stride"]
    if (sh, sw) != (1, 1):
        raise NotImplementedError("only model stride 1 is supported")
    padded = torch.nn.functional.pad(x.to(torch.int64), (pw, pw, ph, ph))
    patches = padded.unfold(2, kh, sh).unfold(3, kw, sw)
    n, channels, oh, ow, _, _ = patches.shape
    if spec["groups"] == channels:
        # Depthwise: one 3x3 dot product per channel and output pixel.
        accum = (patches * weight[:, 0][None, :, None, None, :, :]).sum(dim=(-1, -2))
    elif spec["groups"] == 1 and (kh, kw) == (1, 1):
        # Pointwise: output channels x flattened spatial positions.
        flat = patches[..., 0, 0].reshape(n, channels, oh * ow)
        accum = torch.matmul(weight.reshape(weight.shape[0], channels), flat)
        accum = accum.reshape(n, weight.shape[0], oh, ow)
    else:
        raise NotImplementedError("only the official depthwise/pointwise layers are supported")
    accum += bias[None, :, None, None]
    peak = int(accum.abs().max())
    if peak > INT32_MAX:
        raise OverflowError("INT32 accumulator overflow in " + name)

    result = torch.empty_like(accum)
    for channel, weight_frac in enumerate(spec["weight_frac_per_output_channel"]):
        result[:, channel] = rescale(accum[:, channel],
                                     spec["input_frac"] + weight_frac,
                                     spec["output_frac"])
    clipped = int(((result < INT16_MIN) | (result > INT16_MAX)).sum())
    return clamp_int16(result), spec["output_frac"], peak, clipped, x


def integer_downsample(rgb_uint8, scale_factor):
    if scale_factor != 12:
        raise NotImplementedError("this frozen prototype supports scale_factor=12")
    h, w, _ = rgb_uint8.shape
    h -= h % scale_factor
    w -= w % scale_factor
    rgb = torch.from_numpy(rgb_uint8[:h, :w].copy()).to(torch.int64)
    # Q14 normalized input; valid range 0..16384.
    full_q14 = round_div(rgb * Q14, 255).permute(2, 0, 1).unsqueeze(0)
    # PyTorch bilinear align_corners=False at factor 1/12 samples at
    # 12*i+5.5. Each reduced pixel is exactly the average of four pixels.
    rows = torch.arange(h // 12) * 12 + 5
    cols = torch.arange(w // 12) * 12 + 5
    four = (full_q14[:, :, rows[:, None], cols[None, :]] +
            full_q14[:, :, (rows + 1)[:, None], cols[None, :]] +
            full_q14[:, :, rows[:, None], (cols + 1)[None, :]] +
            full_q14[:, :, (rows + 1)[:, None], (cols + 1)[None, :]])
    return full_q14, clamp_int16(round_div(four, 4))


def build_tanh_lut():
    values = [round(math.tanh(index / 256.0) * Q15)
              for index in range(-2048, 2049)]
    return np.asarray(np.clip(values, -32768, 32767), dtype=np.int16)


def tanh_integer(x, frac, lookup):
    q8 = rescale(x, frac, 8).clamp(-2048, 2048)
    return torch.from_numpy(lookup[(q8 + 2048).numpy()]).to(torch.int16)


def upsample_align_corners(parameter_low_q14, output_h, output_w):
    """Separable bilinear interpolation of signed Q14 parameters."""
    _, _, input_h, input_w = parameter_low_q14.shape
    if input_h < 2 or input_w < 2:
        raise ValueError("parameter map must be at least 2x2")
    x_num = torch.arange(output_w, dtype=torch.int64) * (input_w - 1)
    x_den = output_w - 1
    x0 = torch.div(x_num, x_den, rounding_mode="floor")
    xr = x_num - x0 * x_den
    x1 = (x0 + 1).clamp(max=input_w - 1)
    low = parameter_low_q14.to(torch.int64)
    horizontal = round_div(low[:, :, :, x0] * (x_den - xr) +
                           low[:, :, :, x1] * xr, x_den)

    y_num = torch.arange(output_h, dtype=torch.int64) * (input_h - 1)
    y_den = output_h - 1
    y0 = torch.div(y_num, y_den, rounding_mode="floor")
    yr = y_num - y0 * y_den
    y1 = (y0 + 1).clamp(max=input_h - 1)
    output = round_div(horizontal[:, :, y0, :] * (y_den - yr)[None, None, :, None] +
                       horizontal[:, :, y1, :] * yr[None, None, :, None], y_den)
    return clamp_int16(output)


def enhance_integer(image_q14, parameter_q14):
    current = rescale(image_q14, 14, 15).to(torch.int64)
    parameter = rescale(parameter_q14, 14, 15).to(torch.int64)
    iterations = []
    for _ in range(8):
        squared = round_div(current * current, Q15)
        delta = round_div(parameter * (squared - current), Q15)
        current = (current + delta).clamp(0, Q15)
        iterations.append(current.to(torch.int32))
    return current.to(torch.int32), iterations


def run_integer(rgb_uint8, arrays, config, tanh_lut):
    original, x = integer_downsample(rgb_uint8, 12)
    frac = 14
    features = {}
    nodes, peaks, clips = {"input_downsampled": (x, frac)}, {}, {}
    for index in range(1, 8):
        block = "e_conv" + str(index)
        if index == 1:
            block_input, block_frac = x, frac
        elif index <= 4:
            block_input, block_frac = features[index - 1]
        else:
            left, right = {5: (3, 4), 6: (2, 5), 7: (1, 6)}[index]
            target_frac = config[block + ".depth_conv"]["input_frac"]
            a = clamp_int16(rescale(features[left][0], features[left][1], target_frac))
            b = clamp_int16(rescale(features[right][0], features[right][1], target_frac))
            block_input, block_frac = torch.cat([a, b], dim=1), target_frac
        for kind in ("depth_conv", "point_conv"):
            name = block + "." + kind
            block_input, block_frac, peak, clipped, quantized_input = conv_integer(
                block_input, block_frac, name, arrays, config)
            nodes[name + ".input"] = (quantized_input, config[name]["input_frac"])
            nodes[name] = (block_input, block_frac)
            peaks[name], clips[name] = peak, clipped
        if index < 7:
            block_input = block_input.clamp(min=0)
            features[index] = (block_input, block_frac)
    parameter_low_q15 = tanh_integer(block_input, block_frac, tanh_lut)
    parameter_low = clamp_int16(rescale(parameter_low_q15, 15, 14))
    nodes["parameters_lowres"] = (parameter_low, 14)
    parameter_full = upsample_align_corners(parameter_low, original.shape[2], original.shape[3])
    nodes["parameters_fullres"] = (parameter_full, 14)
    enhanced, iterations = enhance_integer(original, parameter_full)
    for index, value in enumerate(iterations, 1):
        nodes["enhancement_iter_{:02d}".format(index)] = (value, 15)
    nodes["enhanced"] = (enhanced, 15)
    png = round_div(enhanced.to(torch.int64) * 255, Q15).clamp(0, 255).to(torch.uint8)
    return nodes, png, peaks, clips


def float_reference(network, image, downsample_input, predict_parameters,
                    resize_parameters, enhancement_steps):
    nodes, handles = {}, []
    for name, module in network.named_modules():
        if isinstance(module, nn.Conv2d):
            handles.append(module.register_forward_hook(
                lambda _module, _args, result, layer_name=name:
                nodes.__setitem__(layer_name, result.detach().clone())))
    try:
        with torch.inference_mode():
            nodes["input_downsampled"] = downsample_input(network, image)
            low = predict_parameters(network, image)
            full = resize_parameters(network, low, tuple(image.shape[-2:]))
            steps = enhancement_steps(image, full)
    finally:
        for handle in handles:
            handle.remove()
    nodes["parameters_lowres"] = low
    nodes["parameters_fullres"] = full
    for index, value in enumerate(steps, 1):
        nodes["enhancement_iter_{:02d}".format(index)] = value
    nodes["enhanced"] = steps[-1]
    return nodes


def metrics(reference, integer, frac):
    candidate = integer.to(torch.float64) / (2.0 ** frac)
    difference = (reference.to(torch.float64) - candidate).abs()
    return {"mae": float(difference.mean()), "max": float(difference.max()),
            "rmse": float(torch.sqrt(torch.mean(difference * difference)))}


def uint8_image(chw_uint8):
    array = chw_uint8[0].permute(1, 2, 0).numpy()
    return Image.fromarray(array, "RGB")


def float_png(image):
    return torch.round(image.clamp(0, 1) * 255).to(torch.uint8)


def save_comparison(path, input_png, float_output, integer_output):
    difference = (integer_output.to(torch.int16) - float_output.to(torch.int16)).abs()
    difference = (difference * 16).clamp(0, 255).to(torch.uint8)
    panels = [("Input", uint8_image(input_png)), ("FP32", uint8_image(float_output)),
              ("Integer", uint8_image(integer_output)),
              ("Difference x16", uint8_image(difference))]
    width = 480
    height = round(panels[0][1].height * width / panels[0][1].width)
    canvas = Image.new("RGB", (4 * width, height + 30), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (label, panel) in enumerate(panels):
        canvas.paste(panel.resize((width, height), Image.Resampling.LANCZOS),
                     (index * width, 30))
        draw.text((index * width + 8, 8), label, fill="black")
    canvas.save(path)


def evaluate(name, image, rgb_uint8, network, arrays, config, lookup, functions,
             output_dir, save_images=False):
    fp32 = float_reference(network, image, *functions)
    integer_nodes, integer_png, peaks, clips = run_integer(rgb_uint8, arrays, config, lookup)
    result = {"shape_nchw": list(image.shape), "nodes": {},
              "accumulator_abs_peak": peaks, "int16_clipped_values": clips}
    for node_name, (value, frac) in integer_nodes.items():
        if node_name in fp32:
            result["nodes"][node_name] = metrics(fp32[node_name], value, frac)
    fp32_png = float_png(fp32["enhanced"])
    delta = (fp32_png.to(torch.int16) - integer_png.to(torch.int16)).abs()
    result["png"] = {"mae_levels": float(delta.to(torch.float64).mean()),
                     "max_levels": int(delta.max()),
                     "changed_fraction": float((delta != 0).to(torch.float64).mean())}
    if save_images:
        uint8_image(fp32_png).save(output_dir / (name + "_fp32.png"))
        uint8_image(integer_png).save(output_dir / (name + "_integer.png"))
        input_png = torch.from_numpy(rgb_uint8.copy()).permute(2, 0, 1).unsqueeze(0)
        input_png = input_png[:, :, :image.shape[2], :image.shape[3]]
        save_comparison(output_dir / (name + "_comparison.png"),
                        input_png, fp32_png, integer_png)
        parameter_low_q14 = integer_nodes["parameters_lowres"][0].numpy()
        np.save(output_dir / (name + "_parameters_integer_q14.npy"),
                parameter_low_q14, allow_pickle=False)
        parameter_bytes = np.ascontiguousarray(parameter_low_q14, dtype="<i2").tobytes(order="C")
        parameter_file = name + "_a_low_q14_nchw_le.bin"
        (output_dir / parameter_file).write_bytes(parameter_bytes)
        (output_dir / (name + "_a_low_q14_manifest.json")).write_text(
            json.dumps({
                "shape_nchw": list(parameter_low_q14.shape),
                "channel_order": ["R", "G", "B"],
                "layout": "NCHW; C-contiguous; channel, row, column",
                "dtype": "signed int16", "fractional_bits": 14,
                "value_rule": "real_value = signed_raw / 16384",
                "conversion_from_tanh_q15": "signed nearest-even division by 2, then int16 saturation",
                "byte_order": "little-endian", "row_padding_bytes": 0,
                "binary_file": parameter_file,
                "byte_count": len(parameter_bytes),
                "sha256": hashlib.sha256(parameter_bytes).hexdigest(),
                "notes": "Golden DDR payload; CNN HLS source exposes m_axi output. Physical DDR addresses and generated control registers are assigned during integration.",
            }, indent=2) + "\n", encoding="utf-8")
        np.save(output_dir / (name + "_enhanced_integer_q15.npy"),
                integer_nodes["enhanced"][0].numpy(), allow_pickle=False)
        vectors = {}
        for node_name, (value, frac) in integer_nodes.items():
            if node_name == "input_downsampled" or node_name.startswith("e_conv") or \
                    node_name == "parameters_lowres":
                vectors[node_name] = value.numpy()
            elif node_name == "parameters_fullres" or node_name.startswith("enhancement_iter_"):
                vectors[node_name + "_top_left_16x16"] = value[:, :, :16, :16].numpy()
        np.savez_compressed(output_dir / (name + "_integer_test_vectors.npz"), **vectors)
        layer_io = {}
        manifest = {
            "schema_version": 1,
            "layout": "NCHW",
            "array_order": "C-contiguous",
            "archive": name + "_layer_io.npz",
            "weights_archive": "integer_weights.npz",
            "output_semantics": "convolution output after requantization and INT16 saturation, before ReLU",
            "layers": {},
        }
        for layer_name, spec in config.items():
            input_key = layer_name + ".input"
            output_key = layer_name + ".output"
            input_array = integer_nodes[input_key][0].numpy()
            output_array = integer_nodes[layer_name][0].numpy()
            layer_io[input_key] = input_array
            layer_io[output_key] = output_array
            manifest["layers"][layer_name] = {
                "input_key": input_key, "output_key": output_key,
                "input_shape_nchw": list(input_array.shape),
                "output_shape_nchw": list(output_array.shape),
                "input_sha256_c_bytes": hashlib.sha256(
                    input_array.tobytes(order="C")).hexdigest(),
                "output_sha256_c_bytes": hashlib.sha256(
                    output_array.tobytes(order="C")).hexdigest(),
                "input_dtype": str(input_array.dtype),
                "output_dtype": str(output_array.dtype),
                "input_frac": spec["input_frac"],
                "output_frac": spec["output_frac"],
                "input_scale": 2.0 ** -spec["input_frac"],
                "output_scale": 2.0 ** -spec["output_frac"],
                "input_zero_point": 0, "output_zero_point": 0,
                "weight_key": layer_name + ".weight_int8",
                "bias_key": layer_name + ".bias_int32",
                "weight_shape_oihw": spec["weight_shape_oihw"],
                "weight_dtype": "int8", "bias_dtype": "int32",
                "weight_frac_per_output_channel": spec["weight_frac_per_output_channel"],
                "weight_scale_per_output_channel": [
                    2.0 ** -frac for frac in spec["weight_frac_per_output_channel"]],
                "weight_zero_point": 0,
                "bias_scale_per_output_channel": [
                    2.0 ** -(spec["input_frac"] + frac)
                    for frac in spec["weight_frac_per_output_channel"]],
                "bias_zero_point": 0,
            }
        np.savez_compressed(output_dir / (name + "_layer_io.npz"), **layer_io)
        (output_dir / (name + "_layer_io_manifest.json")).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--output-dir", type=Path,
                        default=HERE / "outputs" / "zero_dce_pp" / "quantization" / "integer")
    args = parser.parse_args()
    project, output_dir = args.project_root.resolve(), args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(project))
    from model.zero_dce_pp.enhancement import (downsample_input, enhancement_steps,
                                                predict_parameters, resize_parameters)
    from model.zero_dce_pp.inference import load_model
    from model.zero_dce_pp.io_utils import sha256_file
    from model.zero_dce_pp.preprocessing import preprocess_image

    torch.set_num_threads(min(4, torch.get_num_threads()))
    image_path = project / "data" / "test" / "night_01.jpg"
    weights_path = project / "model" / "zero_dce_pp" / "weights" / "Epoch99.pth"
    network = load_model(weights_path, device="cpu", scale_factor=12)
    image = preprocess_image(image_path, scale_factor=12)
    calibration = make_calibration_samples(image)
    ranges = collect_ranges(network, calibration, predict_parameters)
    arrays, config = quantize_weights(network, ranges)
    lookup = build_tanh_lut()
    np.savez_compressed(output_dir / "integer_weights.npz", **arrays)
    np.save(output_dir / "tanh_q15_lut.npy", lookup, allow_pickle=False)
    (project / "configs" / "zero_dce_pp_integer_rules.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8")

    rgb = np.asarray(Image.open(image_path).convert("RGB"))
    functions = (downsample_input, predict_parameters, resize_parameters,
                 enhancement_steps)
    results = {"original_image": evaluate(
        "night_01", image, rgb, network, arrays, config, lookup, functions,
        output_dir, save_images=True)}
    # These are deterministic stress checks, not independent real-world images.
    for label, sample in calibration.items():
        if label in ("all_black", "all_white"):
            continue
        sample_rgb = float_png(sample)[0].permute(1, 2, 0).numpy()
        decoded = torch.from_numpy(sample_rgb.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255
        results[label] = evaluate(label, decoded, sample_rgb, network, arrays,
                                  config, lookup, functions, output_dir)
    for label, intensity in (("all_black", 0), ("all_white", 255)):
        sample_rgb = np.full((144, 240, 3), intensity, dtype=np.uint8)
        decoded = torch.from_numpy(sample_rgb.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255
        results[label] = evaluate(label, decoded, sample_rgb, network, arrays,
                                  config, lookup, functions, output_dir)

    recorded_reference_error = {}
    recorded_dir = project / "outputs" / "zero_dce_pp" / "reference"
    original_fp32 = float_reference(network, image, *functions)
    for node in ("parameters_lowres", "parameters_fullres", "enhanced"):
        recorded_path = recorded_dir / (node + ".npy")
        if recorded_path.is_file():
            recorded = np.load(recorded_path, allow_pickle=False)
            expected = original_fp32[node].numpy()
            recorded_reference_error[node] = float(np.max(np.abs(recorded - expected)))

    report = {
        "scope": "full integer forward prototype, not an FPGA implementation",
        "model": "Zero-DCE++ Epoch99.pth", "weights_sha256": sha256_file(weights_path),
        "pytorch_version": torch.__version__,
        "calibration": "four deterministic transforms of night_01.jpg plus all-black/all-white edge inputs; no independent dataset",
        "evaluation": "original night_01.jpg, same-source transforms, all-black/all-white synthetic edges",
        "precision": "INT16 activations, INT8 weights, INT32 bias/MAC; Q14 A_low and bilinear, Q15 curve image",
        "rounding": "nearest, ties to even; saturate INT16 after each convolution",
        "lut_entries": len(lookup), "results": results,
        "recorded_fp32_reference_max_error": recorded_reference_error,
        "limitations": [
            "The original evaluation image shares a source with all calibration variants.",
            "The image collection is insufficient for a production quality decision.",
            "This is a CPU integer simulation; HLS source has a native C++ golden check, while Vitis HLS simulation, synthesis, board output and timing remain undone.",
            "The separate HLS package exporter defines raw little-endian model arrays and the m_axi pointer contract; physical DDR address mapping remains an integration task.",
        ],
    }
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {name: {"parameter_mae": result["nodes"]["parameters_lowres"]["mae"],
                      "enhanced_mae": result["nodes"]["enhanced"]["mae"],
                      "png_mae": result["png"]["mae_levels"],
                      "png_max": result["png"]["max_levels"],
                      "clipped": sum(result["int16_clipped_values"].values())}
               for name, result in results.items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
