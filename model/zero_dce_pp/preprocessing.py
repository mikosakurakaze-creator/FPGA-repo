"""Input preparation matching the official Zero-DCE++ test script."""

from pathlib import Path
from typing import Union

import numpy as np
import torch
from PIL import Image
from torch import Tensor


ImageSource = Union[str, Path, Image.Image]


def preprocess_image(
    image: ImageSource,
    scale_factor: int = 12,
) -> Tensor:
    """Read an image and return an RGB float tensor in NCHW layout.

    The official test script divides uint8 samples by 255, converts to a
    float tensor, crops height and width down to multiples of scale_factor,
    changes HWC to CHW, and adds a batch dimension. This adapter additionally
    makes RGB conversion explicit so grayscale and alpha-bearing files cannot
    silently violate the network's three-channel contract.

    No normalization beyond division by 255 is performed.
    """
    if scale_factor < 1:
        raise ValueError("scale_factor must be a positive integer")

    if isinstance(image, Image.Image):
        rgb_image = image.convert("RGB")
    else:
        with Image.open(Path(image)) as opened_image:
            rgb_image = opened_image.convert("RGB")

    image_array = np.asarray(rgb_image) / 255.0
    image_tensor = torch.from_numpy(image_array).float()

    height = (image_tensor.shape[0] // scale_factor) * scale_factor
    width = (image_tensor.shape[1] // scale_factor) * scale_factor
    if height == 0 or width == 0:
        raise ValueError(
            "image dimensions must each be at least scale_factor pixels"
        )

    image_tensor = image_tensor[:height, :width, :]
    return image_tensor.permute(2, 0, 1).unsqueeze(0).contiguous()
