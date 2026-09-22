"""Single-image Zero-DCE++ inference entry points.

These adapters have not yet been runtime-validated in this repository.
"""

from pathlib import Path
from typing import Tuple, Union

import torch
from torch import Tensor

from .enhancement import enhance_image
from .preprocessing import ImageSource, preprocess_image
from .upstream.model import enhance_net_nopool


DeviceLike = Union[str, torch.device]


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
