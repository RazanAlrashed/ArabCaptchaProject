"""
utils/text_normalizer.py

Normalizes Arabic text before comparison.
Handles diacritics removal, alef unification, and whitespace trimming.
"""
import re
import unicodedata


# Arabic diacritics (tashkeel) Unicode range
_DIACRITICS = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]')

# All forms of Alef → bare Alef
_ALEF_VARIANTS = re.compile(r'[\u0622\u0623\u0625\u0671]')  # آ أ إ ٱ

# Taa Marbuta → Haa
_TAA_MARBUTA = re.compile(r'\u0629')  # ة → ه


def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for comparison:
      1. Strip leading/trailing whitespace
      2. Remove diacritics (tashkeel)
      3. Unify all Alef variants to bare Alef (ا)
      4. Convert Taa Marbuta (ة) to Haa (ه)
      5. Collapse multiple spaces into one
      6. Normalize Unicode to NFC form
    """
    if not text:
        return ""

    t = text.strip()
    t = _DIACRITICS.sub('', t)
    t = _ALEF_VARIANTS.sub('\u0627', t)   # → ا
    t = _TAA_MARBUTA.sub('\u0647', t)      # ة → ه
    t = re.sub(r'\s+', ' ', t)
    t = unicodedata.normalize('NFC', t)
    return t


def texts_match(text_a: str, text_b: str) -> bool:
    """Compare two Arabic strings after normalization."""
    return normalize_arabic(text_a) == normalize_arabic(text_b)
