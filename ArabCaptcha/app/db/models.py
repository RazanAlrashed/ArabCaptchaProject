"""
db/models.py

SQLAlchemy ORM models — one class per database table.
These are a direct translation of the agreed ER diagram.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT / SITE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class ClientSite(Base):
    """
    A website/application that integrates ArabCaptcha.
    Identified by a hashed API key (we never store the raw key).
    """
    __tablename__ = "client_site"

    site_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    domains: Mapped[list["ClientDomain"]] = relationship("ClientDomain", back_populates="site")
    sessions: Mapped[list["SiteSession"]] = relationship("SiteSession", back_populates="site")


class ClientDomain(Base):
    """
    Allowed domains for a given site.
    One site can have multiple valid domains/subdomains.
    """
    __tablename__ = "client_domain"

    domain_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("client_site.site_id"), nullable=False)
    domain_url: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    site: Mapped["ClientSite"] = relationship("ClientSite", back_populates="domains")


# ─────────────────────────────────────────────────────────────────────────────
# SESSION & BEHAVIOR TRACKING
# ─────────────────────────────────────────────────────────────────────────────

class SiteSession(Base):
    """
    Represents one user's browsing session on a client site.
    Stores initial and final bot scores after challenge completion.
    """
    __tablename__ = "site_session"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[int] = mapped_column(ForeignKey("client_site.site_id"), nullable=False)
    session_created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    bot_score_initial: Mapped[float | None] = mapped_column(Float, nullable=True)
    bot_score_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    # risk_level: "low" | "med" | "high"
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # status: "active" | "completed" | "expired"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Relationships
    site: Mapped["ClientSite"] = relationship("ClientSite", back_populates="sessions")
    behavior_logs: Mapped[list["BehaviorLog"]] = relationship("BehaviorLog", back_populates="session")
    challenges: Mapped[list["Challenge"]] = relationship("Challenge", back_populates="session")


class BehaviorLog(Base):
    """
    Raw behavioral events captured from the browser for a session.
    Stored as JSON so we can record any type of signal without schema changes.
    """
    __tablename__ = "behavior_log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("site_session.session_id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # event_type examples: "mouse_move", "keystroke", "paste", "submit"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    session: Mapped["SiteSession"] = relationship("SiteSession", back_populates="behavior_logs")


# ─────────────────────────────────────────────────────────────────────────────
# WORD / IMAGE LIBRARY  (Inheritance pattern: Word → ReferenceWord / LowConfidenceWord)
# ─────────────────────────────────────────────────────────────────────────────

class Word(Base):
    """
    Base table for every word image in the system.
    Subtype is indicated by word_type: "reference" or "low_confidence".
    """
    __tablename__ = "word"

    word_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # word_type: "reference" | "low_confidence"
    word_type: Mapped[str] = mapped_column(String(20), nullable=False)


class ReferenceWord(Base):
    """
    A word whose correct text is KNOWN.
    Used as the 'anchor' in every challenge — if the user fails this,
    their low-confidence answer is discarded.
    """
    __tablename__ = "reference_word"

    word_id: Mapped[int] = mapped_column(ForeignKey("word.word_id"), primary_key=True)
    correct_text: Mapped[str] = mapped_column(String(255), nullable=False)
    # source: where the word came from, e.g. "manual", "book_scan"
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    word: Mapped["Word"] = relationship("Word")
    challenges: Mapped[list["Challenge"]] = relationship("Challenge", back_populates="ref_word",
                                                          foreign_keys="Challenge.ref_word_id")


class LowConfidenceWord(Base):
    """
    A word whose text is UNKNOWN — crowdsourced answers build consensus.
    Once verified, verified_text is filled and status → "verified".
    """
    __tablename__ = "low_confidence_word"

    word_id: Mapped[int] = mapped_column(ForeignKey("word.word_id"), primary_key=True)
    initial_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # status: "pending" | "verified" | "unreadable"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    verified_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    word: Mapped["Word"] = relationship("Word")
    challenges: Mapped[list["Challenge"]] = relationship("Challenge", back_populates="low_conf_word",
                                                          foreign_keys="Challenge.low_conf_word_id")
    submissions: Mapped[list["LowConfidenceSubmission"]] = relationship("LowConfidenceSubmission",
                                                                         back_populates="low_conf_word")
    consensus: Mapped["LowConfidenceConsensus | None"] = relationship("LowConfidenceConsensus",
                                                                       back_populates="low_conf_word",
                                                                       uselist=False)


# ─────────────────────────────────────────────────────────────────────────────
# CHALLENGE & ATTEMPT
# ─────────────────────────────────────────────────────────────────────────────

class Challenge(Base):
    """
    One CAPTCHA challenge presented to a user.
    Always contains exactly one reference word + one low-confidence word.
    Difficulty is derived from the session's bot score.
    """
    __tablename__ = "challenge"

    challenge_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("site_session.session_id"), nullable=False)
    ref_word_id: Mapped[int] = mapped_column(ForeignKey("reference_word.word_id"), nullable=False)
    low_conf_word_id: Mapped[int] = mapped_column(ForeignKey("low_confidence_word.word_id"), nullable=False)
    bot_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # difficulty: "easy" | "medium" | "hard"
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, default="easy")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # status: "pending" | "passed" | "failed" | "expired"
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    is_human_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    composite_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    ref_end_x: Mapped[int | None] = mapped_column(Integer, nullable=True, default=-1)

    # Relationships
    session: Mapped["SiteSession"] = relationship("SiteSession", back_populates="challenges")
    ref_word: Mapped["ReferenceWord"] = relationship("ReferenceWord", back_populates="challenges",
                                                      foreign_keys=[ref_word_id])
    low_conf_word: Mapped["LowConfidenceWord"] = relationship("LowConfidenceWord", back_populates="challenges",
                                                               foreign_keys=[low_conf_word_id])
    attempts: Mapped[list["Attempt"]] = relationship("Attempt", back_populates="challenge")


class Attempt(Base):
    """
    One solve attempt within a challenge.
    Stores both raw and normalized text so consensus queries are fast.
    """
    __tablename__ = "attempt"

    attempt_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenge.challenge_id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Reference word inputs
    reference_input_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_input_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Low-confidence word inputs
    low_conf_input_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    low_conf_input_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    challenge: Mapped["Challenge"] = relationship("Challenge", back_populates="attempts")
    submission: Mapped["LowConfidenceSubmission | None"] = relationship("LowConfidenceSubmission",
                                                                         back_populates="attempt",
                                                                         uselist=False)


# ─────────────────────────────────────────────────────────────────────────────
# CROWDSOURCING — SUBMISSIONS & CONSENSUS
# ─────────────────────────────────────────────────────────────────────────────

class LowConfidenceSubmission(Base):
    """
    Created only when the user also passed the reference word.
    (Trust Gate) — untrusted answers are never inserted here.
    """
    __tablename__ = "low_confidence_submission"

    submission_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    low_conf_word_id: Mapped[int] = mapped_column(ForeignKey("low_confidence_word.word_id"), nullable=False)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempt.attempt_id"), nullable=False)
    submitted_text: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    low_conf_word: Mapped["LowConfidenceWord"] = relationship("LowConfidenceWord", back_populates="submissions")
    attempt: Mapped["Attempt"] = relationship("Attempt", back_populates="submission")


class LowConfidenceConsensus(Base):
    """
    Summary table updated each time a new trusted submission arrives.
    Stores the leading candidate text and vote statistics.
    When is_verified=True, the word is considered digitized successfully.
    """
    __tablename__ = "low_confidence_consensus"

    low_conf_word_id: Mapped[int] = mapped_column(ForeignKey("low_confidence_word.word_id"), primary_key=True)
    top_candidate_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    low_conf_word: Mapped["LowConfidenceWord"] = relationship("LowConfidenceWord", back_populates="consensus")
