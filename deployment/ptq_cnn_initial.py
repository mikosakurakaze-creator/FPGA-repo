"""Reproducible, single-image INT8 PTQ experiment for Zero-DCE++'s CNN.

Only the seven parameter-prediction blocks are quantized. Downsampling,
Tanh, parameter upsampling, and the eight enhancement rounds remain FP32.
The convolution simulation uses INT32 products/accumulation in PyTorch; it
is a numerical prototype, not an optimized deployment kernel.
"""

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from torch import nn


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = ROOT
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def activation_qparams(minimum, maximum):
    minimum = min(0.0, float(minimum))
    maximum = max(0.0, float(maximum))
    scale = (maximum - minimum) / 255.0 if maximum > minimum else 1.0 / 255.0
    zero_point = int(max(0, min(255, round(-minimum / scale))))
    return {"min": minimum, "max": maximum, "scale": scale, "zero_point": zero_point}


def quantize_uint8(tensor, params):
    return torch.clamp(
        torch.round(tensor / params["scale"] + params["zero_point"]), 0, 255
    ).to(torch.uint8)


def collect_ranges(network, calibration_paths, preprocess_image, predict_parameters, scale_factor):
    ranges = {}
    handles = []
    for name, module in network.named_modules():
        if not isinstance(module, nn.Conv2d):
            continue
        ranges[name] = {"input_min": math.inf, "input_max": -math.inf,
                        "output_min": math.inf, "output_max": -math.inf}

        def pre_hook(_module, args, layer_name=name):
            value = args[0]
            record = ranges[layer_name]
            record["input_min"] = min(record["input_min"], float(value.min()))
            record["input_max"] = max(record["input_max"], float(value.max()))

        def post_hook(_module, _args, result, layer_name=name):
            record = ranges[layer_name]
            record["output_min"] = min(record["output_min"], float(result.min()))
            record["output_max"] = max(record["output_max"], float(result.max()))

        handles.append(module.register_forward_pre_hook(pre_hook))
        handles.append(module.register_forward_hook(post_hook))

    try:
        with torch.inference_mode():
            for path in calibration_paths:
                predict_parameters(network, preprocess_image(path, scale_factor=scale_factor))
    finally:
        for handle in handles:
            handle.remove()
    return ranges


