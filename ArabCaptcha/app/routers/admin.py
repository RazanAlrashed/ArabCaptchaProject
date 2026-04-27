"""
routers/admin.py

Admin endpoints for managing words and viewing consensus data.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Word, ReferenceWord, LowConfidenceWord, LowConfidenceConsensus
from app.schemas.word import WordListItem, ConsensusDetail

router = APIRouter(prefix="/words", tags=["Admin"])


@router.get("", response_model=list[WordListItem])
def list_words(db: Session = Depends(get_db)):
    """List all words in the system (reference + low-confidence)."""
    words = db.query(Word).all()
    result = []
    for w in words:
        item = WordListItem(
            word_id=w.word_id,
            image_path=w.image_path,
            word_type=w.word_type,
            added_at=w.added_at,
        )
        if w.word_type == "reference":
            ref = db.query(ReferenceWord).filter(ReferenceWord.word_id == w.word_id).first()
            if ref:
                item.correct_text = ref.correct_text
                item.active = ref.active
        elif w.word_type == "low_confidence":
            lc = db.query(LowConfidenceWord).filter(LowConfidenceWord.word_id == w.word_id).first()
            if lc:
                item.status = lc.status
                item.verified_text = lc.verified_text
                item.total_votes = lc.total_votes
        result.append(item)
    return result


@router.patch("/{word_id}/activate")
def toggle_word_activation(word_id: int, active: bool = True, db: Session = Depends(get_db)):
    """Activate or deactivate a reference word."""
    ref = db.query(ReferenceWord).filter(ReferenceWord.word_id == word_id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference word not found")
    ref.active = active
    db.commit()
    return {"word_id": word_id, "active": active}


@router.get("/{word_id}/consensus", response_model=ConsensusDetail)
def get_word_consensus(word_id: int, db: Session = Depends(get_db)):
    """Get consensus details for a low-confidence word."""
    consensus = db.query(LowConfidenceConsensus).filter(
        LowConfidenceConsensus.low_conf_word_id == word_id
    ).first()
    if not consensus:
        raise HTTPException(status_code=404, detail="No consensus data for this word")
    return ConsensusDetail(
        low_conf_word_id=consensus.low_conf_word_id,
        top_candidate_text=consensus.top_candidate_text,
        votes=consensus.votes,
        total=consensus.total,
        ratio=consensus.ratio,
        is_verified=consensus.is_verified,
    )
