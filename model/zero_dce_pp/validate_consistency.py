"""Compare the official forward with the decomposed project adapter."""

import argparse
from pathlib import Path
from typing import Dict, Union

import torch
from torch import Tensor

from .enhancement import enhance_image
from .inference import DEFAULT_WEIGHTS, load_model
from .io_utils import save_json, sha256_file
from .preprocessing import preprocess_image


DEFAULT_REPORT = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "zero_dce_pp"
    / "consistency_report.json"
)


def tensor_error(
    reference: Tensor,
    candidate: Tensor,
    absolute_tolerance: float,
) -> Dict[str, Union[float, bool]]:
    """Calculate direct FP32 tensor errors before any image serialization."""
    if reference.shape != candidate.shape:
        raise ValueError("cannot compare tensors with different shapes")
    if reference.dtype != torch.float32 or candidate.dtype != torch.float32:
        raise ValueError("consistency validation requires FP32 tensors")

    absolute_error = torch.abs(reference - candidate)
    maximum = absolute_error.max().item()
    mean = absolute_error.mean().item()
    return {
        "max_absolute_error": maximum,
        "mean_absolute_error": mean,
        "absolute_tolerance": absolute_tolerance,
        "passed": maximum <= absolute_tolerance,
    }


def validate(
    image_path: Path,
    weights_path: Path,
    report_path: Path,
    device: str = "cpu",
    scale_factor: int = 12,
    absolute_tolerance: float = 1e-6,
) -> Dict[str, object]:
    """Run both paths on one shared FP32 input and emit a JSON report."""
    target_device = torch.device(device)
    image = preprocess_image(
        image_path,
        scale_factor=scale_factor,
    ).to(target_device)
    network = load_model(
        weights_path,
        device=target_device,
        scale_factor=scale_factor,
    )

    with torch.no_grad():
        official_enhanced, official_parameters = network(image)
        split_enhanced, split_parameters = enhance_image(network, image)

    enhanced_metrics = tensor_error(
        official_enhanced,
        split_enhanced,
        absolute_tolerance,
    )
    parameter_metrics = tensor_error(
        official_parameters,
        split_parameters,
        absolute_tolerance,
    )
    report = {
        "passed": bool(
            enhanced_metrics["passed"] and parameter_metrics["passed"]
        ),
        "enhanced_image": enhanced_metrics,
        "full_resolution_parameter_map": parameter_metrics,
        "environment": {
            "pytorch_version": str(torch.__version__),
            "device": str(target_device),
            "input_dtype": str(image.dtype),
            "input_size_nchw": list(image.shape),
            "scale_factor": scale_factor,
        },
        "input_file_name": Path(image_path).name,
        "weight_file_name": Path(weights_path).name,
        "weight_sha256": sha256_file(Path(weights_path)),
        "comparison": "direct FP32 tensors before serialization",
    }
    save_json(report_path, report)
    return report


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare official and decomposed Zero-DCE++ FP32 outputs."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS, type=Path)
    parser.add_argument(
        "--report",
        default=DEFAULT_REPORT,
        type=Path,
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--scale-factor", default=12, type=int)
    parser.add_argument("--atol", default=1e-6, type=float)
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    report = validate(
        image_path=args.input,
        weights_path=args.weights,
        report_path=args.report,
        device=args.device,
        scale_factor=args.scale_factor,
        absolute_tolerance=args.atol,
    )
    print("consistency_passed: {}".format(report["passed"]))
    print("report: {}".format(args.report))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
