'''
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.utils.pdf_utils import pdf_to_image
from app.utils.ocr_engine import detect_arabic_words # سأضع كودها بالأسفل
from app.services.ocr_service import call_colab_and_save
import uuid
from pathlib import Path

router = APIRouter()

UPLOAD_DIR = Path("uploads")
ASSETS_WORDS_DIR = Path("assets/words")

@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # تأكدي من إنشاء المجلدات أولاً
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_WORDS_DIR.mkdir(parents=True, exist_ok=True)

    sid = str(uuid.uuid4())[:8]
    ext = Path(file.filename).suffix.lower()
    save_path = UPLOAD_DIR / f"{sid}{ext}"
    
    with open(save_path, "wb") as buffer:
        buffer.write(await file.read())

    image_path = str(save_path)
    if ext == ".pdf":
        # تأكدي أن دالة pdf_to_image لا ترجع None
        image_path = pdf_to_image(str(save_path), sid)

    # تنفيذ التقطيع
    words = detect_arabic_words(image_path, sid)
    
    return {"session_id": sid, "words": words}

@router.post("/run-ocr")
async def run_ocr_logic(req_data: dict, db: Session = Depends(get_db)):
    results = []
    for word in req_data.get("words", []):
        try:
            db_word = await call_colab_and_save(word, db)
            results.append({"id": word['id'], "status": "saved", "db_id": db_word.word_id})
        except Exception as e:
            results.append({"id": word['id'], "status": "error", "error": str(e)})
    return {"results": results}

# أضيفي هذا في app/routers/ocr.py
import shutil

@router.post("/update-crop")
async def update_crop(file: UploadFile = File(...), word_id: str = Form(...), session_id: str = Form(...)):
    session_dir = ASSETS_WORDS_DIR / session_id
    session_dir.mkdir(exist_ok=True, parents=True)
    
    file_path = session_dir / f"fixed_{word_id}.png"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # نستخدم الفواصل المائلة للأمام دائماً عند الرد للواجهة
    web_path = f"assets/words/{session_id}/fixed_{word_id}.png"
    
    return {
        "status": "success", 
        "new_url": f"/{web_path}",
        "new_path": web_path  # هذا هو المسار الذي سيخزن في الزر
    }
'''
"""
routers/ocr.py

Upload image or PDF → detect words with PaddleOCR → return crops.
PDF: all pages are processed and words from all pages are returned.
/run-ocr: unchanged — still sends to Colab (call_colab_and_save).
"""
'''
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.utils.pdf_utils import pdf_to_images
from app.utils.ocr_engine import detect_arabic_words
from app.services.ocr_service import call_colab_and_save

router = APIRouter()

UPLOAD_DIR       = Path("uploads")
ASSETS_WORDS_DIR = Path("assets/words")


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_WORDS_DIR.mkdir(parents=True, exist_ok=True)

    sid  = str(uuid.uuid4())[:8]
    ext  = Path(file.filename).suffix.lower()
    save_path = UPLOAD_DIR / f"{sid}{ext}"

    with open(save_path, "wb") as buffer:
        buffer.write(await file.read())

    all_words  = []
    word_index = 0   # global word id across all pages

    if ext == ".pdf":
        # ── Convert every PDF page → image → run OCR on each ──────────
        image_paths = pdf_to_images(str(save_path), sid)
        for page_num, image_path in enumerate(image_paths):
            page_words = detect_arabic_words(image_path, sid, start_index=word_index)
            # Tag each word with its page number so dashboard can show it
            for w in page_words:
                w["page"] = page_num + 1
            all_words.extend(page_words)
            word_index += len(page_words)
    else:
        # ── Single image ───────────────────────────────────────────────
        words = detect_arabic_words(str(save_path), sid, start_index=0)
        for w in words:
            w["page"] = 1
        all_words = words

    return {
        "session_id": sid,
        "words":      all_words,
        "total_pages": word_index,   # kept for info
    }


@router.post("/run-ocr")
async def run_ocr_logic(req_data: dict, db: Session = Depends(get_db)):
    """Send selected words to Colab (Qari) for OCR and save result."""
    results = []
    for word in req_data.get("words", []):
        try:
            db_word = await call_colab_and_save(word, db)
            results.append({"id": word["id"], "status": "saved", "db_id": db_word.word_id})
        except Exception as e:
            results.append({"id": word["id"], "status": "error", "error": str(e)})
    return {"results": results}


@router.post("/update-crop")
async def update_crop(
    file: UploadFile = File(...),
    word_id: str    = Form(...),
    session_id: str = Form(...),
):
    session_dir = ASSETS_WORDS_DIR / session_id
    session_dir.mkdir(exist_ok=True, parents=True)

    file_path = session_dir / f"fixed_{word_id}.png"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    web_path = f"assets/words/{session_id}/fixed_{word_id}.png"
    return {
        "status":   "success",
        "new_url":  f"/{web_path}",
        "new_path": web_path,
    }


@router.post("/run-ocr-local")
async def run_ocr_local(req_data: dict, db: Session = Depends(get_db)):
    """
    PaddleOCR local mode: re-run OCR on the crop image
    and save directly to DB without calling Colab.
    """
    from app.services.ocr_service import ingest_word
    import cv2, numpy as np

    results = []
    for word in req_data.get("words", []):
        try:
            path = word.get("path", "").lstrip("/")

            # Re-run PaddleOCR on the crop to get text + confidence
            from app.utils.ocr_engine import _get_engine, _extract_boxes
            boxes = _extract_boxes(_get_engine().ocr(path))

            # Take the highest-confidence detection from the crop
            ocr_text   = ""
            confidence = 0.0
            if boxes:
                best = max(boxes, key=lambda x: x[2])
                ocr_text, confidence = best[1], best[2]

            word_type = "reference" if confidence >= 0.85 else "low_confidence"

            db_word = ingest_word(
                image_path=path,
                word_type=word_type,
                correct_text=ocr_text if word_type == "reference" else None,
                source="paddle_ocr_local",
                initial_confidence=confidence,
                db=db,
            )
            results.append({"id": word.get("id"), "status": "saved", "db_id": db_word.word_id})
        except Exception as e:
            results.append({"id": word.get("id"), "status": "error", "error": str(e)})

    return {"results": results}
'''
"""
routers/ocr.py

Upload image or PDF → smart word detection → return crops.

PDF routing:
  - Vector PDF (has embedded text) → extract directly via PyMuPDF (fast, perfect)
  - Scanned PDF (image-based)      → convert pages → PaddleOCR
Image routing:
  - Always PaddleOCR
"""
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.utils.pdf_utils import pdf_to_images
from app.utils.ocr_engine import (
    detect_arabic_words,
    is_vector_pdf,
    extract_words_from_vector_pdf,
)
from app.services.ocr_service import call_colab_and_save

