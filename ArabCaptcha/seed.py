"""
seed.py

Populates the database with sample data for development and testing.
Run once after migrations:  python seed.py
"""
import sys
import os

# Make sure the app package is importable when running from the project root.
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import SessionLocal, engine, Base
from app.db.models import (
    ClientSite, ClientDomain,
    Word, ReferenceWord, LowConfidenceWord,
)
from app.utils.hashing import hash_api_key

# Create all tables (safe if they already exist)
Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        # ── 1. Demo client site ───────────────────────────────────────────────
        raw_key = "demo_secret_key"
        site = ClientSite(
            site_name="Demo Site",
            api_key_hash=hash_api_key(raw_key),
            status="active",
        )
        db.add(site)
        db.flush()  # flush to get site_id before adding domain

        domain = ClientDomain(site_id=site.site_id, domain_url="http://localhost")
        db.add(domain)

        # ── 2. Reference words (correct text known) ───────────────────────────
        ref_words_data = [
            ("الحجاز", "assets/words/word1.jpg", "manual"),
        ]
        for text, path, source in ref_words_data:
            w = Word(image_path=path, word_type="reference")
            db.add(w)
            db.flush()
            db.add(ReferenceWord(word_id=w.word_id, correct_text=text, source=source, active=True))

        # ── 3. Low-confidence words (correct text unknown) ────────────────────
        low_conf_data = [
            ("assets/words/word2.jpg", 0.40),
        ]
        for path, confidence in low_conf_data:
            w = Word(image_path=path, word_type="low_confidence")
            db.add(w)
            db.flush()
            db.add(LowConfidenceWord(word_id=w.word_id, initial_confidence=confidence, status="pending"))

        db.commit()
        print("✅ Seed complete!")
        print(f"   Demo API key  : {raw_key}")
        print(f"   Demo domain   : http://localhost")
        print(f"   Reference words added  : {len(ref_words_data)}")
        print(f"   Low-conf words added   : {len(low_conf_data)}")

    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
