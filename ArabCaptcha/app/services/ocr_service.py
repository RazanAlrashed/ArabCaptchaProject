"""
services/ocr_service.py

Stub service for OCR word ingestion.
Ready to connect to an actual OCR model in the future.
"""
'''
import httpx
import base64
from sqlalchemy.orm import Session
from app.db.models import Word, ReferenceWord, LowConfidenceWord
from app.core.config import settings # افترضنا وجود التعديلات في config
import os
def ingest_word(
    image_path: str,
    word_type: str,
    correct_text: str | None,
    source: str | None,
    initial_confidence: float | None,
    db: Session,
) -> Word:
    # 1. إنشاء السجل الأساسي في جدول Word
    word = Word(image_path=image_path, word_type=word_type)
    db.add(word)
    db.flush() 

    # 2. التصنيف بناءً على النوع
    if word_type == "reference":
        ref = ReferenceWord(
            word_id=word.word_id,
            correct_text=correct_text,
            source=source,
            active=True
        )
        db.add(ref)
    else:
        lc = LowConfidenceWord(
            word_id=word.word_id,
            initial_confidence=initial_confidence,
            status="pending"
        )
        db.add(lc)

    db.commit()
    db.refresh(word)
    return word
'''
import httpx
import base64
from sqlalchemy.orm import Session
from app.db.models import Word, ReferenceWord, LowConfidenceWord
from app.core.config import settings # افترضنا وجود التعديلات في config
import os
async def call_colab_and_save(word_data: dict, db: Session):
    """دالة منظمة لإرسال الكلمة لكولاب وحفظ نتيجتها فوراً"""
    path = word_data.get("path") 
    
    # ملاحظة: المسار في JSON يبدأ بـ /assets/، يجب تحويله لمسار نظام حقيقي
    # إذا كان المسار المخزن هو /assets/words/xxx.png
    # نحتاج للتأكد من أننا نفتح الملف من المجلد الصحيح في الويندوز
    actual_file_path = path.lstrip('/') # إزالة الشرطة في البداية إذا وجدت
    
    if not os.path.exists(actual_file_path):
        # محاولة أخرى إذا كان المسار يحتاج لتعديل (بناءً على مكان تشغيل السيرفر)
        print(f"⚠️ File not found at {actual_file_path}, trying to fix path...")
        # تأكدي من أن المسار يشير للمكان الصحيح على جهازك
    
    with open(actual_file_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    
    async with httpx.AsyncClient(timeout=60) as client:
        # نستخدم الرابط المخزن في الإعدادات
        response = await client.post(f"{settings.COLAB_OCR_URL}/predict", json={"image_b64": img_b64})
        data = response.json()
        
    predicted_text = data.get("text", "")
    confidence = data.get("confidence", 0.0)

    # تحديد النوع بناءً على الثقة (Threshold)
    # الثقة أعلى من 0.85 تذهب كمرجع، أقل تذهب ككابتشا (Low Confidence)
    w_type = "reference" if confidence >= 0.85 else "low_confidence"
    
    return ingest_word(
        image_path=path.lstrip('/'),
        word_type=w_type,
        correct_text=predicted_text if w_type == "reference" else None,
        source="qari_ocr",
        initial_confidence=confidence,
        db=db
    )

"""
services/ocr_service.py

Local word ingestion service.
Saves detected words to the database — no external Colab dependency.
"""
from sqlalchemy.orm import Session
from app.db.models import Word, ReferenceWord, LowConfidenceWord


def ingest_word(
    image_path: str,
    word_type: str,
    correct_text: str | None,
    source: str | None,
    initial_confidence: float | None,
    db: Session,
) -> Word:
    """
    Save a detected word to the database.

    Args:
        image_path:         relative path stored in DB (no leading slash)
        word_type:          "reference" or "low_confidence"
        correct_text:       OCR text (only for reference words)
        source:             where it came from e.g. "paddle_ocr"
        initial_confidence: OCR confidence score 0.0–1.0
        db:                 SQLAlchemy session

    Returns:
        The created Word ORM object.
    """
    # Normalize path — never store a leading slash
    image_path = image_path.lstrip("/")

    # 1. Base word record
    word = Word(image_path=image_path, word_type=word_type)
    db.add(word)
    db.flush()   # get word_id before inserting child row

    # 2. Type-specific record
    if word_type == "reference":
        ref = ReferenceWord(
            word_id=word.word_id,
            correct_text=correct_text or "",
            source=source,
            active=True,
        )
        db.add(ref)
    else:
        lc = LowConfidenceWord(
            word_id=word.word_id,
            initial_confidence=initial_confidence,
            status="pending",
        )
        db.add(lc)

    db.commit()
    db.refresh(word)
    return word


def ingest_word(image_path, word_type, correct_text, source, initial_confidence, db):
    """Save a word directly to DB without Colab — used by PaddleOCR local mode."""
    from app.db.models import Word, ReferenceWord, LowConfidenceWord
    image_path = image_path.lstrip("/")
    word = Word(image_path=image_path, word_type=word_type)
    db.add(word)
    db.flush()
    if word_type == "reference":
        db.add(ReferenceWord(word_id=word.word_id, correct_text=correct_text or "", source=source, active=True))
    else:
        db.add(LowConfidenceWord(word_id=word.word_id, initial_confidence=initial_confidence, status="pending"))
    db.commit()
    db.refresh(word)
    return word