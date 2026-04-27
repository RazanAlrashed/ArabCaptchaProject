"""
schemas/word.py

Pydantic models for word/OCR ingestion and admin endpoints.
"""
from datetime import datetime
from pydantic import BaseModel, Field


class WordIngest(BaseModel):
    """POST /words/ingest — add a word from OCR pipeline."""
    image_path: str = Field(..., description="Path to the word image file")
    word_type: str = Field(..., description="'reference' or 'low_confidence'")
    correct_text: str | None = Field(None, description="Known correct text (required for reference words)")
    source: str | None = Field(None, description="Origin of the word, e.g. 'book_scan'")
    initial_confidence: float | None = Field(None, description="OCR confidence (for low_confidence words)")


class WordIngestResponse(BaseModel):
    """Response after ingesting a word."""
    word_id: int
    word_type: str

    class Config:
        from_attributes = True


class WordListItem(BaseModel):
    """Single word in the admin word list."""
    word_id: int
    image_path: str
    word_type: str
    added_at: datetime
    # Reference-specific
    correct_text: str | None = None
    active: bool | None = None
    # Low-confidence-specific
    status: str | None = None
    verified_text: str | None = None
    total_votes: int | None = None

    class Config:
        from_attributes = True


class ConsensusDetail(BaseModel):
    """Consensus details for a low-confidence word."""
    low_conf_word_id: int
    top_candidate_text: str | None
    votes: int
    total: int
    ratio: float
    is_verified: bool

    class Config:
        from_attributes = True
