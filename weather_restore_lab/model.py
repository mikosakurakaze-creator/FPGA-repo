"""Local restoration candidate; no pretrained or FPGA performance claims."""
import math
import torch
from torch import nn


class TinyRestore(nn.Module):
    def __init__(self, channels=8, blocks=5):
        super().__init__()
        if channels not in (8, 16) or not 1 <= blocks <= 7:
            raise ValueError('Supported candidate: channels=8/16, blocks=1..7')
        self.channels, self.block_count = channels, blocks
        self.stem = nn.Conv2d(3, channels, 3, padding=1)
        self.blocks = nn.ModuleList([
            nn.ModuleDict({'depth': nn.Conv2d(channels, channels, 3, padding=1, groups=channels),
                           'point': nn.Conv2d(channels, channels, 1)}) for _ in range(blocks)])
        self.tail = nn.Conv2d(channels, 3, 1)
        nn.init.zeros_(self.tail.weight)
        nn.init.zeros_(self.tail.bias)

    @property
    def halo(self):
        return 1 + self.block_count

    def forward(self, x, taps=None):
        def record(name, value):
            if taps is not None:
                taps[name] = value
            return value
        record('input', x)
        z = torch.relu(record('stem', self.stem(x)))
        for i, block in enumerate(self.blocks):
            d = torch.relu(record(f'blocks.{i}.depth', block['depth'](z)))
            p = record(f'blocks.{i}.point', block['point'](d))
            z = torch.relu(record(f'blocks.{i}.add', z + p))
        residual = record('tail', self.tail(z))
        return record('output', x + residual)

    def config(self):
        return {'channels': self.channels, 'blocks': self.block_count}


@torch.inference_mode()
def tiled_forward(model, x, core=128):
    """Exact receptive-field overlap, crop cores; no resize or blended seams."""
    if core <= 0 or x.ndim != 4:
        raise ValueError('Expected NCHW and positive tile core')
    height, width = x.shape[-2:]
    result = torch.empty_like(x)
    halo = model.halo
    for y in range(0, height, core):
        for col in range(0, width, core):
            y1, x1 = min(height, y + core), min(width, col + core)
            top, left = max(0, y-halo), max(0, col-halo)
            patch = x[..., top:min(height, y1+halo), left:min(width, x1+halo)]
            output = model(patch)
            result[..., y:y1, col:x1] = output[..., y-top:y1-top, col-left:x1-left]
    return result


def engineering_profile(model, height=720, width=1272, core=128, fps=30):
    if min(height, width, core, fps) <= 0:
        raise ValueError('Dimensions and FPS must be positive')
    c, b = model.channels, model.block_count
    mac_per_pixel = 27*c + b*(9*c+c*c) + 3*c
    patch_pixels = 0
    halo = model.halo
    for y in range(0, height, core):
        for x in range(0, width, core):
            patch_pixels += (min(height,y+core+halo)-max(0,y-halo)) * (min(width,x+core+halo)-max(0,x-halo))
    largest_patch = min(height, core+2*halo)*min(width, core+2*halo)
    weights = sum(p.numel() for name,p in model.named_parameters() if name.endswith('weight'))
    biases = sum(p.numel() for name,p in model.named_parameters() if name.endswith('bias'))
    macs = height*width*mac_per_pixel
    return {
        'config': model.config(), 'input_nchw': [1,3,height,width],
        'parameters': weights+biases, 'weight_int8_bytes': weights,
        'bias_int32_bytes': biases*4, 'halo_pixels': halo,
        'receptive_field_pixels': 2*halo+1, 'mac_definition': 'one multiply-accumulate = one MAC',
        'macs_per_frame': macs, 'tiled_macs_per_frame': patch_pixels*mac_per_pixel,
        'required_gmac_per_second': macs*fps/1e9,
        'required_tiled_gmac_per_second': patch_pixels*mac_per_pixel*fps/1e9,
        'largest_single_feature_int16_bytes': largest_patch*c*2,
        'three_live_feature_planes_int16_bytes_estimate': largest_patch*c*2*3,
        'minimum_rgb_input_plus_output_int16_bytes_per_frame': height*width*3*2*2,
        'limits': ['No HLS/Vivado/board verification',
                   'Feature estimate is not allocated BRAM; line streaming changes storage',
                   'DDR figure excludes intermediate spills, overlap, weights, bursts and cache costs',
                   'No DSP packing, sustained bandwidth or achievable FPS inferred'],
        'hardware_deployable': 'NOT_VERIFIED'}
