"""
routers/challenge.py

API endpoints for creating and retrieving CAPTCHA challenges.
"""
'''
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.challenge import ChallengeCreate, ChallengeResponse
from app.services.challenge_service import create_challenge, get_challenge, get_image_url

router = APIRouter(prefix="/challenges", tags=["Challenges"])


@router.post("", response_model=ChallengeResponse)
def request_challenge(payload: ChallengeCreate, db: Session = Depends(get_db)):
    """
    Request a new CAPTCHA challenge for an active session.
    Returns two word images (reference + low-confidence) and difficulty.
    """
    challenge = create_challenge(session_id=payload.session_id, db=db)
    return ChallengeResponse(
        challenge_id=challenge.challenge_id,
        ref_image_url=get_image_url(challenge.ref_word_id, db),
        low_conf_image_url=get_image_url(challenge.low_conf_word_id, db),
        difficulty=challenge.difficulty,
        expires_at=challenge.expires_at,
        max_attempts=challenge.max_attempts,
    )


@router.get("/{challenge_id}", response_model=ChallengeResponse)
def fetch_challenge(challenge_id: str, db: Session = Depends(get_db)):
    """Retrieve details of an existing challenge."""
    challenge = get_challenge(challenge_id=challenge_id, db=db)
    return ChallengeResponse(
        challenge_id=challenge.challenge_id,
        ref_image_url=get_image_url(challenge.ref_word_id, db),
        low_conf_image_url=get_image_url(challenge.low_conf_word_id, db),
        difficulty=challenge.difficulty,
        expires_at=challenge.expires_at,
        max_attempts=challenge.max_attempts,
    )
'''

"""
routers/challenge.py

API endpoints for creating and retrieving CAPTCHA challenges.

New in this version:
  - ChallengeResponse includes composite_image_url (stitched distorted image)
    and ref_end_x (pixel split point, kept server-side but sent for debugging).
  - POST /{challenge_id}/upgrade  — called by the widget when in-challenge
    signals push the bot score above the escalation threshold.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.schemas.challenge import ChallengeCreate, ChallengeResponse
from app.services.challenge_service import (
    create_challenge,
    get_challenge,
    get_image_url,
    upgrade_challenge_difficulty,
)

router = APIRouter(prefix="/challenges", tags=["Challenges"])


class ChallengeResponseExtended(ChallengeResponse):
    """
    Extends the base ChallengeResponse to carry the composite image URL.

    composite_image_url  — the stitched, distorted PNG (ref + low-conf combined)
    ref_image_url        — kept for fallback / admin preview
    low_conf_image_url   — kept for fallback / admin preview
    """
    composite_image_url: Optional[str] = None


class UpgradeRequest(BaseModel):
    signals_json: Optional[str] = None
    new_score: float


class UpgradeResponse(BaseModel):
    upgraded: bool
    new_difficulty: str
    new_composite_url: Optional[str] = None


def _build_response(challenge, db: Session) -> ChallengeResponseExtended:
    return ChallengeResponseExtended(
        challenge_id=challenge.challenge_id,
        ref_image_url=get_image_url(challenge.ref_word_id, db),
        low_conf_image_url=get_image_url(challenge.low_conf_word_id, db),
        difficulty=challenge.difficulty,
        expires_at=challenge.expires_at,
        max_attempts=challenge.max_attempts,
        composite_image_url=getattr(challenge, "composite_image_url", None),
    )


@router.post("", response_model=ChallengeResponseExtended)
def request_challenge(payload: ChallengeCreate, db: Session = Depends(get_db)):
    """
    Request a new CAPTCHA challenge for an active session.

    Returns ONE composite image (ref + low-conf stitched together, distorted
    according to the session's bot score).
    """
    challenge = create_challenge(session_id=payload.session_id, db=db)
    return _build_response(challenge, db)


@router.get("/{challenge_id}", response_model=ChallengeResponseExtended)
def fetch_challenge(challenge_id: str, db: Session = Depends(get_db)):
    """Retrieve details of an existing challenge."""
    challenge = get_challenge(challenge_id=challenge_id, db=db)
    return _build_response(challenge, db)


@router.post("/{challenge_id}/upgrade", response_model=UpgradeResponse)
def escalate_challenge(
    challenge_id: str,
    payload: UpgradeRequest,
    db: Session = Depends(get_db),
):
    """
    Escalate challenge difficulty based on in-challenge behavioral signals.

    Called by the widget when real-time signal analysis raises the bot score
    above the escalation threshold. The server regenerates the composite image
    at the new difficulty level and resets the attempt counter.
    """
    challenge = upgrade_challenge_difficulty(
        challenge_id=challenge_id,
        new_score=payload.new_score,
        db=db,
    )
    return UpgradeResponse(
        upgraded=True,
        new_difficulty=challenge.difficulty,
        new_composite_url=getattr(challenge, "composite_image_url", None),
    )
