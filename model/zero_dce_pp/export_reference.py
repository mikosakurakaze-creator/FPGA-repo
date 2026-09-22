"""Export Zero-DCE++ FP32 reference tensors for later FPGA comparison."""

import argparse
from pathlib import Path
from typing import Dict

import torch
from PIL import Image
from torch import Tensor

from .enhancement import (
    downsample_input,
    enhancement_steps,
    predict_parameters,
    resize_parameters,
)
from .inference import DEFAULT_WEIGHTS, load_model
from .io_utils import save_json, save_tensor, sha256_file
from .preprocessing import preprocess_image


UPSTREAM_REPOSITORY = "https://github.com/Li-Chongyi/Zero-DCE_extension"
UPSTREAM_COMMIT = "09f202b690f82da939b8e6ec8535960ae97ad8bd"
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "zero_dce_pp"
    / "reference"
)


def tensor_metadata(tensor: Tensor) -> Dict[str, object]:
    return {
        "dtype": str(tensor.dtype),
        "layout": "NCHW",
        "shape": list(tensor.shape),
    }


def export_reference(
    image_path: Path,
    weights_path: Path,
    output_dir: Path,
    device: str = "cpu",
    scale_factor: int = 12,
) -> Dict[str, object]:
    """Export the requested V1 tensors without image encoding or clipping."""
    image_path = Path(image_path)
    weights_path = Path(weights_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as opened_image:
        original_image_size = [opened_image.height, opened_image.width]

    target_device = torch.device(device)
    model_input = preprocess_image(
        image_path,
        scale_factor=scale_factor,
    ).to(target_device)
    network = load_model(
        weights_path,
        device=target_device,
        scale_factor=scale_factor,
    )

    with torch.no_grad():
        downsampled = downsample_input(network, model_input)
        parameters_lowres = predict_parameters(network, model_input)
        parameters_fullres = resize_parameters(
            network,
            parameters_lowres,
            tuple(model_input.shape[-2:]),
        )
        steps = enhancement_steps(model_input, parameters_fullres)

    tensors = {
        "model_input": model_input,
        "input_downsampled": downsampled,
        "parameters_lowres": parameters_lowres,
        "parameters_fullres": parameters_fullres,
    }
    for index, step in enumerate(steps, start=1):
        tensors["enhancement_iter_{:02d}".format(index)] = step
    tensors["enhanced"] = steps[-1]

    file_metadata = {}
    for name, tensor in tensors.items():
        file_name = "{}.npy".format(name)
        save_tensor(output_dir / file_name, tensor)
        file_metadata[file_name] = tensor_metadata(tensor)

    metadata = {
        "model": {
            "name": "Zero-DCE++",
            "upstream_repository": UPSTREAM_REPOSITORY,
            "upstream_commit": UPSTREAM_COMMIT,
        },
        "weights": {
            "file_name": weights_path.name,
            "sha256": sha256_file(weights_path),
            "format": "PyTorch state_dict",
        },
        "input": {
            "file_name": image_path.name,
            "original_image_size_hw": original_image_size,
            "model_input_size_nchw": list(model_input.shape),
            "channel_order": "RGB",
            "normalization": "uint8 / 255.0",
        },
        "execution": {
            "device": str(target_device),
            "pytorch_version": str(torch.__version__),
            "scale_factor": scale_factor,
            "dtype": str(model_input.dtype),
        },
        "tensor_format": "NCHW",
        "files": file_metadata,
        "notes": [
            "All arrays contain raw tensors before image serialization.",
            "No clipping or quantization is applied.",
            "Convolution-layer intermediate export is deferred.",
        ],
    }
    save_json(output_dir / "metadata.json", metadata)
    return metadata


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export Zero-DCE++ FP32 FPGA reference tensors."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS, type=Path)
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        type=Path,
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--scale-factor", default=12, type=int)
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    export_reference(
        image_path=args.input,
        weights_path=args.weights,
        output_dir=args.output_dir,
        device=args.device,
        scale_factor=args.scale_factor,
    )
    print("reference_directory: {}".format(args.output_dir))


if __name__ == "__main__":
    main()
