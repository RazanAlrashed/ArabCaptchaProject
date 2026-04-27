"""
services/challenge_service.py

Creates CAPTCHA challenges by selecting words and setting difficulty.
"""
'''
import random
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import SiteSession, Challenge, ReferenceWord, LowConfidenceWord, Word
from app.core.config import settings
from app.utils.bot_scorer import determine_difficulty


def create_challenge(session_id: str, db: Session) -> Challenge:
    """
    1. Verify session is active.
    2. Pick a random active reference word.
    3. Pick a random pending low-confidence word.
    4. Set difficulty from session's bot score.
    5. Create and return the Challenge.
    """
    # ── Validate session ─────────────────────────────────────────────────
    site_session = db.query(SiteSession).filter(
        SiteSession.session_id == session_id
    ).first()
    if not site_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if site_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    # ── Pick reference word ──────────────────────────────────────────────
    ref_word = (
        db.query(ReferenceWord)
        .filter(ReferenceWord.active == True)
        .order_by(func.random())
        .first()
    )
    if not ref_word:
        raise HTTPException(status_code=503, detail="No reference words available")

    # ── Pick low-confidence word ─────────────────────────────────────────
    low_conf_word = (
        db.query(LowConfidenceWord)
        .filter(LowConfidenceWord.status == "pending")
        .order_by(func.random())
        .first()
    )
    if not low_conf_word:
        raise HTTPException(status_code=503, detail="No low-confidence words available")

    # ── Determine difficulty ─────────────────────────────────────────────
    bot_score = site_session.bot_score_initial or 0.0
    difficulty = determine_difficulty(bot_score)

    # ── Create challenge ─────────────────────────────────────────────────
    challenge = Challenge(
        session_id=session_id,
        ref_word_id=ref_word.word_id,
        low_conf_word_id=low_conf_word.word_id,
        bot_score=bot_score,
        difficulty=difficulty,
        max_attempts=settings.MAX_CHALLENGE_ATTEMPTS,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.CHALLENGE_EXPIRY_MINUTES),
        status="pending",
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge


def get_challenge(challenge_id: str, db: Session) -> Challenge:
    """Fetch a challenge by ID or 404."""
    challenge = db.query(Challenge).filter(
        Challenge.challenge_id == challenge_id
    ).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def get_image_url(word_id: int, db: Session) -> str:
    """Get the image URL/path for a word."""
    word = db.query(Word).filter(Word.word_id == word_id).first()
    return word.image_path if word else ""
'''

"""
services/challenge_service.py

Creates CAPTCHA challenges:
  1. Selects words from DB.
  2. Applies difficulty-based image distortions (via image_manipulator).
  3. Stitches ref + low-conf images into ONE composite image
     (confuses automated segmentation).
  4. Stores composite_path and ref_end_x in the Challenge row.
"""
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import SiteSession, Challenge, ReferenceWord, LowConfidenceWord, Word
from app.core.config import settings
from app.utils.bot_scorer import determine_difficulty
from app.utils.image_manipulator import build_captcha_image


# Where composite images are saved (served by FastAPI as /assets/captcha/…)
_CAPTCHA_DIR = Path("assets") / "captcha"


