"""
services/captcha_image_service.py

Complete CAPTCHA image generation pipeline:
  1. Load raw word crops (possibly low-quality scans)
  2. Preprocess (upscale, enhance, denoise, normalize)
  3. Apply difficulty-based distortions
  4. Stitch into composite
  5. Save final CAPTCHA PNG

This ensures consistent, high-quality, readable CAPTCHA images
regardless of input scan quality.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Dict

# Assuming these are in your project structure
from app.utils.image_preprocessor import preprocess_word_image
from app.utils.image_manipulator import (
    distort_image,
    stitch_images,
    _add_join_noise,
    _pad_to_height,
    Difficulty,
)


def generate_captcha_composite(
    ref_path: str,
    lc_path: str,
    difficulty: Difficulty,
    output_path: str,
    target_word_height: int = 130,
    target_word_width: int = 220,
    preprocess_enabled: bool = True,
) -> Dict[str, any]:
    """
    Full pipeline: raw images → preprocessed → distorted → composite → saved PNG.
    
    Pipeline stages
    ────────────────
      1. Load raw word crops from disk
      2. Preprocess (upscale, enhance contrast, denoise, normalize size)
      3. Apply per-word distortion based on difficulty
      4. Stitch side-by-side: [lc_distorted] | [gap] | [ref_distorted]
         (lc on left, ref on right — Arabic reading order)
      5. Save composite PNG
    
    Args:
        ref_path:            path to reference word crop (should be clear/typed)
        lc_path:             path to low-confidence word crop (maybe scan)
        difficulty:          "easy", "medium", "hard", or "none"
        output_path:         where to save the final composite PNG
        target_word_height:  standardize both words to this height (px)
        target_word_width:   minimum width for each word (px)
        preprocess_enabled:  if False, skip enhancement (use raw images)
    
    Returns:
        {
          "composite_path": str,    # path to saved PNG
          "ref_end_x": int,         # pixel x where lc ends / ref begins
          "difficulty": str,
          "ref_size_before": (h, w),
          "ref_size_after": (h, w),
          "lc_size_before": (h, w),
          "lc_size_after": (h, w),
        }
    
    Example:
        >>> result = generate_captcha_composite(
        ...     "uploads/ref_scan.jpg",
        ...     "uploads/lc_scan.jpg",
        ...     "hard",
        ...     "assets/captcha/challenge_123.png"
        ... )
        >>> print(f"Composite saved: {result['composite_path']}")
        >>> print(f"Difficulty: {result['difficulty']}")
    """
    # ── Load raw images ──────────────────────────────────────────────
    ref_img = cv2.imread(ref_path)
    lc_img = cv2.imread(lc_path)
    
    if ref_img is None:
        raise FileNotFoundError(f"Cannot read reference image: {ref_path}")
    if lc_img is None:
        raise FileNotFoundError(f"Cannot read low-confidence image: {lc_path}")
    
    ref_size_before = ref_img.shape[:2]
    lc_size_before = lc_img.shape[:2]
    
    # ── Preprocess ───────────────────────────────────────────────────
    if preprocess_enabled:
        # Enhance low-quality scans: upscale, boost contrast, denoise
        ref_img = preprocess_word_image(
            ref_path,
            target_height=target_word_height,
            target_width=target_word_width,
            upscale_small=True,
            enhance_contrast=True,
            denoise=True,
        )
        lc_img = preprocess_word_image(
            lc_path,
            target_height=target_word_height,
            target_width=target_word_width,
            upscale_small=True,
            enhance_contrast=True,
            denoise=True,
        )
    else:
        # Just normalize size (minimal processing)
        from app.utils.image_preprocessor import _normalize_size, _pad_to_width
        ref_img = _normalize_size(ref_img, target_height=target_word_height)
        lc_img = _normalize_size(lc_img, target_height=target_word_height)
        ref_img = _pad_to_width(ref_img, target_width=target_word_width)
        lc_img = _pad_to_width(lc_img, target_width=target_word_width)
    
    ref_size_after = ref_img.shape[:2]
    lc_size_after = lc_img.shape[:2]
    
    # ── Apply per-word distortion ────────────────────────────────────
    ref_distorted = distort_image(ref_img, difficulty)
    lc_distorted = distort_image(lc_img, difficulty)
    
    # ── Stitch composite ─────────────────────────────────────────────
    # Layout: [lc_distorted] | [gap] | [ref_distorted]
    #         (left)         (gap)   (right - Arabic order)
    composite, ref_start_x = stitch_images(ref_distorted, lc_distorted, difficulty)
    
    # ── Final light noise (optional, for medium/hard) ────────────────
    if difficulty == "medium":
        from app.utils.image_manipulator import _subtle_noise
        composite = _subtle_noise(composite, 0.06)
    
    # ── Save ─────────────────────────────────────────────────────────
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(output_path, composite)
    
    return {
        "composite_path": output_path,
        "ref_end_x": ref_start_x,
        "difficulty": difficulty,
        "ref_size_before": ref_size_before,
        "ref_size_after": ref_size_after,
        "lc_size_before": lc_size_before,
        "lc_size_after": lc_size_after,
    }


def batch_generate_captchas(
    word_pairs: list,
    output_dir: str = "assets/captcha",
    difficulty: Difficulty = "medium",
    **kwargs
) -> list:
    """
    Generate multiple CAPTCHA composites in batch.
    
    Args:
        word_pairs: list of (ref_path, lc_path, challenge_id) tuples
        output_dir: directory to save all composites
        difficulty: apply this difficulty to all
        **kwargs: passed to generate_captcha_composite()
    
    Returns:
        list of result dicts
    
    Example:
        >>> pairs = [
        ...     ("ref1.jpg", "lc1.jpg", "chall_001"),
        ...     ("ref2.jpg", "lc2.jpg", "chall_002"),
        ... ]
        >>> results = batch_generate_captchas(pairs, difficulty="hard")
    """
    results = []
    for ref_path, lc_path, challenge_id in word_pairs:
        output_path = str(Path(output_dir) / f"{challenge_id}.png")
        try:
            result = generate_captcha_composite(
                ref_path,
                lc_path,
                difficulty,
                output_path,
                **kwargs
            )
            results.append(result)
            print(f"✓ {challenge_id}: {result['ref_size_before']} → {result['ref_size_after']}")
        except Exception as e:
            print(f"✗ {challenge_id}: {e}")
            results.append({
                "challenge_id": challenge_id,
                "error": str(e),
            })
    
    return results