class SimulatedIntegerConv(nn.Module):
    """Per-tensor UINT8 activations, per-output INT8 weights, INT32 bias/MAC."""

    def __init__(self, original, input_q, output_q):
        super().__init__()
        weight = original.weight.detach().cpu()
        weight_peak = weight.abs().amax(dim=(1, 2, 3))
        # Some pretrained channels contain subnormal near-zero weights but a
        # nonzero bias. A tiny per-channel scale would overflow INT32 bias.
        bias = original.bias.detach().cpu()
        bias_limit = 2**31 - 1 - 4_194_304
        minimum_scale_for_bias = bias.abs() / (bias_limit * input_q["scale"])
        weight_scale = torch.maximum(
            torch.maximum(weight_peak / 127.0, minimum_scale_for_bias),
            torch.full_like(weight_peak, 1e-8))
        weight_q = torch.clamp(torch.round(weight / weight_scale[:, None, None, None]),
                               -127, 127).to(torch.int8)
        bias_scale = input_q["scale"] * weight_scale
        bias_q = torch.round(bias / bias_scale).to(torch.int32)

        self.register_buffer("weight_q", weight_q)
        self.register_buffer("bias_q", bias_q)
        self.register_buffer("weight_scale", weight_scale)
        self.input_q = input_q
        self.output_q = output_q
        self.stride = original.stride
        self.padding = original.padding
        self.dilation = original.dilation
        self.groups = original.groups
        self.in_channels = original.in_channels
        self.out_channels = original.out_channels
        self.kernel_size = original.kernel_size

    def forward(self, x):
        qx = quantize_uint8(x, self.input_q)
        zp = self.input_q["zero_point"]
        ph, pw = self.padding
        # F.unfold pads with literal zero; quantized zero is the zero-point.
        padded = F.pad(qx.to(torch.float32), (pw, pw, ph, ph), value=float(zp))
        patches = F.unfold(padded, self.kernel_size, dilation=self.dilation,
                           stride=self.stride).to(torch.int32)
        patches -= zp

        n, _, h, w = x.shape
        kh, kw = self.kernel_size
        sh, sw = self.stride
        dh, dw = self.dilation
        oh = (h + 2 * ph - dh * (kh - 1) - 1) // sh + 1
        ow = (w + 2 * pw - dw * (kw - 1) - 1) // sw + 1

        if self.groups == 1:
            weights = self.weight_q.to(torch.int32).reshape(self.out_channels, -1)
            accumulator = torch.matmul(weights, patches)
        elif self.groups == self.in_channels == self.out_channels:
            patches = patches.reshape(n, self.in_channels, kh * kw, -1)
            weights = self.weight_q.to(torch.int32).reshape(1, self.out_channels, kh * kw, 1)
            accumulator = torch.sum(patches * weights, dim=2, dtype=torch.int32)
        else:
            raise NotImplementedError("this prototype supports the model's depthwise and pointwise convolutions")

        accumulator = accumulator + self.bias_q[None, :, None]
        float_accumulator = F.conv2d(
            qx.to(torch.float32) - float(zp), self.weight_q.to(torch.float32),
            self.bias_q.to(torch.float32), stride=self.stride, padding=self.padding,
            dilation=self.dilation, groups=self.groups)
        integer_accumulator = accumulator.reshape(n, self.out_channels, oh, ow)
        discrepancy = (integer_accumulator.to(torch.float32) - float_accumulator).abs().max()
        if discrepancy > 1024.0:
            raise AssertionError(
                "INT32 accumulation disagrees with convolution cross-check: {}".format(
                    float(discrepancy)))
        dequantized = (accumulator.reshape(n, self.out_channels, oh, ow).to(torch.float32)
                       * (self.input_q["scale"] * self.weight_scale)[None, :, None, None])
        qout = quantize_uint8(dequantized, self.output_q)
        return (qout.to(torch.float32) - self.output_q["zero_point"]) * self.output_q["scale"]


def replace_convolutions(network, ranges):
    quantized = copy.deepcopy(network)
    layer_config = {}
    weight_arrays = {}
    for name, module in list(quantized.named_modules()):
        if not isinstance(module, nn.Conv2d):
            continue
        observed = ranges[name]
        input_q = activation_qparams(observed["input_min"], observed["input_max"])
        output_q = activation_qparams(observed["output_min"], observed["output_max"])
        replacement = SimulatedIntegerConv(module, input_q, output_q)
        parent_name, child_name = name.rsplit(".", 1)
        setattr(quantized.get_submodule(parent_name), child_name, replacement)
        layer_config[name] = {
            "input_activation": input_q,
            "output_activation": output_q,
            "weight_dtype": "int8 symmetric per output channel",
            "weight_scale": replacement.weight_scale.tolist(),
            "bias_dtype": "int32",
            "weight_shape_oihw": list(replacement.weight_q.shape),
            "stride": list(replacement.stride),
            "padding": list(replacement.padding),
            "groups": replacement.groups,
        }
        weight_arrays[name + ".weight_int8"] = replacement.weight_q.numpy()
        weight_arrays[name + ".bias_int32"] = replacement.bias_q.numpy()
    quantized.eval()
    return quantized, layer_config, weight_arrays


def image_from_tensor(tensor):
    array = tensor.detach().cpu().numpy()[0].transpose(1, 2, 0)
    return Image.fromarray(np.rint(np.clip(array, 0, 1) * 255).astype(np.uint8), "RGB")


