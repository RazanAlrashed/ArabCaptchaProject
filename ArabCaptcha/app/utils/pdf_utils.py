'''
# PDF utilities for ArabCaptcha
from pathlib import Path
from fastapi import HTTPException
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
# --- دالة تحويل PDF ---
def pdf_to_image(pdf_path: str, session_id: str) -> str:
    try:
        import fitz
    except ImportError:
        raise HTTPException(500, "Run: pip install PyMuPDF")
    
    doc  = fitz.open(pdf_path)
    pix  = doc[0].get_pixmap(matrix=fitz.Matrix(3.0, 3.0))
    out  = str(UPLOAD_DIR / f"{session_id}_page.png")
    pix.save(out)
    doc.close()
    return out
'''
"""
utils/pdf_utils.py

Converts PDF pages to high-resolution PNG images for OCR.
Supports single page or all pages.
"""
from pathlib import Path
from fastapi import HTTPException

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def pdf_to_images(pdf_path: str, session_id: str) -> list[str]:
    """
    Convert ALL pages of a PDF to PNG images.

    Returns:
        list of image paths, one per page e.g.
        ["uploads/abc123_page0.png", "uploads/abc123_page1.png", ...]
    """
    try:
        import fitz
    except ImportError:
        raise HTTPException(500, "PyMuPDF غير مثبت. شغّل: pip install PyMuPDF")

    doc         = fitz.open(pdf_path)
    image_paths = []

    for page_num in range(len(doc)):
        pix = doc[page_num].get_pixmap(matrix=fitz.Matrix(3.0, 3.0))
        out = str(UPLOAD_DIR / f"{session_id}_page{page_num}.png")
        pix.save(out)
        image_paths.append(out)

    doc.close()
    return image_paths


def pdf_to_image(pdf_path: str, session_id: str) -> str:
    """First page only — kept for backward compatibility."""
    pages = pdf_to_images(pdf_path, session_id)
    return pages[0] if pages else ""