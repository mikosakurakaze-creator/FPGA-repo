"""Single-image Zero-DCE++ inference entry points.

These adapters have not yet been runtime-validated in this repository.
"""

import argparse
from pathlib import Path
from typing import Dict, Tuple, Union

import torch
from PIL import Image
from torch import Tensor

from .enhancement import enhance_image
from .io_utils import save_json, save_rgb_preview, save_tensor, sha256_file
from .preprocessing import ImageSource, preprocess_image
from .upstream.model import enhance_net_nopool


DeviceLike = Union[str, torch.device]
MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parents[1]
DEFAULT_WEIGHTS = MODULE_DIR / "weights" / "Epoch99.pth"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "zero_dce_pp" / "inference"


def load_model(
    weights_path: Union[str, Path],
    device: DeviceLike = "cpu",
    scale_factor: int = 12,
) -> enhance_net_nopool:
    """Construct the official network and load its raw PyTorch state_dict."""
    target_device = torch.device(device)
    network = enhance_net_nopool(scale_factor).to(target_device)
    state_dict = torch.load(Path(weights_path), map_location=target_device)
    network.load_state_dict(state_dict)
    network.eval()
    return network


def enhance_file(
    image_path: ImageSource,
    weights_path: Union[str, Path],
    device: DeviceLike = "cpu",
    scale_factor: int = 12,
) -> Tuple[Tensor, Tensor]:
    """Prepare and enhance one image without saving or clamping the result.

    Returns the enhanced image and resized parameter map as NCHW tensors on
    the selected device. The function deliberately does not choose an output
    image encoding, because serialization can introduce implicit clipping.
    """
    image = preprocess_image(image_path, scale_factor=scale_factor)
    image = image.to(torch.device(device))
    network = load_model(
        weights_path,
        device=device,
        scale_factor=scale_factor,
    )

    with torch.no_grad():
        return enhance_image(network, image)


def run_inference(
    image_path: ImageSource,
    weights_path: Union[str, Path] = DEFAULT_WEIGHTS,
    output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR,
    device: DeviceLike = "cpu",
    scale_factor: int = 12,
) -> Dict[str, str]:
    """Run one image and save raw tensors separately from PNG previews."""
    image_path = Path(image_path)
    weights_path = Path(weights_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as opened_image:
        original_rgb = opened_image.convert("RGB")
        original_size = [original_rgb.height, original_rgb.width]
        original_rgb.save(output_dir / "original_input.png")

    model_input = preprocess_image(image_path, scale_factor=scale_factor)
    target_device = torch.device(device)
    model_input = model_input.to(target_device)
    network = load_model(
        weights_path,
        device=target_device,
        scale_factor=scale_factor,
    )

    with torch.no_grad():
        enhanced, parameters = enhance_image(network, model_input)

    paths = {
        "original_input_png": str(output_dir / "original_input.png"),
        "model_input_npy": str(output_dir / "model_input.npy"),
        "model_input_png": str(output_dir / "model_input.png"),
        "enhanced_npy": str(output_dir / "enhanced.npy"),
        "enhanced_png": str(output_dir / "enhanced.png"),
        "parameter_map_npy": str(output_dir / "parameter_map.npy"),
        "parameter_map_png": str(output_dir / "parameter_map.png"),
        "metadata_json": str(output_dir / "metadata.json"),
    }
    save_tensor(Path(paths["model_input_npy"]), model_input)
    save_tensor(Path(paths["enhanced_npy"]), enhanced)
    save_tensor(Path(paths["parameter_map_npy"]), parameters)
    save_rgb_preview(Path(paths["model_input_png"]), model_input)
    save_rgb_preview(Path(paths["enhanced_png"]), enhanced)
    save_rgb_preview(
        Path(paths["parameter_map_png"]),
        parameters,
        value_range=(-1.0, 1.0),
    )

    metadata = {
        "device": str(target_device),
        "input_file_name": image_path.name,
        "original_image_size_hw": original_size,
        "model_input_size_nchw": list(model_input.shape),
        "parameter_map_size_nchw": list(parameters.shape),
        "pytorch_version": str(torch.__version__),
        "scale_factor": scale_factor,
        "tensor_dtype": str(model_input.dtype),
        "tensor_format": "NCHW",
        "channel_order": "RGB",
        "weight_file_name": weights_path.name,
        "weight_sha256": sha256_file(weights_path),
        "png_policy": {
            "model_input": "clip [0,1], round to uint8",
            "enhanced": "clip [0,1], round to uint8",
            "parameter_map": "map [-1,1] to [0,1], clip, round to uint8",
        },
    }
    save_json(Path(paths["metadata_json"]), metadata)
    return paths


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Zero-DCE++ image and save tensors/previews."
    )
    parser.add_argument("--input", required=True, help="input image path")
    parser.add_argument(
        "--weights",
        default=str(DEFAULT_WEIGHTS),
        help="PyTorch state_dict path",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="directory for tensors, previews, and metadata",
    )
    parser.add_argument("--device", default="cpu", help="cpu, cuda, or cuda:N")
    parser.add_argument("--scale-factor", type=int, default=12)
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    paths = run_inference(
        image_path=args.input,
        weights_path=args.weights,
        output_dir=args.output_dir,
        device=args.device,
        scale_factor=args.scale_factor,
    )
    for name, path in sorted(paths.items()):
        print("{}: {}".format(name, path))


if __name__ == "__main__":
    main()
