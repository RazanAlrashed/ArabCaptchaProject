"""
services/solve_service.py

Handles CAPTCHA solve attempts:
  - Trust Gate: verify reference word answer first
  - Record attempt
  - If trusted, store low-confidence submission for crowdsourcing
  - Issue token on success
"""
'''
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    Challenge, Attempt, ReferenceWord,
    LowConfidenceSubmission, BehaviorLog,
)
from app.utils.text_normalizer import normalize_arabic, texts_match
from app.services.consensus_service import update_consensus


def solve_challenge(
    challenge_id: str,
    ref_answer: str,
    low_conf_answer: str,
    response_time_ms: float | None,
    signals_json: str | None,
    db: Session,
) -> dict:
    """
    Process a solve attempt:
      1. Validate challenge (exists, pending, not expired)
      2. Count existing attempts
      3. Check reference answer (Trust Gate)
      4. If correct → record low-confidence submission + update consensus
      5. Update challenge status
      6. Return result with token if passed
    """
    # ── Validate challenge ───────────────────────────────────────────────
    challenge = db.query(Challenge).filter(
        Challenge.challenge_id == challenge_id
    ).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if challenge.status != "pending":
        raise HTTPException(status_code=400, detail="Challenge already resolved")
    if datetime.utcnow() > challenge.expires_at:
        challenge.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Challenge has expired")

    # ── Count attempts ───────────────────────────────────────────────────
    attempt_count = db.query(Attempt).filter(
        Attempt.challenge_id == challenge_id
    ).count()

    if attempt_count >= challenge.max_attempts:
        challenge.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Maximum attempts reached")

    # ── Trust Gate: check reference answer ───────────────────────────────
    ref_word = db.query(ReferenceWord).filter(
        ReferenceWord.word_id == challenge.ref_word_id
    ).first()

    ref_correct = texts_match(ref_answer, ref_word.correct_text)

    # ── Record the attempt ───────────────────────────────────────────────
    attempt = Attempt(
        challenge_id=challenge_id,
        attempt_number=attempt_count + 1,
        reference_input_text=ref_answer,
        reference_input_normalized=normalize_arabic(ref_answer),
        low_conf_input_text=low_conf_answer,
        low_conf_input_normalized=normalize_arabic(low_conf_answer),
        passed=ref_correct,
        response_time_ms=response_time_ms,
        signals_json=signals_json,
    )
    db.add(attempt)
    db.flush()

    # ── Log behavior signals ─────────────────────────────────────────────
    if signals_json:
        log = BehaviorLog(
            session_id=challenge.session_id,
            event_type="solve_attempt",
            signals_json=signals_json,
        )
        db.add(log)

    # ── If reference answer is correct → Trust Gate passed ───────────────
    token = None
    if ref_correct:
        # Store low-confidence submission for crowdsourcing
        submission = LowConfidenceSubmission(
            low_conf_word_id=challenge.low_conf_word_id,
            attempt_id=attempt.attempt_id,
            submitted_text=low_conf_answer,
            normalized_text=normalize_arabic(low_conf_answer),
        )
        db.add(submission)

        # Mark challenge as passed
        challenge.status = "passed"
        challenge.is_human_verified = True

        # Generate verification token
        token = str(uuid.uuid4())

        db.commit()

        # Update consensus (after commit so submission is persisted)
        update_consensus(challenge.low_conf_word_id, db)
    else:
        # Check if this was the last attempt
        if attempt_count + 1 >= challenge.max_attempts:
            challenge.status = "failed"
        db.commit()

    attempts_left = challenge.max_attempts - (attempt_count + 1)

    return {
        "passed": ref_correct,
        "attempts_left": max(attempts_left, 0),
        "token": token,
    }
    
'''

"""
services/solve_service.py

Handles CAPTCHA solve attempts:
  ① Trust Gate: verify reference word answer first
  ② Compute FINAL bot score from in-challenge behavioral signals
  ③ If final score indicates bot but initial was human → escalate
     (return needs_upgrade=True so the client shows a harder challenge)
  ④ If trusted → record low-conf submission + update consensus + issue token
  ⑤ Persist bot_score_final on the session for ML training (Phase 2)
"""

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    Challenge, Attempt, ReferenceWord,
    LowConfidenceSubmission, BehaviorLog, SiteSession,
)
from app.utils.text_normalizer import normalize_arabic, texts_match
from app.utils.bot_scorer import calculate_bot_score, needs_challenge as score_needs_challenge
from app.services.consensus_service import update_consensus


# How much the final score must rise above the initial before we escalate
_ESCALATION_DELTA = 0.25

# Final score below this → treat as bot regardless of initial score
_BOT_THRESHOLD = 0.40


