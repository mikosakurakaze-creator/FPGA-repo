"""Serialization helpers that keep raw tensors separate from PNG previews."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image
from torch import Tensor


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it all at once."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def tensor_to_numpy(tensor: Tensor) -> np.ndarray:
    """Detach a tensor and preserve its numeric values, dtype, and layout."""
    return tensor.detach().cpu().numpy()


def save_tensor(path: Path, tensor: Tensor) -> None:
    """Save a tensor as an uncompressed NumPy array."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, tensor_to_numpy(tensor), allow_pickle=False)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write deterministic, human-readable UTF-8 JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def save_rgb_preview(
    path: Path,
    tensor: Tensor,
    value_range: Tuple[float, float] = (0.0, 1.0),
) -> None:
    """Save the first NCHW RGB sample as a clipped uint8 PNG preview.

    This conversion is visualization only. It must not be used for numerical
    comparison or FPGA golden data.
    """
    if tensor.dim() != 4 or tensor.shape[0] != 1 or tensor.shape[1] != 3:
        raise ValueError("preview expects a [1, 3, H, W] tensor")

    lower, upper = value_range
    if not lower < upper:
        raise ValueError("value_range must satisfy lower < upper")

    image = tensor_to_numpy(tensor)[0].transpose(1, 2, 0)
    image = (image - lower) / (upper - lower)
    image = np.clip(image, 0.0, 1.0)
    image = np.rint(image * 255.0).astype(np.uint8)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(path)