router = APIRouter()

UPLOAD_DIR       = Path("uploads")
ASSETS_WORDS_DIR = Path("assets/words")


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_WORDS_DIR.mkdir(parents=True, exist_ok=True)

    sid       = str(uuid.uuid4())[:8]
    ext       = Path(file.filename).suffix.lower()
    save_path = UPLOAD_DIR / f"{sid}{ext}"

    with open(save_path, "wb") as buffer:
        buffer.write(await file.read())

    all_words = []

    if ext == ".pdf":
        if is_vector_pdf(str(save_path)):
            # ── Vector PDF: extract directly — pixel-perfect, no OCR ──
            print(f"📄 Vector PDF detected — extracting words directly")
            all_words = extract_words_from_vector_pdf(str(save_path), sid)
        else:
            # ── Scanned PDF: render each page → PaddleOCR ─────────────
            print(f"🖼 Scanned PDF detected — using PaddleOCR")
            image_paths = pdf_to_images(str(save_path), sid)
            word_index  = 0
            for page_num, image_path in enumerate(image_paths):
                page_words = detect_arabic_words(image_path, sid, start_index=word_index)
                for w in page_words:
                    w["page"] = page_num + 1
                all_words.extend(page_words)
                word_index += len(page_words)
    else:
        # ── Image upload: PaddleOCR ────────────────────────────────────
        all_words = detect_arabic_words(str(save_path), sid)
        for w in all_words:
            w["page"] = 1

    return {
        "session_id": sid,
        "words":      all_words,
        "source":     "vector" if ext == ".pdf" and is_vector_pdf(str(save_path)) else "ocr",
    }


@router.post("/run-ocr")
async def run_ocr_logic(req_data: dict, db: Session = Depends(get_db)):
    """Send words to Colab (Qari) — unchanged."""
    results = []
    for word in req_data.get("words", []):
        try:
            db_word = await call_colab_and_save(word, db)
            results.append({"id": word["id"], "status": "saved", "db_id": db_word.word_id})
        except Exception as e:
            results.append({"id": word["id"], "status": "error", "error": str(e)})
    return {"results": results}


@router.post("/run-ocr-local")
async def run_ocr_local(req_data: dict, db: Session = Depends(get_db)):
    """PaddleOCR local mode — re-read crop and save to DB."""
    from app.services.ocr_service import ingest_word
    from app.utils.ocr_engine import _get_engine, _extract_boxes

    results = []
    for word in req_data.get("words", []):
        try:
            path  = word.get("path", "").lstrip("/")
            boxes = _extract_boxes(_get_engine().ocr(path))
            ocr_text, confidence = "", 0.0
            if boxes:
                best = max(boxes, key=lambda x: x[2])
                ocr_text, confidence = best[1], float(best[2])

            word_type = "reference" if confidence >= 0.85 else "low_confidence"
            db_word   = ingest_word(
                image_path=path, word_type=word_type,
                correct_text=ocr_text if word_type == "reference" else None,
                source="paddle_ocr_local", initial_confidence=confidence, db=db,
            )
            results.append({"id": word.get("id"), "status": "saved", "db_id": db_word.word_id})
        except Exception as e:
            results.append({"id": word.get("id"), "status": "error", "error": str(e)})
    return {"results": results}


@router.post("/update-crop")
async def update_crop(
    file: UploadFile = File(...),
    word_id: str    = Form(...),
    session_id: str = Form(...),
):
    session_dir = ASSETS_WORDS_DIR / session_id
    session_dir.mkdir(exist_ok=True, parents=True)
    file_path = session_dir / f"fixed_{word_id}.png"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    web_path = f"assets/words/{session_id}/fixed_{word_id}.png"
    return {"status": "success", "new_url": f"/{web_path}", "new_path": web_path}