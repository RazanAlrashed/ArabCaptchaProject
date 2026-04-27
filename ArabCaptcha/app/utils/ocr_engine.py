'''
import cv2
import numpy as np
from pathlib import Path
from paddleocr import PaddleOCR
import os

# 1. إعدادات البيئة لضمان الاستقرار على ويندوز
os.environ['FLAGS_enable_onednn'] = '0'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

# 2. تعريف المسارات (تأكدي أن هذه المسارات تتوافق مع مشروعك)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_WORDS_DIR = BASE_DIR / "assets" / "words"

# 3. تعريف المحرك (OCR Engine)
# أضفنا show_log=False لتقليل الزحام في الـ Terminal
ocr_engine = PaddleOCR(
    lang='ar', 
    det_db_unclip_ratio=1.2, 
    enable_mkldnn=False)

def detect_arabic_words(image_path: str, session_id: str):
    # تشغيل الـ OCR
    result = ocr_engine.ocr(image_path)
    
    if not result:
        return []

    image = cv2.imread(image_path)
    if image is None:
        return []

    words_data = []

    # استخراج البيانات بناءً على الهيكل الجديد الذي ظهر في الـ Terminal
    # نلاحظ أن البيانات موجودة في result[0]['dt_polys'] أو result[0]['rec_boxes']
    data = result[0]
    boxes = data.get('dt_polys', [])

    for idx, box in enumerate(boxes):
        try:
            # تحويل البوكس إلى مصفوفة numpy
            pts = np.array(box).astype(np.float32)
            
            # حساب الإحداثيات
            x_min = max(0, int(pts[:, 0].min()))
            y_min = max(0, int(pts[:, 1].min()))
            x_max = min(image.shape[1], int(pts[:, 0].max()))
            y_max = min(image.shape[0], int(pts[:, 1].max()))

            # قص الكلمة
            word_img = image[y_min:y_max, x_min:x_max]
            
            if word_img.size > 0:
                word_filename = f"word_{idx:03d}.png"
                
                # إنشاء المسار
                session_dir = ASSETS_WORDS_DIR / session_id
                session_dir.mkdir(parents=True, exist_ok=True)
                
                save_path = session_dir / word_filename
                cv2.imwrite(str(save_path), word_img)
                
                words_data.append({
                    "id": idx,
                    "path": f"/assets/words/{session_id}/{word_filename}"
                })
        except Exception as e:
            print(f"⚠️ Error cutting word {idx}: {e}")

    return words_data
'''
'''
utils/ocr_engine.py

Detects Arabic words using PaddleOCR.
Now accepts start_index so multi-page PDFs get unique word IDs.
Handles both old (list-of-tuples) and new (dict) PaddleOCR result formats.

import cv2
import numpy as np
from pathlib import Path
import os

os.environ['FLAGS_enable_onednn'] = '0'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

BASE_DIR         = Path(__file__).resolve().parent.parent.parent
ASSETS_WORDS_DIR = BASE_DIR / "assets" / "words"

_ocr_engine = None


def _get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            lang='ar',
            det_db_unclip_ratio=1.2,
            enable_mkldnn=False,
        )
    return _ocr_engine


def _extract_boxes(result) -> list:
    """Normalize PaddleOCR output across v2.x (list) and v3.x (dict)."""
    if not result:
        return []

    first = result[0]

    # New dict format (v3+)
    if isinstance(first, dict):
        boxes = first.get("dt_polys", [])
        texts = first.get("rec_texts", [""] * len(boxes))
        confs = first.get("rec_scores", [0.0] * len(boxes))
        return list(zip(boxes, texts, confs))

    # Old list format (v2.x)
    if isinstance(first, list):
        items = []
        for item in first:
            if item is None:
                continue
            try:
                box  = item[0]
                text = item[1][0] if item[1] else ""
                conf = float(item[1][1]) if item[1] else 0.0
                items.append((box, text, conf))
            except (IndexError, TypeError):
                continue
        return items

    return []


def detect_arabic_words(image_path: str, session_id: str, start_index: int = 0) -> list:
    """
    Run OCR, crop each word region, save PNGs.

    Args:
        image_path:  path to the image file
        session_id:  used to organise saved crops
        start_index: offset for word IDs (use for multi-page PDFs)

    Returns:
        list of {"id", "path"} — same structure as before so
        the existing dashboard JS and Colab flow work unchanged.
    """
    image = cv2.imread(image_path)
    if image is None:
        print(f"⚠️ Cannot read: {image_path}")
        return []

    try:
        result = _get_engine().ocr(image_path)
    except Exception as e:
        print(f"⚠️ OCR error: {e}")
        return []

    boxes = _extract_boxes(result)
    if not boxes:
        print(f"⚠️ No words in: {image_path}")
        return []

    session_dir = ASSETS_WORDS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    words_data = []

    for local_idx, (box, ocr_text, confidence) in enumerate(boxes):
        global_idx = start_index + local_idx
        try:
            pts   = np.array(box).astype(np.float32)
            x_min = max(0, int(pts[:, 0].min()))
            y_min = max(0, int(pts[:, 1].min()))
            x_max = min(image.shape[1], int(pts[:, 0].max()))
            y_max = min(image.shape[0], int(pts[:, 1].max()))

            if x_max <= x_min or y_max <= y_min:
                continue

            word_img = image[y_min:y_max, x_min:x_max]
            if word_img.size == 0:
                continue

            filename  = f"word_{global_idx:03d}.png"
            save_path = session_dir / filename
            cv2.imwrite(str(save_path), word_img)

            words_data.append({
                "id":   global_idx,
                "path": f"/assets/words/{session_id}/{filename}",
            })

        except Exception as e:
            print(f"⚠️ Word {global_idx} error: {e}")

    print(f"✅ {len(words_data)} words from {image_path}")
    return words_data
'''


