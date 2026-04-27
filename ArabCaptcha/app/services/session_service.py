'''
"""
services/session_service.py

Handles session creation: validates API key, computes bot score,
determines risk level, and persists the session.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import ClientSite, ClientDomain, SiteSession, BehaviorLog
from app.utils.hashing import hash_api_key
from app.utils.bot_scorer import calculate_bot_score, determine_risk_level


def create_session(
    api_key: str,
    domain: str,
    signals_json: str | None,
    db: Session,
) -> SiteSession:
    """
    1. Hash the API key and look up the client site.
    2. Verify the domain is allowed.
    3. Calculate initial bot score from signals.
    4. Create and return a SiteSession.
    """
    # ── Validate API key ──────────────────────────────────────────────────
    key_hash = hash_api_key(api_key)
    site = db.query(ClientSite).filter(ClientSite.api_key_hash == key_hash).first()
    if not site:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if site.status != "active":
        raise HTTPException(status_code=403, detail="Site is inactive")

    # ── Validate domain ──────────────────────────────────────────────────
    allowed = db.query(ClientDomain).filter(
        ClientDomain.site_id == site.site_id,
        ClientDomain.domain_url == domain,
    ).first()
    if not allowed:
        raise HTTPException(status_code=403, detail="Domain not authorized")

    # ── Bot score ────────────────────────────────────────────────────────
    bot_score = calculate_bot_score(signals_json)
    risk_level = determine_risk_level(bot_score)

    # ── Create session ───────────────────────────────────────────────────
    session = SiteSession(
        site_id=site.site_id,
        bot_score_initial=bot_score,
        risk_level=risk_level,
        status="active",
    )
    db.add(session)
    db.flush()  # ensure session_id is generated before referencing it

    # ── Log behavior signals ─────────────────────────────────────────────
    if signals_json:
        log = BehaviorLog(
            session_id=session.session_id,
            event_type="session_init",
            signals_json=signals_json,
        )
        db.add(log)

    db.commit()
    db.refresh(session)
    return session
'''


"""
services/session_service.py

Handles session creation: validates API key, computes bot score,
determines risk level, and persists the session.

Phase 2 note:
  score_breakdown (JSON) is saved in behavior_log so every session
  becomes a labeled training row once you add is_human ground truth.
"""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import ClientSite, ClientDomain, SiteSession, BehaviorLog
from app.utils.hashing import hash_api_key
from app.utils.bot_scorer import (
    calculate_bot_score,
    determine_risk_level,
    needs_challenge,
)


def create_session(
    api_key: str,
    domain: str,
    signals_json: str | None,
    db: Session,
) -> SiteSession:
    """
    1. Hash the API key and look up the client site.
    2. Verify the domain is allowed.
    3. Calculate human-confidence score (0.0–1.0) from signals.
    4. Persist session + behavior log with full score breakdown.
    5. Return SiteSession with needs_challenge flag attached.
    """
    # ── Validate API key ──────────────────────────────────────────────────
    key_hash = hash_api_key(api_key)
    site = db.query(ClientSite).filter(ClientSite.api_key_hash == key_hash).first()
    if not site:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if site.status != "active":
        raise HTTPException(status_code=403, detail="Site is inactive")

    # ── Validate domain ───────────────────────────────────────────────────
    allowed = db.query(ClientDomain).filter(
        ClientDomain.site_id == site.site_id,
        ClientDomain.domain_url == domain,
    ).first()
    if not allowed:
        raise HTTPException(status_code=403, detail="Domain not authorized")

    # ── Bot score ─────────────────────────────────────────────────────────
    score, breakdown = calculate_bot_score(signals_json)
    risk_level = determine_risk_level(score)

    # Console log for monitoring during early stage
    triggered = [k for k, v in breakdown.items() if v != 0.0 and not k.startswith("_")]
    print(f"🤖 score={score} risk={risk_level} triggers={triggered}")

    # ── Create session ────────────────────────────────────────────────────
    session = SiteSession(
        site_id=site.site_id,
        bot_score_initial=score,
        risk_level=risk_level,
        status="active",
    )
    db.add(session)
    db.flush()  # generate session_id before referencing it

    # ── Log signals + breakdown ───────────────────────────────────────────
    # breakdown is stored in signals_json column as extended JSON.
    # This is the data you'll export for ML training in Phase 2.
    log_payload = {
        "raw_signals": json.loads(signals_json) if signals_json else {},
        "score_breakdown": breakdown,   # ← Phase 2: this becomes your feature vector
    }
    log = BehaviorLog(
        session_id=session.session_id,
        event_type="session_init",
        signals_json=json.dumps(log_payload, ensure_ascii=False),
    )
    db.add(log)

    db.commit()
    db.refresh(session)

    # Attach needs_challenge as a plain attribute (not a DB column).
    # The router reads it to build the response.
    session.needs_challenge = needs_challenge(score)
    return session
