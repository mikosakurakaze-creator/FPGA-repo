"""Traceable decomposition of the official Zero-DCE++ forward pass."""

from typing import List, Tuple

import torch
import torch.nn.functional as F
from torch import Tensor

from .upstream.model import enhance_net_nopool


ENHANCEMENT_ITERATIONS = 8


def _validate_image_tensor(image: Tensor) -> None:
    if image.dim() != 4 or image.shape[1] != 3:
        raise ValueError("expected an NCHW tensor with exactly three channels")


def downsample_input(
    network: enhance_net_nopool,
    image: Tensor,
) -> Tensor:
    """Apply the input scaling operation used by the upstream forward."""
    _validate_image_tensor(image)
    if network.scale_factor == 1:
        return image
    return F.interpolate(
        image,
        scale_factor=1 / network.scale_factor,
        mode="bilinear",
    )


def predict_parameters(
    network: enhance_net_nopool,
    image: Tensor,
) -> Tensor:
    """Predict the low-resolution three-channel curve parameter map.

    This is the parameter-prediction portion of upstream model.py::forward,
    kept in the same operation order. For scale_factor > 1, the returned map
    is still at the network's reduced spatial resolution.
    """
    _validate_image_tensor(image)
    image_down = downsample_input(network, image)

    feature_1 = network.relu(network.e_conv1(image_down))
    feature_2 = network.relu(network.e_conv2(feature_1))
    feature_3 = network.relu(network.e_conv3(feature_2))
    feature_4 = network.relu(network.e_conv4(feature_3))
    feature_5 = network.relu(
        network.e_conv5(torch.cat([feature_3, feature_4], dim=1))
    )
    feature_6 = network.relu(
        network.e_conv6(torch.cat([feature_2, feature_5], dim=1))
    )
    return F.tanh(
        network.e_conv7(torch.cat([feature_1, feature_6], dim=1))
    )


def resize_parameters(
    network: enhance_net_nopool,
    parameters: Tensor,
    output_size: Tuple[int, int],
) -> Tensor:
    """Apply the exact upsampling module declared by the upstream network."""
    if network.scale_factor == 1:
        resized = parameters
    else:
        resized = network.upsample(parameters)

    if tuple(resized.shape[-2:]) != tuple(output_size):
        raise ValueError(
            "official scale-factor upsampling did not reproduce the input "
            "size; preprocess with dimensions divisible by scale_factor"
        )
    return resized


def enhancement_steps(image: Tensor, parameters: Tensor) -> List[Tensor]:
    """Return all eight upstream curve-update results in operation order."""
    _validate_image_tensor(image)
    if image.shape != parameters.shape:
        raise ValueError("image and parameter tensors must have equal shapes")

    enhanced = image
    steps = []
    for _ in range(ENHANCEMENT_ITERATIONS):
        enhanced = enhanced + parameters * (
            torch.pow(enhanced, 2) - enhanced
        )
        steps.append(enhanced)
    return steps


def apply_enhancement(image: Tensor, parameters: Tensor) -> Tensor:
    """Apply the upstream curve update eight times without output clipping."""
    return enhancement_steps(image, parameters)[-1]


def enhance_image(
    network: enhance_net_nopool,
    image: Tensor,
) -> Tuple[Tensor, Tensor]:
    """Enhance one NCHW batch and return (enhanced_image, parameter_map)."""
    low_resolution_parameters = predict_parameters(network, image)
    parameters = resize_parameters(
        network,
        low_resolution_parameters,
        tuple(image.shape[-2:]),
    )
    enhanced = apply_enhancement(image, parameters)
    return enhanced, parameters