"""
utils/ocr_engine.py

Arabic word detection using PaddleOCR.

Fixes applied vs original:
  1. Handles both PaddleOCR result formats (v2 list / v3 dict)
  2. Image preprocessing: denoise + contrast + binarize before OCR
  3. det_db_unclip_ratio raised to 1.8 for connected Arabic text
  4. Padding added around each crop so letters aren't clipped
  5. Minimum crop size filter — skips noise/blank detections
  6. start_index param for multi-page PDF word ID continuity
"""
"""
utils/ocr_engine.py

Arabic word detection with two strategies:
  A — Vector PDF: extract directly from PDF metadata (pixel-perfect)
  B — Scanned image / image-based PDF: preprocess + PaddleOCR

Each detected word now includes page_image_path so the dashboard
crop editor can show the full page instead of the tiny crop.
"""
import cv2
import numpy as np
from pathlib import Path
import os

os.environ['FLAGS_enable_onednn'] = '0'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

BASE_DIR         = Path(__file__).resolve().parent.parent.parent
ASSETS_WORDS_DIR = BASE_DIR / "assets" / "words"

MIN_WORD_WIDTH  = 15
MIN_WORD_HEIGHT = 10
CROP_PADDING    = 4

_ocr_engine = None


# ─────────────────────────────────────────────────────────────
# STRATEGY A — Vector PDF
# ─────────────────────────────────────────────────────────────

def is_vector_pdf(pdf_path: str) -> bool:
    try:
        import fitz
        doc  = fitz.open(pdf_path)
        text = "".join(page.get_text("text").strip() for page in doc)
        doc.close()
        return len(text) >= 10
    except Exception:
        return False


def extract_words_from_vector_pdf(
    pdf_path: str,
    session_id: str,
    start_index: int = 0,
    scale: float = 3.0,
) -> list:
    """
    Extract every word from a vector PDF using PyMuPDF word-level boxes.
    Each word dict includes page_image_path (the full rendered page PNG)
    so the crop editor can show the full page.
    """
    import fitz

    doc         = fitz.open(pdf_path)
    session_dir = ASSETS_WORDS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    all_words  = []
    global_idx = start_index

    for page_num, page in enumerate(doc):
        # Render full page — save it so the crop editor can load it
        pix            = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        page_img_file  = session_dir / f"page{page_num}_full.png"
        pix.save(str(page_img_file))
        page_img_url   = f"/assets/words/{session_id}/page{page_num}_full.png"

        img = cv2.imread(str(page_img_file))
        if img is None:
            continue

        h, w   = img.shape[:2]
        pdf_words = page.get_text("words")

        for word_data in pdf_words:
            x0, y0, x1, y1, text = word_data[:5]
            if not text.strip():
                continue

            ix0 = max(0, int(x0 * scale) - CROP_PADDING)
            iy0 = max(0, int(y0 * scale) - CROP_PADDING)
            ix1 = min(w, int(x1 * scale) + CROP_PADDING)
            iy1 = min(h, int(y1 * scale) + CROP_PADDING)

            if (ix1 - ix0) < MIN_WORD_WIDTH or (iy1 - iy0) < MIN_WORD_HEIGHT:
                continue

            crop = img[iy0:iy1, ix0:ix1]
            if crop.size == 0:
                continue

            filename  = f"word_{global_idx:03d}.png"
            cv2.imwrite(str(session_dir / filename), crop)

            all_words.append({
                "id":              global_idx,
                "path":            f"/assets/words/{session_id}/{filename}",
                "page_image_path": page_img_url,   # ← full page for crop editor
                "page":            page_num + 1,
                # Store original coords so editor can pre-select the word
                "box": {
                    "x": ix0, "y": iy0,
                    "w": ix1 - ix0, "h": iy1 - iy0,
                },
            })
            global_idx += 1

    doc.close()
    print(f"✅ Vector PDF: {len(all_words)} words from {Path(pdf_path).name}")
    return all_words


