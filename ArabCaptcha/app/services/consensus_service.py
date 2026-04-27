"""
services/consensus_service.py

Updates crowdsourcing consensus after each trusted submission.
Determines if a low-confidence word has reached agreement or should be discarded.
"""
from datetime import datetime
from collections import Counter

from sqlalchemy.orm import Session

from app.db.models import LowConfidenceWord, LowConfidenceSubmission, LowConfidenceConsensus
from app.core.config import settings


def update_consensus(low_conf_word_id: int, db: Session) -> None:
    """
    Recalculate consensus for a given low-confidence word:
      1. Gather all trusted submissions (normalized text)
      2. Find the most common answer
      3. Update or create the consensus record
      4. If enough votes + agreement → mark as verified
      5. If too many attempts without consensus → mark as unreadable
    """
    # ── Gather all submissions ───────────────────────────────────────────
    submissions = (
        db.query(LowConfidenceSubmission)
        .filter(LowConfidenceSubmission.low_conf_word_id == low_conf_word_id)
        .all()
    )

    total = len(submissions)
    if total == 0:
        return

    # ── Count votes per normalized text ──────────────────────────────────
    vote_counts = Counter(s.normalized_text for s in submissions)
    top_text, top_votes = vote_counts.most_common(1)[0]
    ratio = top_votes / total

    # ── Update or create consensus record ────────────────────────────────
    consensus = db.query(LowConfidenceConsensus).filter(
        LowConfidenceConsensus.low_conf_word_id == low_conf_word_id
    ).first()

    if not consensus:
        consensus = LowConfidenceConsensus(
            low_conf_word_id=low_conf_word_id,
            top_candidate_text=top_text,
            votes=top_votes,
            total=total,
            ratio=ratio,
        )
        db.add(consensus)
    else:
        consensus.top_candidate_text = top_text
        consensus.votes = top_votes
        consensus.total = total
        consensus.ratio = ratio

    # ── Check if consensus is reached ────────────────────────────────────
    lc_word = db.query(LowConfidenceWord).filter(
        LowConfidenceWord.word_id == low_conf_word_id
    ).first()

    if lc_word:
        lc_word.total_votes = total

        if total >= settings.MIN_VOTES_REQUIRED_FOR_CONSENSUS and ratio >= settings.CONSENSUS_AGREEMENT_RATIO:
            # Consensus reached → verify the word
            consensus.is_verified = True
            lc_word.status = "verified"
            lc_word.verified_text = top_text
            lc_word.verified_at = datetime.utcnow()

        elif total >= settings.MAX_ATTEMPTS_BEFORE_DISCARD:
            # Too many attempts with no agreement → unreadable
            lc_word.status = "unreadable"

    db.commit()
