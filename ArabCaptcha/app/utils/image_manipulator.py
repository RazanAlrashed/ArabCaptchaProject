"""
utils/image_manipulator.py

Applies visual distortions to CAPTCHA images based on bot score / difficulty.
Also creates a composite "stitched" image from two word crops so they appear
connected — this confuses automated segmentation / OCR attacks.

Difficulty ladder
─────────────────
  easy   (score ≥ 0.50): light noise + slight rotation
  medium (score ≥ 0.30): medium noise + warp + rotation + mild blur
  hard   (score  < 0.30): heavy noise + strong warp + rotation +
                           blur + random erasing + perspective tilt
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Literal

Difficulty = Literal["easy", "medium", "hard", "none"]


# ─────────────────────────────────────────────────────────────
# Low-level distortion helpers
# ─────────────────────────────────────────────────────────────

def _add_noise(img: np.ndarray, strength: float) -> np.ndarray:
    """Gaussian noise; strength 0–1."""
    sigma = int(strength * 45) + 5
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    out = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return out


def _rotate(img: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate image with white fill, keeping canvas the same size."""
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    M = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
    return cv2.warpAffine(img, M, (w, h),
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def _elastic_warp(img: np.ndarray, strength: float) -> np.ndarray:
    """Sinusoidal wave distortion."""
    h, w = img.shape[:2]
    amp = max(2, int(strength * h * 0.3))
    freq = 2 * np.pi / max(w, 1)

    map_x = np.zeros((h, w), dtype=np.float32)
    map_y = np.zeros((h, w), dtype=np.float32)
    for y in range(h):
        map_x[y, :] = np.arange(w) + amp * np.sin(freq * y * 3)
        map_y[y, :] = y + amp * np.cos(freq * np.arange(w) * 2)

    map_x = np.clip(map_x, 0, w - 1)
    map_y = np.clip(map_y, 0, h - 1)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def _blur(img: np.ndarray, ksize: int) -> np.ndarray:
    ksize = ksize if ksize % 2 == 1 else ksize + 1
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def _random_erase(img: np.ndarray, n_patches: int = 3) -> np.ndarray:
    """Cover random rectangles with white — breaks pattern recognition."""
    out = img.copy()
    h, w = out.shape[:2]
    for _ in range(n_patches):
        rw = np.random.randint(w // 10, w // 4)
        rh = np.random.randint(h // 8, h // 3)
        x = np.random.randint(0, max(1, w - rw))
        y = np.random.randint(0, max(1, h - rh))
        out[y:y + rh, x:x + rw] = 255
    return out


def _perspective(img: np.ndarray, strength: float) -> np.ndarray:
    """Random perspective tilt."""
    h, w = img.shape[:2]
    d = max(2, int(min(w, h) * strength * 0.15))
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [np.random.randint(0, d), np.random.randint(0, d)],
        [w - np.random.randint(0, d), np.random.randint(0, d)],
        [w - np.random.randint(0, d), h - np.random.randint(0, d)],
        [np.random.randint(0, d), h - np.random.randint(0, d)],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (w, h),
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def _add_grid_lines(img: np.ndarray, n: int = 4, alpha: float = 0.25) -> np.ndarray:
    """
    Overlay faint crossing lines — disrupts segmentation without
    making text unreadable by a human.
    """
    overlay = img.copy()
    h, w = img.shape[:2]
    for _ in range(n):
        x = np.random.randint(0, w)
        cv2.line(overlay, (x, 0), (x + np.random.randint(-20, 20), h),
                 (180, 180, 180), 1)
    for _ in range(n):
        y = np.random.randint(0, h)
        cv2.line(overlay, (0, y), (w, y + np.random.randint(-20, 20)),
                 (180, 180, 180), 1)
    return cv2.addWeighted(img, 1 - alpha, overlay, alpha, 0)


# ─────────────────────────────────────────────────────────────
# Difficulty pipelines
# ─────────────────────────────────────────────────────────────

def apply_easy(img: np.ndarray) -> np.ndarray:
    angle = np.random.uniform(-4, 4)
    img = _rotate(img, angle)
    img = _add_noise(img, 0.15)
    img = _add_grid_lines(img, n=2, alpha=0.10)
    return img


def apply_medium(img: np.ndarray) -> np.ndarray:
    angle = np.random.uniform(-8, 8)
    img = _rotate(img, angle)
    img = _elastic_warp(img, 0.45)
    img = _add_noise(img, 0.35)
    img = _blur(img, 3)
    img = _add_grid_lines(img, n=5, alpha=0.20)
    return img


def apply_hard(img: np.ndarray) -> np.ndarray:
    angle = np.random.uniform(-12, 12)
    img = _rotate(img, angle)
    img = _perspective(img, 0.8)
    img = _elastic_warp(img, 0.70)
    img = _add_noise(img, 0.55)
    img = _blur(img, 5)
    img = _random_erase(img, n_patches=np.random.randint(2, 5))
    img = _add_grid_lines(img, n=8, alpha=0.30)
    return img


PIPELINE = {
    "none":   lambda img: img,          # trusted — no distortion
    "easy":   apply_easy,
    "medium": apply_medium,
    "hard":   apply_hard,
}


def distort_image(img: np.ndarray, difficulty: Difficulty) -> np.ndarray:
    """Apply the appropriate distortion pipeline for the given difficulty."""
    pipeline = PIPELINE.get(difficulty, apply_medium)
    return pipeline(img)


# ─────────────────────────────────────────────────────────────
# Composite (stitched) image
# ─────────────────────────────────────────────────────────────

def _pad_to_height(img: np.ndarray, target_h: int) -> np.ndarray:
    """Vertically center an image on a white canvas of height target_h."""
    h, w = img.shape[:2]
    if h == target_h:
        return img
    canvas = np.full((target_h, w, 3), 255, dtype=np.uint8)
    top = (target_h - h) // 2
    canvas[top:top + h, :w] = img
    return canvas


def _add_join_noise(canvas: np.ndarray, x_split: int, width: int = 15) -> np.ndarray:
    """
    Add a noisy vertical band at the join point so the seam is
    indistinguishable from the rest of the image texture.
    """
    h = canvas.shape[0]
    x0 = max(0, x_split - width // 2)
    x1 = min(canvas.shape[1], x_split + width // 2)
    band = canvas[:, x0:x1].astype(np.float32)
    noise = np.random.normal(0, 18, band.shape)
    canvas[:, x0:x1] = np.clip(band + noise, 0, 255).astype(np.uint8)
    return canvas


def stitch_images(
    img_ref: np.ndarray,
    img_lc: np.ndarray,
    difficulty: Difficulty,
    gap: int = 8,
) -> tuple[np.ndarray, int]:
    """
    Combine two word images side-by-side into one composite canvas.

    Strategy varies by difficulty:
      easy   — clear gap between images
      medium — images touch (gap=0) with join noise
      hard   — images slightly overlap (negative gap) with join noise

    Returns:
        composite     np.ndarray  — the stitched image
        ref_end_x     int         — pixel x where the ref word ends
                                    (used to split answers on the server)
    """
    # Normalise heights
    target_h = max(img_ref.shape[0], img_lc.shape[0])
    ref_norm = _pad_to_height(img_ref, target_h)
    lc_norm  = _pad_to_height(img_lc,  target_h)

    # Adjust gap per difficulty
    if difficulty == "medium":
        gap = 0
    elif difficulty == "hard":
        gap = -max(4, min(img_ref.shape[1], img_lc.shape[1]) // 10)

    if gap >= 0:
        spacer = np.full((target_h, gap, 3), 255, dtype=np.uint8)
        composite = np.hstack([ref_norm, spacer, lc_norm])
    else:
        # Overlap: trim gap pixels from the right of ref and left of lc
        trim = abs(gap)
        ref_trim = ref_norm[:, :max(1, ref_norm.shape[1] - trim)]
        lc_trim  = lc_norm[:, trim:]
        composite = np.hstack([ref_trim, lc_trim])

    ref_end_x = ref_norm.shape[1] + max(gap, 0)

    # Blur the join for medium/hard to hide the seam
    if difficulty in ("medium", "hard"):
        composite = _add_join_noise(composite, ref_end_x)

    return composite, ref_end_x


# ─────────────────────────────────────────────────────────────
# Public entry-point
# ─────────────────────────────────────────────────────────────

def build_captcha_image(
    ref_path: str,
    lc_path: str,
    difficulty: Difficulty,
    output_path: str,
) -> dict:
    """
    Load two word crops, distort them individually, stitch them together,
    and save the composite PNG.

    Returns metadata the challenge service stores so the solver can
    verify answers:
        {
          "composite_path": str,
          "ref_end_x": int,          # split point for server-side answer validation
          "difficulty": str,
        }
    """
    ref_img = cv2.imread(ref_path)
    lc_img  = cv2.imread(lc_path)

    if ref_img is None:
        raise FileNotFoundError(f"Cannot read ref image: {ref_path}")
    if lc_img is None:
        raise FileNotFoundError(f"Cannot read lc image: {lc_path}")

    # 1. Individual distortions
    ref_distorted = distort_image(ref_img, difficulty)
    lc_distorted  = distort_image(lc_img,  difficulty)

    # 2. Stitch
    # الآن نضع الضعيفة (lc) أولاً لتكون على اليسار، والمرجعية (ref) ثانياً لتكون على اليمين
    composite, split_x = stitch_images(lc_distorted, ref_distorted, difficulty)

    # ملاحظة هامة: قيمة ref_end_x الآن تمثل بداية الكلمة المرجعية من جهة اليسار
    # أو نهاية الكلمة الضعيفة. سنقوم بتخزينها كإحداثي للفصل.
    ref_end_x = split_x
    
    # 3. One final pass of noise over the whole composite (medium/hard)
    if difficulty == "medium":
        composite = _add_noise(composite, 0.10)
    elif difficulty == "hard":
        composite = _add_noise(composite, 0.20)

    # 4. Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(output_path, composite)

    return {
        "composite_path": output_path,
        "ref_end_x": ref_end_x,
        "difficulty": difficulty,
    }