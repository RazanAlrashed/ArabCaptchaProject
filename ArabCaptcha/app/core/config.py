"""
core/config.py

This file holds all application settings.
Change values here to tune the system behavior without touching any logic code.
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite (development). To switch to MySQL, change to:
    # "mysql+pymysql://user:password@localhost/arabcaptcha"
    DATABASE_URL: str = "sqlite:///./arabcaptcha.db"
    
    COLAB_OCR_URL: str = "https://nonactionable-donnetta-refracturable.ngrok-free.dev/"
    OCR_CONFIDENCE_THRESHOLD: float = 0.85
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    ASSETS_DIR: Path = BASE_DIR / "assets"
    WORDS_DIR: Path = ASSETS_DIR / "words"

    # ── Bot Score Thresholds ─────────────────────────────────────────────────
    # Score is 0-100. Higher = more suspicious.
    # Scores below LOW_RISK_THRESHOLD → Easy CAPTCHA
    # Scores between LOW and HIGH    → Medium CAPTCHA
    # Scores above HIGH_RISK_THRESHOLD → Hard/Rejected CAPTCHA
    #LOW_RISK_THRESHOLD: int = 20
    #HIGH_RISK_THRESHOLD: int = 60

    # ── Bot Score Signal Weights ──────────────────────────────────────────────
    # Points added to the bot score when each suspicious signal is detected.
    # Increase a weight to be stricter about that signal.
    #WEIGHT_FAST_SUBMIT: int = 50      # Submitted in < 800ms
    #WEIGHT_PASTE_USED: int = 25       # Answer was pasted, not typed
    #WEIGHT_NO_MOUSE: int = 40         # Zero mouse moves AND zero scrolls
    #WEIGHT_WEBDRIVER: int = 80        # Browser is controlled by automation (Selenium, etc.)
    #WEIGHT_FAST_FIRST_INTERACTION: int = 15  # First keystroke/click in < 150ms
    #WEIGHT_FOCUS_BLUR: int = 10       # Switched tabs > 3 times
    WEIGHT_TOO_MANY_ATTEMPTS: int = 15  # Failed the challenge >= 3 times

    # ── Consensus (Crowdsourcing) Settings ───────────────────────────────────
    # Minimum number of trusted votes before we evaluate a low-confidence word.
    MIN_VOTES_REQUIRED_FOR_CONSENSUS: int = 3

    # What fraction of votes must agree on the same text to accept it as correct.
    # e.g. 0.70 means 70% must agree.
    CONSENSUS_AGREEMENT_RATIO: float = 0.70

    # If a word gets this many attempts and still has no consensus, mark it as unreadable.
    MAX_ATTEMPTS_BEFORE_DISCARD: int = 50

    # ── Challenge Settings ───────────────────────────────────────────────────
    # How many minutes before an unsolved challenge expires.
    CHALLENGE_EXPIRY_MINUTES: int = 3

    # Maximum number of solve attempts allowed per challenge.
    MAX_CHALLENGE_ATTEMPTS: int = 3

    class Config:
        env_file = ".env"          # Optional: override any value via a .env file
        extra = "ignore"


# A single shared instance used across the entire application.
settings = Settings()

# في آخر سطر بالملف بعد settings = Settings()
print(f"DEBUG: Application is connecting to: {settings.DATABASE_URL}")