def write_comparison(path, original, fp32, quantized):
    difference = (quantized - fp32).abs() * 8.0
    panels = [("Input", image_from_tensor(original)),
              ("FP32", image_from_tensor(fp32)),
              ("CNN INT8", image_from_tensor(quantized)),
              ("Difference x8", image_from_tensor(difference))]
    width = 640
    height = round(panels[0][1].height * width / panels[0][1].width)
    canvas = Image.new("RGB", (width * len(panels), height + 32), "white")
    drawing = ImageDraw.Draw(canvas)
    for index, (label, panel) in enumerate(panels):
        canvas.paste(panel.resize((width, height), Image.Resampling.LANCZOS), (index * width, 32))
        drawing.text((index * width + 8, 8), label, fill="black")
    canvas.save(path)


def error_metrics(reference, candidate):
    difference = (reference - candidate).abs()
    mae = float(difference.mean())
    mse = float(torch.mean((reference - candidate) ** 2))
    return {"mean_absolute_error": mae, "max_absolute_error": float(difference.max()),
            "rmse": math.sqrt(mse)}


def capture_cnn_outputs(network, image, predict_parameters):
    values = {}
    handles = []
    for name, module in network.named_modules():
        if isinstance(module, (nn.Conv2d, SimulatedIntegerConv)):
            handles.append(module.register_forward_hook(
                lambda _module, _args, result, layer_name=name:
                values.__setitem__(layer_name, result.detach().clone())))
    try:
        output = predict_parameters(network, image)
    finally:
        for handle in handles:
            handle.remove()
    return output, values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--calibration-dir", type=Path)
    parser.add_argument("--evaluation-image", type=Path)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "outputs" / "zero_dce_pp" / "quantization" / "initial")
    parser.add_argument("--scale-factor", type=int, default=12)
    args = parser.parse_args()

    project = args.project_root.resolve()
    calibration_dir = args.calibration_dir or project / "data" / "test"
    evaluation_image = args.evaluation_image or project / "data" / "test" / "night_01.jpg"
    calibration_paths = sorted(path for path in calibration_dir.iterdir()
                               if path.suffix.lower() in IMAGE_EXTENSIONS)
    if not calibration_paths:
        raise ValueError("calibration directory contains no supported images")
    if args.scale_factor < 1:
        raise ValueError("scale-factor must be positive")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(project))
    from model.zero_dce_pp.enhancement import (apply_enhancement, predict_parameters,
                                                resize_parameters)
    from model.zero_dce_pp.inference import load_model
    from model.zero_dce_pp.io_utils import sha256_file
    from model.zero_dce_pp.preprocessing import preprocess_image

    torch.set_num_threads(min(4, torch.get_num_threads()))
    weights_path = project / "model" / "zero_dce_pp" / "weights" / "Epoch99.pth"
    fp32_network = load_model(weights_path, device="cpu", scale_factor=args.scale_factor)
    ranges = collect_ranges(fp32_network, calibration_paths, preprocess_image,
                            predict_parameters, args.scale_factor)
    quantized_network, layers, weights = replace_convolutions(fp32_network, ranges)

    image = preprocess_image(evaluation_image, scale_factor=args.scale_factor)
    with torch.inference_mode():
        parameter_fp32, intermediate_fp32 = capture_cnn_outputs(
            fp32_network, image, predict_parameters)
        parameter_int8, intermediate_int8 = capture_cnn_outputs(
            quantized_network, image, predict_parameters)
        resized_fp32 = resize_parameters(fp32_network, parameter_fp32, tuple(image.shape[-2:]))
        resized_int8 = resize_parameters(quantized_network, parameter_int8, tuple(image.shape[-2:]))
        enhanced_fp32 = apply_enhancement(image, resized_fp32)
        enhanced_int8 = apply_enhancement(image, resized_int8)

    np.savez_compressed(output / "cnn_int8_weights.npz", **weights)
    np.save(output / "parameters_lowres_fp32.npy", parameter_fp32.numpy(), allow_pickle=False)
    np.save(output / "parameters_lowres_int8.npy", parameter_int8.numpy(), allow_pickle=False)
    np.save(output / "enhanced_int8.npy", enhanced_int8.numpy(), allow_pickle=False)
    image_from_tensor(enhanced_fp32).save(output / "enhanced_fp32.png")
    image_from_tensor(enhanced_int8).save(output / "enhanced_int8.png")
    write_comparison(output / "comparison.png", image, enhanced_fp32, enhanced_int8)

    pixel_fp32 = np.asarray(image_from_tensor(enhanced_fp32), dtype=np.int16)
    pixel_int8 = np.asarray(image_from_tensor(enhanced_int8), dtype=np.int16)
    pixel_delta = np.abs(pixel_fp32 - pixel_int8)
    reference_dir = project / "outputs" / "zero_dce_pp" / "reference"
    recorded_reference_error = {}
    for name, current in (("parameters_lowres", parameter_fp32),
                          ("enhanced", enhanced_fp32)):
        recorded_path = reference_dir / (name + ".npy")
        if recorded_path.is_file():
            recorded = np.load(recorded_path, allow_pickle=False)
            recorded_reference_error[name] = error_metrics(
                torch.from_numpy(recorded), current)
    report = {
        "status": "preliminary single-image PTQ; not a deployable FPGA design",
        "calibration_images": [str(path) for path in calibration_paths],
        "evaluation_image": str(evaluation_image),
        "evaluation_reuses_calibration_image": evaluation_image.resolve() in
        {path.resolve() for path in calibration_paths},
        "model": "Zero-DCE++ Epoch99.pth",
        "weights_sha256": sha256_file(weights_path),
        "pytorch_version": torch.__version__,
        "scale_factor": args.scale_factor,
        "cnn_input_shape_nchw": list(image.shape),
        "parameter_shape_nchw": list(parameter_fp32.shape),
        "quantization": {
            "scope": "14 CNN convolutions only; downsampling, Tanh, upsampling and curve mapping FP32",
            "activations": "UINT8 asymmetric per tensor, min/max calibration, round-to-nearest-even",
            "weights": "INT8 symmetric per output channel, range [-127,127]",
            "bias_and_accumulator": "INT32",
            "execution": "INT32 convolution simulated with PyTorch unfold/matmul; FP32 requantization",
            "activation_scale_zero_point": "see cnn_quantization.json",
        },
        "parameter_lowres_error": error_metrics(parameter_fp32, parameter_int8),
        "recorded_fp32_reference_error": recorded_reference_error,
        "convolution_output_error": {
            name: error_metrics(intermediate_fp32[name], intermediate_int8[name])
            for name in layers
        },
        "parameter_fullres_error": error_metrics(resized_fp32, resized_int8),
        "enhanced_fp32_error": error_metrics(enhanced_fp32, enhanced_int8),
        "enhanced_png_error": {
            "mean_absolute_uint8_levels": float(pixel_delta.mean()),
            "max_absolute_uint8_levels": int(pixel_delta.max()),
            "changed_channel_fraction": float(np.count_nonzero(pixel_delta) / pixel_delta.size),
        },
        "limitations": [
            "One calibration image is not representative and is also used for evaluation.",
            "FP32 interpolation, Tanh and eight curve rounds are not quantized.",
            "PyTorch INT32 simulation is not an HLS kernel or speed benchmark.",
            "No FPGA resource, timing or visual-quality acceptance claim is made.",
        ],
    }
    (output / "cnn_quantization.json").write_text(
        json.dumps(layers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output),
                      "parameter_lowres_error": report["parameter_lowres_error"],
                      "enhanced_fp32_error": report["enhanced_fp32_error"],
                      "enhanced_png_error": report["enhanced_png_error"]}, indent=2))


if __name__ == "__main__":
    main()
