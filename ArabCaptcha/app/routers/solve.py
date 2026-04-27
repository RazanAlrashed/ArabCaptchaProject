"""
routers/solve.py

API endpoint for submitting CAPTCHA solve attempts.
"""
'''
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.attempt import AttemptCreate, AttemptResponse
from app.services.solve_service import solve_challenge

router = APIRouter(prefix="/challenges", tags=["Solve"])


@router.post("/{challenge_id}/solve", response_model=AttemptResponse)
def submit_answer(challenge_id: str, payload: AttemptCreate, db: Session = Depends(get_db)):
    """
    Submit an answer for a challenge.

    The reference word answer is checked first (Trust Gate).
    If correct, the low-confidence answer is recorded for crowdsourcing.
    Returns a verification token on success.
    """
    result = solve_challenge(
        challenge_id=challenge_id,
        ref_answer=payload.ref_answer,
        low_conf_answer=payload.low_conf_answer,
        response_time_ms=payload.response_time_ms,
        signals_json=payload.signals_json,
        db=db,
    )
    return AttemptResponse(**result)
'''

"""
routers/solve.py

API endpoint for submitting CAPTCHA solve attempts.

New in this version:
  AttemptResponse now carries:
    needs_upgrade     bool   — widget should reload challenge at harder difficulty
    new_difficulty    str    — what difficulty the upgraded challenge will be
    new_composite_url str    — URL of the new composite image (if upgraded)
    bot_score_final   float  — final score computed from in-challenge signals
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.schemas.attempt import AttemptCreate
from app.services.solve_service import solve_challenge

router = APIRouter(prefix="/challenges", tags=["Solve"])


class AttemptResponseExtended(BaseModel):
    passed: bool
    attempts_left: int
    token: Optional[str] = None
    needs_upgrade: bool = False
    new_difficulty: Optional[str] = None
    new_composite_url: Optional[str] = None
    bot_score_final: Optional[float] = None


@router.post("/{challenge_id}/solve", response_model=AttemptResponseExtended)
def submit_answer(challenge_id: str, payload: AttemptCreate, db: Session = Depends(get_db)):
    """
    Submit an answer for a challenge.

    Flow:
      1. Final bot score computed from in-challenge signals.
      2. If score escalated significantly → return needs_upgrade=True.
         The widget reloads /challenges/{id}/upgrade to get a harder image.
      3. If Trust Gate passes → low-conf answer stored, token issued.
    """
    result = solve_challenge(
        challenge_id=challenge_id,
        ref_answer=payload.ref_answer,
        low_conf_answer=payload.low_conf_answer,
        response_time_ms=payload.response_time_ms,
        signals_json=payload.signals_json,
        db=db,
    )
    return AttemptResponseExtended(**result)