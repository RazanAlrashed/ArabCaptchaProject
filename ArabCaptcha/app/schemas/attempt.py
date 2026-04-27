"""
schemas/attempt.py

Pydantic models for solve-attempt API requests and responses.
"""
from pydantic import BaseModel, Field


class AttemptCreate(BaseModel):
    """POST /challenges/{id}/solve — submit an answer."""
    ref_answer: str = Field(..., description="User's answer for the reference word")
    low_conf_answer: str = Field(..., description="User's answer for the low-confidence word")
    response_time_ms: float | None = Field(None, description="Time taken to answer in ms")
    signals_json: str | None = Field(None, description="JSON string of behavioral signals")


class AttemptResponse(BaseModel):
    """Response after a solve attempt."""
    passed: bool
    attempts_left: int
    token: str | None = None

    class Config:
        from_attributes = True
