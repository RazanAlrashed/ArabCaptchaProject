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
'''
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
'''

"""
utils/image_manipulator.py

Applies visual distortions to CAPTCHA images based on bot score / difficulty.
Also creates a composite "stitched" image from two word crops so they appear
connected — this confuses automated segmentation / OCR attacks.

Difficulty ladder
─────────────────
  easy   (score ≥ 0.50): slight rotation + light dots + light adversarial noise
  medium (score ≥ 0.30): rotation + wave/elastic warp + random lines + medium noise + blur
  hard   (score  < 0.30): strong rotation + perspective + heavy wave + elastic warp +
                          dense lines & dots + random erasing + high adversarial noise + blur
"""

"""
utils/image_manipulator.py

Applies visual distortions to CAPTCHA images based on bot score / difficulty.
Also creates a composite "stitched" image from two word crops so they appear
connected — this confuses automated segmentation / OCR attacks.

CRITICAL: Input images are REAL Arabic text:
  • Typed text (clear, consistent letterforms)
  • Handwritten text (variable stroke, authentic patterns)
  • Scanned documents (potential noise, resolution variations)

Distortion philosophy:
  ✓ Rotate/warp letterforms → breaks CNN/ML detectors
  ✗ DON'T remove strokes → humans need them to read
  ✓ Add noise that fades at distance → invisible to humans, breaks pixel-level OCR
  ✗ DON'T add so much noise it becomes static → unreadable
  ✓ Disrupt segmentation points (joins) → prevents word/letter splitting
  ✗ DON'T blur so much letters merge → humans can't distinguish

Difficulty ladder (human-readable optimized)
──────────────────────────────────────────
  none   (score ≥ 0.80): no distortion
  easy   (score ≥ 0.50): ✓ readable by humans, stops simple OCR
  medium (score ≥ 0.30): ✓ still readable but requires focus
  hard   (score  < 0.30): ✓ readable only with Arabic knowledge
                           ✗ impossible for non-native readers or bots
"""
"""
utils/image_manipulator.py

Applies visual distortions to CAPTCHA images based on bot score / difficulty.
Also creates a composite "stitched" image from two word crops so they appear
connected — this confuses automated segmentation / OCR attacks.

CRITICAL: Input images are REAL Arabic text:
  • Typed text (clear, consistent letterforms)
  • Handwritten text (variable stroke, authentic patterns)
  • Scanned documents (potential noise, resolution variations)

Distortion philosophy:
  ✓ Rotate/warp letterforms → breaks CNN/ML detectors
  ✗ DON'T remove strokes → humans need them to read
  ✓ Add noise that fades at distance → invisible to humans, breaks pixel-level OCR
  ✗ DON'T add so much noise it becomes static → unreadable
  ✓ Disrupt segmentation points (joins) → prevents word/letter splitting
  ✗ DON'T blur so much letters merge → humans can't distinguish

Difficulty ladder (human-readable optimized)
──────────────────────────────────────────
  none   (score ≥ 0.80): no distortion
  easy   (score ≥ 0.50): ✓ readable by humans, stops simple OCR
  medium (score ≥ 0.30): ✓ still readable but requires focus
  hard   (score  < 0.30): ✓ readable only with Arabic knowledge
                           ✗ impossible for non-native readers or bots
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Literal

Difficulty = Literal["easy", "medium", "hard", "none"]


# ══════════════════════════════════════════════════════════════
# HELPER PRIMITIVES
# Design: maximize bot confusion while preserving Arabic letterforms
# ══════════════════════════════════════════════════════════════

def _smart_rotate(img: np.ndarray, angle_deg: float) -> np.ndarray:
    """
    Rotation breaks CNN alignment assumptions.
    Used at all levels, with angle increasing per difficulty.
    Key: use white padding (not black) so background doesn't interfere.
    """
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle_deg, 1.0)
    return cv2.warpAffine(img, M, (w, h),
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=(255, 255, 255))


def _row_wave(img: np.ndarray, amplitude: float = 8.0, period: float = 50.0) -> np.ndarray:
    """
    Horizontal wave: each row shifts left/right by amplitude * sin(row_index).
    Effect: baseline of Arabic letters warps, confusing sequence models.
    Humans read around the warp; OCR can't.
    Amplitude small enough: letters remain intact, just displaced.
    """
    rows, cols = img.shape[:2]
    distorted = np.zeros_like(img)
    for i in range(rows):
        shift = int(amplitude * np.sin(2 * np.pi * i / period))
        distorted[i] = np.roll(img[i], shift, axis=0)
    return distorted


def _elastic_warp(img: np.ndarray, strength: float) -> np.ndarray:
    """
    2-axis sinusoidal remap via cv2.remap.
    Effect: twists the image nonlinearly → breaks geometric assumptions in CNNs.
    Humans (especially fluent Arabic readers) can still parse distorted letters.
    """
    h, w = img.shape[:2]
    amp  = max(1, int(strength * h * 0.25))  # slightly smaller for readability
    freq = 2 * np.pi / max(w, 1)

    map_x = np.zeros((h, w), dtype=np.float32)
    map_y = np.zeros((h, w), dtype=np.float32)
    for y in range(h):
        map_x[y, :] = np.arange(w) + amp * np.sin(freq * y * 2.5)
        map_y[y, :] = y            + amp * np.cos(freq * np.arange(w) * 1.5)

    map_x = np.clip(map_x, 0, w - 1)
    map_y = np.clip(map_y, 0, h - 1)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT,
                     borderValue=(255, 255, 255))


def _smart_blur(img: np.ndarray, ksize: int) -> np.ndarray:
    """
    Gaussian blur: small kernel (3x3, 5x5).
    Effect: softens sharp edges that CNN detectors use as features.
    At ksize=3: humans still see letters clearly.
    At ksize=5: requires focus, but readable.
    Beyond ksize=5: starts to merge letters → bad for humans.
    """
    ksize = ksize if ksize % 2 == 1 else ksize + 1
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def _subtle_noise(img: np.ndarray, intensity: float) -> np.ndarray:
    """
    Gaussian noise: fine-grained but not overwhelming.
    Effect at intensity=0.08: invisible to humans, breaks pixel-level OCR.
    Effect at intensity=0.15: slightly visible to humans at close range,
                              clearly breaks ML feature extractors.
    Effect at intensity=0.25: visible texture, but letters still readable.
    Beyond 0.25: becomes visual static → bad for humans.
    """
    sigma = int(intensity * 20) + 2
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _faint_dots(img: np.ndarray, num_dots: int) -> np.ndarray:
    """
    Sparse random pixel scatter (much lighter than test.py).
    Effect: doesn't visibly degrade text, but adds entropy to break
            template matching and pixel-perfect attacks.
    """
    out = img.copy()
    h, w = out.shape[:2]
    xs = np.random.randint(0, w, num_dots)
    ys = np.random.randint(0, h, num_dots)
    # Use grey tones (not full random) to keep noise subtle
    greys = np.random.randint(100, 200, (num_dots,))
    for x, y, grey in zip(xs, ys, greys):
        out[y, x] = [grey, grey, grey]
    return out


def _light_lines(img: np.ndarray, num_lines: int, grey_only: bool = True) -> np.ndarray:
    """
    Random lines: LIGHT version to avoid visual clutter.
    grey_only=True: subtle grey lines (easy/medium).
    grey_only=False: occasional colored lines (hard only, sparse).
    
    Effect: disrupts clean-crop segmentation without making text unreadable.
    Humans ignore random lines when reading; OCR treats them as noise.
    """
    out = img.copy()
    h, w = out.shape[:2]
    for _ in range(num_lines):
        x1 = int(np.random.randint(0, w))
        y1 = int(np.random.randint(0, h))
        x2 = int(np.random.randint(0, w))
        y2 = int(np.random.randint(0, h))
        
        if grey_only or np.random.rand() > 0.7:
            # Grey line (most of the time)
            g = int(np.random.randint(150, 200))
            color = (g, g, g)
        else:
            # Occasional colored line
            color = tuple(int(c) for c in np.random.randint(80, 200, 3).tolist())
        
        thickness = 1  # keep thin
        cv2.line(out, (x1, y1), (x2, y2), color, thickness)
    return out


def _minimal_erase(img: np.ndarray, n_patches: int = 1) -> np.ndarray:
    """
    Random white rectangle patches: MINIMAL version.
    Only 1-2 small patches, unlike test.py's aggressive random_erase.
    
    Effect at 1 patch (hard): removes a small portion of 1-2 letters,
                              but context+pattern still visible.
    Effect at 2 patches (hard): might impact readability if placed badly.
                              Falls back to context for humans.
    
    Key: small patches (h/12-h/4 range), not huge erasures.
    """
    out = img.copy()
    h, w = out.shape[:2]
    for _ in range(n_patches):
        rw = int(np.random.randint(max(1, w // 12), max(2, w // 5)))
        rh = int(np.random.randint(max(1, h // 10), max(2, h // 4)))
        x = int(np.random.randint(0, max(1, w - rw)))
        y = int(np.random.randint(0, max(1, h - rh)))
        out[y:y + rh, x:x + rw] = 255
    return out


def _mild_perspective(img: np.ndarray, strength: float) -> np.ndarray:
    """
    Perspective warp: MILD version.
    strength < 0.5 keeps the warp visually subtle.
    
    Effect: 3D tilt confuses alignment-sensitive models (text lines).
    At strength=0.4: tilt is noticeable but not disorienting to humans.
    At strength=0.6+: starts to look like viewing from extreme angle.
    """
    h, w = img.shape[:2]
    d = max(1, int(min(w, h) * strength * 0.10))
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [np.random.randint(0, d),         np.random.randint(0, d)],
        [w - np.random.randint(0, d),     np.random.randint(0, d)],
        [w - np.random.randint(0, d), h - np.random.randint(0, d)],
        [np.random.randint(0, d),     h - np.random.randint(0, d)],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (w, h),
                               borderMode=cv2.BORDER_CONSTANT,
                               borderValue=(255, 255, 255))


def _grid_underlay(img: np.ndarray, n: int = 3, alpha: float = 0.15) -> np.ndarray:
    """
    Faint axis-aligned grid lines (more subtle than test.py).
    Effect: light visual texture that humans ignore, breaks clean-crop
            assumptions in segmentation algorithms.
    """
    overlay = img.copy()
    h, w = img.shape[:2]
    
    # Vertical lines
    for _ in range(n):
        x = int(np.random.randint(w // 4, 3 * w // 4))
        cv2.line(overlay, (x, 0), (x + int(np.random.randint(-10, 10)), h),
                 (200, 200, 200), 1)
    
    # Horizontal lines
    for _ in range(n):
        y = int(np.random.randint(h // 4, 3 * h // 4))
        cv2.line(overlay, (0, y), (w, y + int(np.random.randint(-10, 10))),
                 (200, 200, 200), 1)
    
    return cv2.addWeighted(img, 1 - alpha, overlay, alpha, 0)


# ══════════════════════════════════════════════════════════════
# DIFFICULTY PIPELINES
# Each calibrated for Arabic text readability
# ══════════════════════════════════════════════════════════════

def apply_easy(img: np.ndarray) -> np.ndarray:
    """
    Applied to: mostly-human-looking users (score ≥ 0.50).
    Goal: prevent simple OCR attacks without annoying the user.

    Techniques:
      ✓ Rotation ±2°         → minimal tilt (barely noticeable)
      ✓ Subtle noise 0.08    → invisible to humans, breaks pixel-OCR
      ✓ Faint dots 50        → sparse entropy, unnoticeable
      ✓ Grid 2 lines         → soft visual texture
    
    Visual effect:
      At arm's length: looks like the original
      Under examination: clear letter shapes, readable
    """
    img = _smart_rotate(img, float(np.random.uniform(-2, 2)))
    img = _subtle_noise(img, 0.08)
    img = _faint_dots(img, num_dots=50)
    img = _grid_underlay(img, n=2, alpha=0.12)
    return img


def apply_medium(img: np.ndarray) -> np.ndarray:
    """
    Applied to: suspicious users (score 0.30-0.50).
    Goal: defeat ML models while staying readable by native Arabic readers.
    
    CRITICAL: Arabic text is sensitive to rotation and perspective.
    No aggressive geometric distortions that merge letter shapes.

    Techniques:
      ✓ Rotation ±3°           → subtle, Arabic ligatures still visible
      ✓ Row wave amp=5         → warps baseline, breaks line segmentation
      ✓ Elastic warp 0.25      → mild nonlinear twist (NOT aggressive)
      ✓ Light lines 3          → subtle layout noise
      ✓ Subtle noise 0.15      → visible texture, breaks feature maps
      ✓ Faint dots 120         → sparse scatter
      ✓ Blur k=3               → softens sharp edges
      ✓ Grid 3 lines           → moderate texture
    
    Visual effect:
      Quick glance: requires focus to read
      Native reader (5 seconds): fully readable
      Non-native reader: might struggle slightly
      OCR system: fails (segmentation broken by wave)
    """
    img = _smart_rotate(img, float(np.random.uniform(-3, 3)))
    img = _row_wave(img, amplitude=5.0, period=50.0)
    img = _elastic_warp(img, strength=0.25)  # reduced from 0.35
    img = _light_lines(img, num_lines=3, grey_only=True)
    img = _subtle_noise(img, 0.15)
    img = _faint_dots(img, num_dots=120)
    img = _smart_blur(img, 3)
    img = _grid_underlay(img, n=3, alpha=0.14)
    return img


def apply_hard(img: np.ndarray) -> np.ndarray:
    """
    Applied to: likely-bot users (score < 0.30).
    Goal: create maximum confusion for ML without making it unreadable.
    
    CRITICAL: Arabic text - NO excessive rotation or perspective.
    Instead: use wave + elastic warp which break line segmentation
    without making the text unreadable.

    Techniques:
      ✓ Rotation ±4°           → minimal tilt (NOT ±10°, too much for Arabic)
      ✓ Mild perspective 0.15  → very subtle 3D (NOT 0.40, too aggressive)
      ✓ Row wave amp=10        → aggressive baseline warp (main defense)
      ✓ Elastic warp 0.50      → strong nonlinear bend (main defense)
      ✓ Light lines 6          → more false edges
      ✓ Subtle noise 0.22      → visible texture
      ✓ Faint dots 250         → more scatter
      ✓ Minimal erase 1        → removes small piece of 1 letter
      ✓ Blur k=5               → stronger edge softening
      ✓ Grid 4 lines           → denser grid
    
    Visual effect:
      Quick glance: looks distorted but baseline visible
      Native reader (10-15 seconds): still readable via context + letter patterns
      Non-native reader: very difficult without linguistic knowledge
      OCR system: fails (wave breaks line segmentation, elastic breaks coordinates)
    
    Key insight: Arabic OCR relies heavily on baseline + letter connections.
    Wave distortions break this completely, even without aggressive rotation.
    Don't tilt the page too much — keep the letters themselves intact!
    """
    img = _smart_rotate(img, float(np.random.uniform(-2, 2)))  # reduced from ±4 to ±2
    img = _mild_perspective(img, strength=0.15)  # reduced from 0.40
    img = _row_wave(img, amplitude=10.0, period=55.0)  # kept strong (main defense)
    img = _elastic_warp(img, strength=0.50)  # kept strong (main defense)
    img = _light_lines(img, num_lines=6, grey_only=False)
    img = _subtle_noise(img, 0.22)
    img = _faint_dots(img, num_dots=250)
    img = _minimal_erase(img, n_patches=1)
    img = _smart_blur(img, 5)
    img = _grid_underlay(img, n=4, alpha=0.16)
    return img


PIPELINE: dict = {
    "none":   lambda img: img,   # trusted user
    "easy":   apply_easy,
    "medium": apply_medium,
    "hard":   apply_hard,
}


def distort_image(img: np.ndarray, difficulty: Difficulty) -> np.ndarray:
    """Apply the appropriate distortion pipeline for the given difficulty."""
    fn = PIPELINE.get(difficulty, apply_medium)
    return fn(img)


# ══════════════════════════════════════════════════════════════
# COMPOSITE (STITCHED) IMAGE
# ══════════════════════════════════════════════════════════════

def _pad_to_height(img: np.ndarray, target_h: int) -> np.ndarray:
    """Vertically centre an image on a white canvas of height target_h."""
    h, w = img.shape[:2]
    if h == target_h:
        return img
    canvas = np.full((target_h, w, 3), 255, dtype=np.uint8)
    top = (target_h - h) // 2
    canvas[top:top + h, :w] = img
    return canvas


def _add_join_noise(canvas: np.ndarray, x_split: int, width: int = 12) -> np.ndarray:
    """
    Noise band at the seam: makes the join point visually indistinguishable.
    Prevents a segmentation model from finding the split point.
    """
    x0 = max(0, x_split - width // 2)
    x1 = min(canvas.shape[1], x_split + width // 2)
    band = canvas[:, x0:x1].astype(np.float32)
    noise = np.random.normal(0, 15, band.shape)  # slightly reduced from 18
    canvas[:, x0:x1] = np.clip(band + noise, 0, 255).astype(np.uint8)
    return canvas


def stitch_images(
    img_ref: np.ndarray,
    img_lc: np.ndarray,
    difficulty: Difficulty,
    gap: int = 8,
) -> tuple[np.ndarray, int]:
    """
    Stitch two distorted word images side-by-side.
    
    Arabic reading order (right to left):
      Layout: [lc_word] | [gap] | ref_word (RIGHT SIDE ALWAYS)
    
    The reference word MUST be on the RIGHT because:
      • Arabic text reads right → left
      • User reads reference word first (it's verified, trusted)
      • Low-conf word is on left (being crowdsourced)
    
    Gap strategy:
      easy   → 8 px clear gap (words visibly separate)
      medium → 0 px touch (but seam is noisy, not visually jarring)
      hard   → -4 to -6 px overlap (words appear to merge slightly)
    """
    target_h = max(img_ref.shape[0], img_lc.shape[0])
    ref_norm = _pad_to_height(img_ref, target_h)
    lc_norm = _pad_to_height(img_lc, target_h)

    if difficulty == "medium":
        gap = 0
    elif difficulty == "hard":
        gap = -max(4, min(img_ref.shape[1], img_lc.shape[1]) // 12)

    if gap >= 0:
        spacer = np.full((target_h, gap, 3), 255, dtype=np.uint8)
        # lc_word | gap | ref_word (RIGHT SIDE - Arabic order)
        composite = np.hstack([lc_norm, spacer, ref_norm])
    else:
        trim = abs(gap)
        lc_trim = lc_norm[:, :max(1, lc_norm.shape[1] - trim)]
        ref_trim = ref_norm[:, trim:]
        # lc overlaps slightly with ref
        composite = np.hstack([lc_trim, ref_trim])

    # Split point: where lc ends and ref begins (reading left to right in code)
    ref_start_x = lc_norm.shape[1] + max(gap, 0)

    if difficulty in ("medium", "hard"):
        composite = _add_join_noise(composite, ref_start_x)

    return composite, ref_start_x


# ══════════════════════════════════════════════════════════════
# PUBLIC ENTRY-POINT
# ══════════════════════════════════════════════════════════════

def build_captcha_image(
    ref_path: str,
    lc_path: str,
    difficulty: Difficulty,
    output_path: str,
) -> dict:
    """
    Full pipeline: load → distort each → stitch → save.
    
    Optimized for Arabic readability + bot defense.
    
    Layout (as displayed to user - Arabic right-to-left):
      [كلمة الضعيفة] | [فجوة] | [كلمة المرجعية]
       (يسار)        (gap)    (يمين - دائماً على اليمين)
    
    Returns
    -------
    {
      "composite_path": str,
      "ref_end_x": int,  # pixel x where low-conf word ends and ref word begins
      "difficulty": str,
    }
    """
    ref_img = cv2.imread(ref_path)
    lc_img = cv2.imread(lc_path)

    if ref_img is None:
        raise FileNotFoundError(f"Cannot read ref image: {ref_path}")
    if lc_img is None:
        raise FileNotFoundError(f"Cannot read lc image: {lc_path}")

    # 1. Per-word distortion
    ref_distorted = distort_image(ref_img, difficulty)
    lc_distorted = distort_image(lc_img, difficulty)

    # 2. Stitch: lc on left, ref on RIGHT (Arabic reading order)
    composite, ref_start_x = stitch_images(ref_distorted, lc_distorted, difficulty)

    # 3. No aggressive final pass — keep the composite readable
    # Light medium level gets minimal cleanup
    if difficulty == "medium":
        composite = _subtle_noise(composite, 0.06)  # very subtle
    # Hard level stays as-is; per-word distortions are sufficient

    # 4. Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(output_path, composite)

    return {
        "composite_path": output_path,
        "ref_end_x": ref_start_x,  # pixel boundary between lc and ref
        "difficulty": difficulty,
    }