# ─────────────────────────────────────────────────────────────
# STRATEGY B — PaddleOCR for scanned images
# ─────────────────────────────────────────────────────────────

def _get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            lang='ar',
            det_db_unclip_ratio=1.8,
            det_db_thresh=0.3,
            det_db_box_thresh=0.4,
            enable_mkldnn=False,
            use_angle_cls=True,
        )
    return _ocr_engine


def _preprocess(image: np.ndarray) -> np.ndarray:
    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray     = clahe.apply(gray)
    denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    binary   = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, blockSize=15, C=8,
    )
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def _extract_boxes(result) -> list:
    if not result:
        return []
    first = result[0]
    if isinstance(first, dict):
        boxes = first.get("dt_polys", [])
        texts = first.get("rec_texts", [""] * len(boxes))
        confs = first.get("rec_scores", [0.0] * len(boxes))
        return list(zip(boxes, texts, confs))
    if isinstance(first, list):
        items = []
        for item in first:
            if item is None:
                continue
            try:
                items.append((item[0], item[1][0], float(item[1][1])))
            except (IndexError, TypeError):
                continue
        return items
    return []


def detect_arabic_words(
    image_path: str,
    session_id: str,
    start_index: int = 0,
) -> list:
    """
    Strategy B: PaddleOCR on a scanned image.
    page_image_path points to the same source image (it IS the full page).
    """
    image = cv2.imread(image_path)
    if image is None:
        print(f"⚠️ Cannot read: {image_path}")
        return []

    # Copy source image into session dir so it's accessible via /assets/
    session_dir = ASSETS_WORDS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save a copy of the full page so the crop editor can load it via URL
    page_filename = f"page_full_{Path(image_path).stem}.png"
    page_full_dst = session_dir / page_filename
    cv2.imwrite(str(page_full_dst), image)
    page_img_url  = f"/assets/words/{session_id}/{page_filename}"

    processed      = _preprocess(image)
    processed_path = str(Path(image_path).parent / (Path(image_path).stem + "_proc.png"))
    cv2.imwrite(processed_path, processed)

    try:
        result = _get_engine().ocr(processed_path)
        boxes  = _extract_boxes(result)
        if not boxes:
            result = _get_engine().ocr(image_path)
            boxes  = _extract_boxes(result)
    except Exception as e:
        print(f"⚠️ OCR error: {e}")
        return []

    if not boxes:
        print(f"⚠️ No text detected in: {image_path}")
        return []

    words_data = []
    for local_idx, (box, ocr_text, confidence) in enumerate(boxes):
        global_idx = start_index + local_idx
        try:
            pts   = np.array(box).astype(np.float32)
            x_min = max(0, int(pts[:, 0].min()) - CROP_PADDING)
            y_min = max(0, int(pts[:, 1].min()) - CROP_PADDING)
            x_max = min(image.shape[1], int(pts[:, 0].max()) + CROP_PADDING)
            y_max = min(image.shape[0], int(pts[:, 1].max()) + CROP_PADDING)

            if (x_max - x_min) < MIN_WORD_WIDTH or (y_max - y_min) < MIN_WORD_HEIGHT:
                continue

            crop = image[y_min:y_max, x_min:x_max]
            if crop.size == 0:
                continue

            filename  = f"word_{global_idx:03d}.png"
            cv2.imwrite(str(session_dir / filename), crop)

            words_data.append({
                "id":              global_idx,
                "path":            f"/assets/words/{session_id}/{filename}",
                "page_image_path": page_img_url,   # ← full page for crop editor
                "page":            1,
                "box": {
                    "x": x_min, "y": y_min,
                    "w": x_max - x_min, "h": y_max - y_min,
                },
            })
        except Exception as e:
            print(f"⚠️ Word {global_idx}: {e}")

    print(f"✅ Scanned: {len(words_data)} words from {Path(image_path).name}")
    return words_data