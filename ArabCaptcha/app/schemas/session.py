"""
schemas/session.py

Pydantic models for session-related API requests and responses.
"""
from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """POST /sessions — create a new CAPTCHA session."""
    api_key: str = Field(..., description="Raw API key for the client site")
    domain: str = Field(..., description="Origin domain of the request")
    signals_json: str | None = Field(None, description="JSON string of behavioral signals")


class SessionResponse(BaseModel):
    """Response after creating a session."""
    session_id: str
    risk_level: str
    bot_score: float

    class Config:
        from_attributes = True