def solve_challenge(
    challenge_id: str,
    ref_answer: str,
    low_conf_answer: str,
    response_time_ms: float | None,
    signals_json: str | None,
    db: Session,
) -> dict:
    """
    Process a solve attempt.

    Returns a dict with keys:
      passed          bool   — did the user answer the ref word correctly?
      attempts_left   int
      token           str | None
      needs_upgrade   bool   — client should request a harder challenge
      new_difficulty  str | None
      bot_score_final float  — so the client / server can log it
    """
    # ── Validate challenge ───────────────────────────────────────────────
    challenge = db.query(Challenge).filter(
        Challenge.challenge_id == challenge_id
    ).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if challenge.status != "pending":
        raise HTTPException(status_code=400, detail="Challenge already resolved")
    if datetime.utcnow() > challenge.expires_at:
        challenge.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Challenge has expired")

    # ── Count existing attempts ──────────────────────────────────────────
    attempt_count = db.query(Attempt).filter(
        Attempt.challenge_id == challenge_id
    ).count()

    if attempt_count >= challenge.max_attempts:
        challenge.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Maximum attempts reached")

    # ── Compute FINAL bot score from in-challenge signals ────────────────
    final_score, final_breakdown = calculate_bot_score(signals_json)
    initial_score = challenge.bot_score or 0.5

    # ── Check for score escalation ───────────────────────────────────────
    # Score dropped significantly (user looks more like a bot now)
    score_delta    = initial_score - final_score      # positive = got more suspicious
    is_now_bot     = final_score < _BOT_THRESHOLD
    score_escalated = score_delta >= _ESCALATION_DELTA or (is_now_bot and initial_score >= 0.5)

    # ── Trust Gate: check reference answer ───────────────────────────────
    ref_word = db.query(ReferenceWord).filter(
        ReferenceWord.word_id == challenge.ref_word_id
    ).first()
    ref_correct = texts_match(ref_answer, ref_word.correct_text)

    # ── Record the attempt ───────────────────────────────────────────────
    attempt = Attempt(
        challenge_id=challenge_id,
        attempt_number=attempt_count + 1,
        reference_input_text=ref_answer,
        reference_input_normalized=normalize_arabic(ref_answer),
        low_conf_input_text=low_conf_answer,
        low_conf_input_normalized=normalize_arabic(low_conf_answer),
        passed=ref_correct,
        response_time_ms=response_time_ms,
        signals_json=signals_json,
    )
    db.add(attempt)
    db.flush()

    # ── Log behavior signals ─────────────────────────────────────────────
    if signals_json:
        import json
        log_payload = {
            "raw_signals": json.loads(signals_json) if isinstance(signals_json, str) else signals_json,
            "score_breakdown": final_breakdown,
            "initial_score": initial_score,
            "final_score": final_score,
        }
        log = BehaviorLog(
            session_id=challenge.session_id,
            event_type="solve_attempt",
            signals_json=json.dumps(log_payload, ensure_ascii=False),
        )
        db.add(log)

    # ── Persist final bot score on the session ───────────────────────────
    site_session = db.query(SiteSession).filter(
        SiteSession.session_id == challenge.session_id
    ).first()
    if site_session:
        # bot_score_final column should exist (add via migration below)
        if hasattr(site_session, "bot_score_final"):
            site_session.bot_score_final = final_score

    # ── Handle escalation: bot detected mid-challenge ────────────────────
    if score_escalated and not ref_correct:
        # Upgrade the challenge to a harder tier
        from app.services.challenge_service import upgrade_challenge_difficulty
        updated = upgrade_challenge_difficulty(challenge_id, final_score, db)

        db.commit()
        print(f"🚨 Score escalated {initial_score:.2f}→{final_score:.2f}. "
              f"Challenge upgraded to {updated.difficulty}")

        return {
            "passed": False,
            "attempts_left": updated.max_attempts,
            "token": None,
            "needs_upgrade": True,
            "new_difficulty": updated.difficulty,
            "new_composite_url": getattr(updated, "composite_image_url", None),
            "bot_score_final": round(final_score, 4),
        }

    # ── Normal path: answer was correct ─────────────────────────────────
    token = None
    if ref_correct:
        submission = LowConfidenceSubmission(
            low_conf_word_id=challenge.low_conf_word_id,
            attempt_id=attempt.attempt_id,
            submitted_text=low_conf_answer,
            normalized_text=normalize_arabic(low_conf_answer),
        )
        db.add(submission)
        challenge.status = "passed"
        challenge.is_human_verified = True
        token = str(uuid.uuid4())

        db.commit()
        update_consensus(challenge.low_conf_word_id, db)
    else:
        if attempt_count + 1 >= challenge.max_attempts:
            challenge.status = "failed"
        db.commit()

    attempts_left = challenge.max_attempts - (attempt_count + 1)

    return {
        "passed": ref_correct,
        "attempts_left": max(attempts_left, 0),
        "token": token,
        "needs_upgrade": False,
        "new_difficulty": None,
        "new_composite_url": None,
        "bot_score_final": round(final_score, 4),
    }