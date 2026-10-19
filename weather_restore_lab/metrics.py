import numpy as np
from skimage.metrics import structural_similarity


def quality(prediction, reference):
    """RGB [0,1], full image, no border shave or per-image normalization."""
    prediction = np.clip(prediction,0,1).astype(np.float64)
    reference = reference.astype(np.float64)
    mse = float(np.mean((prediction-reference)**2))
    psnr = None if mse == 0 else float(-10*np.log10(mse))
    side = min(reference.shape[:2])
    window = min(7,side if side%2 else side-1)
    if window < 3:
        raise ValueError('SSIM requires images at least 3x3')
    return {'psnr_db':psnr, 'psnr_infinite':mse == 0,
            'ssim':float(structural_similarity(reference,prediction,data_range=1,
                                             channel_axis=2,win_size=window)),
            'mae':float(np.abs(prediction-reference).mean())}
