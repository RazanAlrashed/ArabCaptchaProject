"""
utils/image_preprocessor.py

Handles scanned/low-quality Arabic word images:
  ✓ Upscaling (super-resolution for small/blurry crops)
  ✓ Contrast enhancement (brings out faded text from scans)
  ✓ Denoising (removes scan artifacts without losing letters)
  ✓ Size normalization (ensures ref and lc words are comparable)
  ✓ Padding (adds context, prevents edge artifacts in distortion)

Input: raw crop from document scan or typed text
Output: normalized, high-quality image ready for distortion
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple

# ══════════════════════════════════════════════════════════════
# UPSCALING / SUPER-RESOLUTION
# ══════════════════════════════════════════════════════════════

def _upscale_image(img: np.ndarray, scale_factor: float = 2.0) -> np.ndarray:
    """
    Upscale image using OpenCV's INTER_CUBIC interpolation.
    Good for small/blurry crops from document scans.
    
    Args:
        img: input image (BGR)
        scale_factor: how many times to enlarge (1.5-3.0 typical)
    
    Returns:
        upscaled image with same color space
    """
    h, w = img.shape[:2]
    new_h = int(h * scale_factor)
    new_w = int(w * scale_factor)
    
    # INTER_CUBIC for smooth upscaling
    upscaled = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return upscaled


def _adaptive_upscale(img: np.ndarray, min_height: int = 100) -> np.ndarray:
    """
    Smart upscaling: scales image to minimum height while preserving aspect ratio.
    
    Args:
        img: input image
        min_height: target minimum height (typically 100-150 px)
    
    Returns:
        upscaled image with height >= min_height
    
    Example:
        Small scan 40x200 → upscale 2x → 80x400 (height still < 100)
                        → upscale to 100 → 50x250 (correct aspect, min height met)
    """
    h, w = img.shape[:2]
    
    if h >= min_height:
        return img  # Already large enough
    
    scale = min_height / h
    new_h = min_height
    new_w = int(w * scale)
    
    upscaled = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return upscaled


# ══════════════════════════════════════════════════════════════
# CONTRAST & BRIGHTNESS ENHANCEMENT
# ══════════════════════════════════════════════════════════════

def _enhance_contrast(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    """
    CLAHE (Contrast Limited Adaptive Histogram Equalization).
    Brings out faded text from old document scans.
    
    Args:
        img: input image (BGR)
        clip_limit: contrast limit (1.5-3.0 for scans)
    
    Returns:
        enhanced image with boosted local contrast
    """
    # Convert to LAB color space (better for contrast)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    
    # Apply CLAHE to L (lightness) channel
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)
    
    # Merge and convert back
    lab[:, :, 0] = l_enhanced
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    return enhanced


def _auto_levels(img: np.ndarray) -> np.ndarray:
    """
    Stretch the histogram to fill the full range [0, 255].
    Fixes low-contrast faded scans automatically.
    
    Args:
        img: input image
    
    Returns:
        image with full-range contrast
    """
    # Convert to LAB
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    
    # Stretch L channel to [0, 255]
    min_val = l_channel.min()
    max_val = l_channel.max()
    
    if max_val > min_val:
        l_stretched = np.clip((l_channel - min_val) * 255.0 / (max_val - min_val), 0, 255).astype(np.uint8)
    else:
        l_stretched = l_channel
    
    lab[:, :, 0] = l_stretched
    stretched = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    return stretched


# ══════════════════════════════════════════════════════════════
# DENOISING
# ══════════════════════════════════════════════════════════════

def _denoise_scan(img: np.ndarray, strength: float = 10.0, method: str = "bilateral") -> np.ndarray:
    """
    Bilateral filtering for denoising: preserves edges while removing noise.
    More compatible than fastNlMeansDenoisingColored across OpenCV versions.
    
    Args:
        img: input image (BGR)
        strength: denoising strength (7-15 for scans)
        method: "bilateral" (default, fast, compatible) or "gaussian" (lighter)
    
    Returns:
        denoised image with cleaner texture
    """
    if method == "bilateral":
        # Bilateral filter: excellent for text/document images
        # diameter: pixel neighborhood size (9-15 typical)
        # sigmaColor: color space sigma (75-100 typical)
        # sigmaSpace: coordinate space sigma (75-100 typical)
        
        d = int(strength)  # neighborhood diameter
        sigma_color = int(strength * 8)
        sigma_space = int(strength * 8)
        
        denoised = cv2.bilateralFilter(
            img,
            d=d,
            sigmaColor=sigma_color,
            sigmaSpace=sigma_space
        )
        return denoised
    
    elif method == "gaussian":
        # Very light Gaussian blur — softer alternative
        kernel_size = max(3, int(strength / 2) * 2 + 1)  # ensure odd
        denoised = cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)
        return denoised
    
    else:
        # Fallback: no denoising
        return img


def _morphological_denoise(img: np.ndarray) -> np.ndarray:
    """
    Removes small noise spots while preserving text details.
    Uses opening (erode then dilate) to clean up artifacts.
    
    Args:
        img: input image
    
    Returns:
        denoised image
    """
    # Create a kernel for morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    
    # Opening: remove small noise
    opened = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=1)
    
    return opened


# ══════════════════════════════════════════════════════════════
# SIZE NORMALIZATION
# ══════════════════════════════════════════════════════════════

def _normalize_size(img: np.ndarray, target_height: int = 120) -> np.ndarray:
    """
    Resize image to a standard height while preserving aspect ratio.
    Ensures both ref and lc words are comparable in size.
    
    Args:
        img: input image
        target_height: desired height (120-150 typical)
    
    Returns:
        resized image with preserved aspect ratio
    """
    h, w = img.shape[:2]
    
    if h == target_height:
        return img
    
    scale = target_height / h
    new_w = int(w * scale)
    
    normalized = cv2.resize(img, (new_w, target_height), interpolation=cv2.INTER_CUBIC)
    return normalized


def _pad_to_width(img: np.ndarray, target_width: int = 200, pad_color: Tuple[int, int, int] = (255, 255, 255)) -> np.ndarray:
    """
    Pad image horizontally to a minimum width.
    Adds context around words to prevent edge distortion artifacts.
    
    Args:
        img: input image
        target_width: minimum width to pad to
        pad_color: RGB color for padding (white default)
    
    Returns:
        padded image centered with white space
    """
    h, w = img.shape[:2]
    
    if w >= target_width:
        return img
    
    pad_left = (target_width - w) // 2
    pad_right = target_width - w - pad_left
    
    padded = cv2.copyMakeBorder(
        img,
        top=10,                      # slight top/bottom padding too
        bottom=10,
        left=pad_left,
        right=pad_right,
        borderType=cv2.BORDER_CONSTANT,
        value=pad_color
    )
    
    return padded


# ══════════════════════════════════════════════════════════════
# FULL PREPROCESSING PIPELINE
# ══════════════════════════════════════════════════════════════

def preprocess_word_image(
    image_path: str,
    target_height: int = 120,
    target_width: int = 200,
    upscale_small: bool = True,
    enhance_contrast: bool = True,
    denoise: bool = True,
    denoise_method: str = "bilateral",
) -> np.ndarray:
    """
    Complete preprocessing pipeline for scanned/low-quality Arabic word images.
    
    Pipeline stages (in order):
      1. Load image
      2. Upscale if too small (optional)
      3. Enhance contrast / levels (optional)
      4. Denoise (optional)
      5. Normalize size to target height
      6. Pad to minimum width
    
    Args:
        image_path: path to word crop image
        target_height: standardize to this height (120-150 typical)
        target_width: minimum width (200 typical)
        upscale_small: enable smart upscaling
        enhance_contrast: enable CLAHE contrast boost
        denoise: enable denoising
        denoise_method: "bilateral" (default), "gaussian", or "none"
    
    Returns:
        preprocessed image ready for distortion
    
    Example:
        >>> preprocessed = preprocess_word_image("scan_crop.jpg", target_height=130)
        >>> # Output: clear, normalized, padded image
    """
    # 1. Load
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    
    # 2. Upscale if small
    if upscale_small:
        img = _adaptive_upscale(img, min_height=100)
    
    # 3. Enhance contrast
    if enhance_contrast:
        img = _enhance_contrast(img, clip_limit=2.5)
        img = _auto_levels(img)
    
    # 4. Denoise
    if denoise:
        img = _denoise_scan(img, strength=10.0, method=denoise_method)
    
    # 5. Normalize height
    img = _normalize_size(img, target_height=target_height)
    
    # 6. Pad width
    img = _pad_to_width(img, target_width=target_width)
    
    return img


def preprocess_and_save(
    input_path: str,
    output_path: str,
    target_height: int = 120,
    target_width: int = 200,
    **kwargs
) -> None:
    """
    Preprocess image and save to disk.
    
    Args:
        input_path: source image path
        output_path: where to save preprocessed image
        target_height: standardize height
        target_width: minimum width
        **kwargs: passed to preprocess_word_image()
    """
    img = preprocess_word_image(input_path, target_height, target_width, **kwargs)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(output_path, img)
    print(f"✓ Preprocessed: {input_path} → {output_path} ({img.shape})")


# ══════════════════════════════════════════════════════════════
# BATCH PREPROCESSING
# ══════════════════════════════════════════════════════════════

def preprocess_word_pair(
    ref_path: str,
    lc_path: str,
    output_dir: str = "preprocessed",
    target_height: int = 120,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Preprocess both reference and low-confidence words.
    Ensures they're at comparable sizes and quality.
    
    Args:
        ref_path: reference word image path
        lc_path: low-confidence word image path
        output_dir: directory to save preprocessed images
        target_height: standard height for both
    
    Returns:
        (ref_img, lc_img) preprocessed images
    
    Example:
        >>> ref, lc = preprocess_word_pair("ref.jpg", "lc.jpg", target_height=130)
        >>> # Both images now same height, good quality, ready for distortion
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    ref_output = str(Path(output_dir) / "ref_preprocessed.png")
    lc_output = str(Path(output_dir) / "lc_preprocessed.png")
    
    # Preprocess both with same target height
    ref_img = preprocess_word_image(ref_path, target_height=target_height)
    lc_img = preprocess_word_image(lc_path, target_height=target_height)
    
    # Save for inspection if needed
    cv2.imwrite(ref_output, ref_img)
    cv2.imwrite(lc_output, lc_img)
    
    print(f"✓ Ref word: {ref_img.shape}")
    print(f"✓ LC word:  {lc_img.shape}")
    
    return ref_img, lc_img