def create_challenge(session_id: str, db: Session) -> Challenge:
    """
    1. Verify session is active.
    2. Pick a random active reference word.
    3. Pick a random pending low-confidence word.
    4. Determine difficulty from bot score.
    5. Build the composite image (distorted + stitched).
    6. Persist and return the Challenge.
    """
    # ── Validate session ─────────────────────────────────────────────────
    site_session = db.query(SiteSession).filter(
        SiteSession.session_id == session_id
    ).first()
    if not site_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if site_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    # ── Pick reference word ──────────────────────────────────────────────
    ref_word = (
        db.query(ReferenceWord)
        .filter(ReferenceWord.active == True)
        .order_by(func.random())
        .first()
    )
    if not ref_word:
        raise HTTPException(status_code=503, detail="No reference words available")

    # ── Pick low-confidence word ─────────────────────────────────────────
    low_conf_word = (
        db.query(LowConfidenceWord)
        .filter(LowConfidenceWord.status == "pending")
        .order_by(func.random())
        .first()
    )
    if not low_conf_word:
        raise HTTPException(status_code=503, detail="No low-confidence words available")

    # ── Determine difficulty ─────────────────────────────────────────────
    bot_score  = site_session.bot_score_initial or 0.5
    difficulty = determine_difficulty(bot_score)

    # ── Get word image paths ─────────────────────────────────────────────
    ref_word_base  = db.query(Word).filter(Word.word_id == ref_word.word_id).first()
    lc_word_base   = db.query(Word).filter(Word.word_id == low_conf_word.word_id).first()

    ref_img_path = ref_word_base.image_path.lstrip("/") if ref_word_base else ""
    lc_img_path  = lc_word_base.image_path.lstrip("/")  if lc_word_base else ""

    # ── Build composite distorted image ─────────────────────────────────
    challenge_id   = str(uuid.uuid4())
    composite_file = _CAPTCHA_DIR / f"{challenge_id}.png"

    try:
        meta = build_captcha_image(
            ref_path=ref_img_path,
            lc_path=lc_img_path,
            difficulty=difficulty,
            output_path=str(composite_file),
        )
        composite_url = f"/assets/captcha/{challenge_id}.png"
        ref_end_x     = meta["ref_end_x"]
    except FileNotFoundError as e:
        # Fallback: serve original paths separately (no composite)
        print(f"⚠️ Composite build failed: {e}. Using raw images.")
        composite_url = f"/{ref_img_path}"
        ref_end_x     = -1     # -1 = composite unavailable, use separate URLs

    # ── Create challenge ─────────────────────────────────────────────────
    challenge = Challenge(
        challenge_id=challenge_id,
        session_id=session_id,
        ref_word_id=ref_word.word_id,
        low_conf_word_id=low_conf_word.word_id,
        bot_score=bot_score,
        difficulty=difficulty,
        max_attempts=settings.MAX_CHALLENGE_ATTEMPTS,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.CHALLENGE_EXPIRY_MINUTES),
        status="pending",
        # New composite fields — add these columns via migration
        composite_image_url=composite_url,
        ref_end_x=ref_end_x,
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge


def upgrade_challenge_difficulty(challenge_id: str, new_score: float, db: Session) -> Challenge:
    """
    Called when in-challenge behavioral signals push the bot score higher.
    Regenerates the composite image at a harder difficulty and resets the challenge.

    Returns the updated Challenge.
    """
    challenge = db.query(Challenge).filter(
        Challenge.challenge_id == challenge_id
    ).first()
    if not challenge or challenge.status != "pending":
        raise HTTPException(status_code=404, detail="Challenge not upgradeable")

    new_difficulty = determine_difficulty(new_score)

    # Only re-render if difficulty actually increases
    _rank = {"none": 0, "easy": 1, "medium": 2, "hard": 3}
    if _rank.get(new_difficulty, 0) <= _rank.get(challenge.difficulty, 0):
        return challenge

    ref_word_base = db.query(Word).filter(Word.word_id == challenge.ref_word_id).first()
    lc_word_base  = db.query(Word).filter(Word.word_id == challenge.low_conf_word_id).first()

    ref_img_path = ref_word_base.image_path.lstrip("/") if ref_word_base else ""
    lc_img_path  = lc_word_base.image_path.lstrip("/")  if lc_word_base else ""

    composite_file = _CAPTCHA_DIR / f"{challenge_id}_v2.png"
    try:
        meta = build_captcha_image(
            ref_path=ref_img_path,
            lc_path=lc_img_path,
            difficulty=new_difficulty,
            output_path=str(composite_file),
        )
        composite_url = f"/assets/captcha/{challenge_id}_v2.png"
        ref_end_x     = meta["ref_end_x"]
    except Exception as e:
        print(f"⚠️ Upgrade composite failed: {e}")
        return challenge

    challenge.difficulty         = new_difficulty
    challenge.composite_image_url = composite_url
    challenge.ref_end_x          = ref_end_x
    challenge.bot_score          = new_score
    challenge.attempts_count     = 0     # reset so user gets fresh attempts
    db.commit()
    db.refresh(challenge)

    print(f"🔴 Challenge {challenge_id} upgraded → {new_difficulty} (score={new_score})")
    return challenge


def get_challenge(challenge_id: str, db: Session) -> Challenge:
    """Fetch a challenge by ID or 404."""
    challenge = db.query(Challenge).filter(
        Challenge.challenge_id == challenge_id
    ).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def get_image_url(word_id: int, db: Session) -> str:
    """Get the image URL/path for a word (used for individual fallback)."""
    word = db.query(Word).filter(Word.word_id == word_id).first()
    return word.image_path if word else ""