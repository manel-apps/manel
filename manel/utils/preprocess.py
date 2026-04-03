from __future__ import annotations

from PIL import Image, ImageFilter, ImageEnhance


def to_high_contrast_bw(image: Image.Image) -> Image.Image:
    """Convert image to high contrast black and white for panel detection.

    Steps:
    1. Convert to grayscale
    2. Apply aggressive contrast enhancement
    3. Threshold to pure B/W
    4. Denoise slightly to clean artifacts
    """
    gray = image.convert("L")

    enhancer = ImageEnhance.Contrast(gray)
    contrasted = enhancer.enhance(3.0)

    threshold = 128
    bw = contrasted.point(lambda p: 255 if p > threshold else 0)

    bw = bw.filter(ImageFilter.MedianFilter(size=3))

    return bw


def preprocess_for_analysis(image: Image.Image) -> Image.Image:
    """Preprocess an image for panel detection and analysis.

    Returns a high-contrast B/W version optimized for SAM2 and DINOv2.
    """
    return to_high_contrast_bw(image)
