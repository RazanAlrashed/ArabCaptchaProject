'''
"""
utils/bot_scorer.py

Calculates a bot suspicion score (0–100) from behavioral signals.
Uses configurable weights from config.py.
"""
import json
from app.core.config import settings


def calculate_bot_score(signals_json: str | None) -> float:
    """
    Analyze behavior signals and return a bot score (0–100).

    Expected signals_json keys:
      - submit_time_ms: int      (time from page load to form submit)
      - paste_used: bool          (user pasted the answer)
      - mouse_moves: int          (number of mouse move events)
      - scroll_events: int        (number of scroll events)
      - webdriver: bool           (navigator.webdriver flag)
      - first_interaction_ms: int (time to first keystroke/click)
      - focus_blur_count: int     (number of tab switches)
      - failed_attempts: int      (previous failed attempts count)
    """
    if not signals_json:
        return 0.0

    try:
        signals = json.loads(signals_json) if isinstance(signals_json, str) else signals_json
    except (json.JSONDecodeError, TypeError):
        return 0.0

    score = 0.0

    # Fast submit (< 800ms)
    submit_time = signals.get("submit_time_ms", 5000)
    if submit_time < 800:
        score += settings.WEIGHT_FAST_SUBMIT

    # Paste used
    if signals.get("paste_used", False):
        score += settings.WEIGHT_PASTE_USED

    # No mouse movement AND no scroll
    mouse_moves = signals.get("mouse_moves", 1)
    scroll_events = signals.get("scroll_events", 1)
    if mouse_moves == 0 and scroll_events == 0:
        score += settings.WEIGHT_NO_MOUSE

    # Webdriver detected
    if signals.get("webdriver", False):
        score += settings.WEIGHT_WEBDRIVER

    # First interaction too fast (< 150ms)
    first_interaction = signals.get("first_interaction_ms", 500)
    if first_interaction is not None and first_interaction < 150:
        score += settings.WEIGHT_FAST_FIRST_INTERACTION

    # Excessive tab switching (> 3 times)
    focus_blur = signals.get("focus_blur_count", 0)
    if focus_blur > 3:
        score += settings.WEIGHT_FOCUS_BLUR

    # Too many failed attempts (>= 3)
    failed_attempts = signals.get("failed_attempts", 0)
    if failed_attempts >= 3:
        score += settings.WEIGHT_TOO_MANY_ATTEMPTS

    return min(score, 100.0)


def determine_risk_level(bot_score: float) -> str:
    """Map a bot score to a risk level: low / med / high."""
    if bot_score < settings.LOW_RISK_THRESHOLD:
        return "low"
    elif bot_score < settings.HIGH_RISK_THRESHOLD:
        return "med"
    else:
        return "high"


def determine_difficulty(bot_score: float) -> str:
    """Map a bot score to challenge difficulty: easy / medium / hard."""
    if bot_score < settings.LOW_RISK_THRESHOLD:
        return "easy"
    elif bot_score < settings.HIGH_RISK_THRESHOLD:
        return "medium"
    else:
        return "hard"
'''


"""
utils/bot_scorer.py

Phase 1: Rule-based human-confidence scoring (0.0 = bot, 1.0 = human).
Phase 2 ready: every signal is stored in a structured dict so it can be
               exported as a feature vector for ML training later.

Score bands:
  >= 0.8  → trusted human  → skip challenge entirely
  0.5–0.8 → likely human   → easy challenge
  0.3–0.5 → suspicious     → medium challenge
  < 0.3   → likely bot     → hard challenge
"""
import json
import math


# ─────────────────────────────────────────────────────────────
# WEIGHTS — all in one place so they're easy to tune manually
# now and easy to replace with learned weights in Phase 2.
# ─────────────────────────────────────────────────────────────
W = {
    # Hard bot indicators
    "webdriver":                   -0.45,
    "paste_used":                  -0.15,
    "no_mouse_no_scroll":          -0.50,

    # Timing — bot penalties
    "first_interaction_superhuman": -0.40,   # < 100 ms
    "first_interaction_fast":       -0.10,   # 100–300 ms
    "submit_superhuman":            -0.40,   # < 500 ms
    "submit_fast":                  -0.05,   # 500–2000 ms
    "time_on_page_short":           -0.10,   # < 1000 ms

    # Timing — human bonuses
    "first_interaction_natural":   +0.20,   # 300–8000 ms
    "submit_natural":              +0.10,   # 2000–60000 ms
    "time_on_page_ok":             +0.05,   # > 2000 ms

    # Mouse
    "good_mouse_activity":         +0.10,   # > 20 moves
    "robotic_mouse_pattern":       -0.30,
    "mouse_speed_superhuman":      -0.10,   # avg > 5 px/ms

    # Keyboard
    "robotic_keystroke_rhythm":    -0.40,
    "natural_keystroke_rhythm":    +0.10,
    "superhuman_key_release":      -0.10,
    "natural_key_hold":            +0.05,

    # Device
    "touch_device":                +0.15,
    "headless_screen_size":        -0.35,   # 800×600 (Puppeteer default)
    "common_headless_size":        -0.05,   # 1280×720 without touch

    # Session history
    "excessive_tab_switching":     -0.10,   # focus_blur > 5
    "tab_hidden_frequently":       -0.05,   # tab_hidden > 3
    "too_many_failures":           -0.20,   # failed >= 3
    "some_failures":               -0.05,   # failed >= 1
}


def calculate_bot_score(signals_json: str | None) -> tuple[float, dict]:
    """
    Returns:
      score   float  0.0 (bot) → 1.0 (human)
      details dict   every signal's contribution — stored in DB for Phase 2
    """
    # ── Parse ────────────────────────────────────────────────────────────
    if not signals_json:
        return 0.5, {"note": "no_signals"}

    try:
        s = json.loads(signals_json) if isinstance(signals_json, str) else signals_json
    except (json.JSONDecodeError, TypeError):
        return 0.5, {"note": "parse_error"}

    score = 0.5        # neutral start
    details = {}       # signal_name → weight applied (0 if not triggered)

    def apply(key: str, condition: bool):
        """Apply a weight if condition is True; always record the signal."""
        w = W.get(key, 0.0)
        if condition:
            details[key] = w
            return w
        details[key] = 0.0
        return 0.0

    # ════════════════════════════════════════════
    # 1. HARD BOT INDICATORS
    # ════════════════════════════════════════════
    score += apply("webdriver",          s.get("webdriver", False))
    score += apply("paste_used",         s.get("paste_used", False))
    score += apply("no_mouse_no_scroll",
                   s.get("mouse_moves", 0) == 0 and s.get("scroll_events", 0) == 0)

    # ════════════════════════════════════════════
    # 2. TIMING
    # ════════════════════════════════════════════
    first_ms = s.get("first_interaction_ms")
    if first_ms is not None:
        score += apply("first_interaction_superhuman", first_ms < 100)
        score += apply("first_interaction_fast",       100 <= first_ms < 300)
        score += apply("first_interaction_natural",    300 <= first_ms <= 8000)

    submit_ms = s.get("submit_time_ms")
    if submit_ms is not None:
        score += apply("submit_superhuman", submit_ms < 500)
        score += apply("submit_fast",       500 <= submit_ms < 2000)
        score += apply("submit_natural",    2000 <= submit_ms <= 60000)

    time_on_page = s.get("time_on_page_ms", 0)
    score += apply("time_on_page_short", time_on_page < 1000)
    score += apply("time_on_page_ok",    time_on_page >= 2000)

    # ════════════════════════════════════════════
    # 3. MOUSE
    # ════════════════════════════════════════════
    mouse_moves   = s.get("mouse_moves", 0)
    path_length   = s.get("mouse_path_length", 0)
    mouse_speed   = s.get("mouse_speed_avg", 0)

    score += apply("good_mouse_activity",    mouse_moves > 20)
    score += apply("mouse_speed_superhuman", mouse_speed > 5.0)

    # Robotic mouse: many events but very short total path = straight lines
    if mouse_moves > 5 and path_length > 0:
        moves_per_px = mouse_moves / max(path_length, 1)
        score += apply("robotic_mouse_pattern", moves_per_px > 0.5)
    else:
        details["robotic_mouse_pattern"] = 0.0

    # ════════════════════════════════════════════
    # 4. KEYBOARD
    # ════════════════════════════════════════════
    intervals = s.get("keystroke_intervals", [])
    key_holds  = s.get("key_hold_durations", [])

    if len(intervals) >= 3:
        avg_i = sum(intervals) / len(intervals)
        var_i = sum((x - avg_i) ** 2 for x in intervals) / len(intervals)
        score += apply("robotic_keystroke_rhythm", var_i < 10 and avg_i < 200)
        score += apply("natural_keystroke_rhythm", var_i > 500)
    else:
        details["robotic_keystroke_rhythm"] = 0.0
        details["natural_keystroke_rhythm"]  = 0.0

    if len(key_holds) >= 3:
        avg_h = sum(key_holds) / len(key_holds)
        score += apply("superhuman_key_release", avg_h < 20)
        score += apply("natural_key_hold",       50 <= avg_h <= 300)
    else:
        details["superhuman_key_release"] = 0.0
        details["natural_key_hold"]        = 0.0

    # ════════════════════════════════════════════
    # 5. DEVICE & ENVIRONMENT
    # ════════════════════════════════════════════
    touch = s.get("touch_events", 0)
    score += apply("touch_device", touch > 0)

    sw, sh = s.get("screen_width", 0), s.get("screen_height", 0)
    score += apply("headless_screen_size",  sw == 800  and sh == 600)
    score += apply("common_headless_size",  sw == 1280 and sh == 720 and touch == 0)

    # ════════════════════════════════════════════
    # 6. SESSION HISTORY
    # ════════════════════════════════════════════
    score += apply("excessive_tab_switching", s.get("focus_blur_count", 0) > 5)
    score += apply("tab_hidden_frequently",   s.get("tab_hidden_count", 0) > 3)

    failed = s.get("failed_attempts", 0)
    score += apply("too_many_failures", failed >= 3)
    score += apply("some_failures",     1 <= failed < 3)

    # ════════════════════════════════════════════
    # Final — clamp to [0.0, 1.0]
    # ════════════════════════════════════════════
    final = round(max(0.0, min(1.0, score)), 4)
    details["_final_score"] = final
    details["_phase"] = "rule_based_v1"   # tag for Phase 2 migration tracking

    return final, details


def determine_risk_level(score: float) -> str:
    """0.0 = bot, 1.0 = human."""
    if score >= 0.8:
        return "trusted"
    elif score >= 0.65:
        return "low"
    elif score >= 0.30:
        return "medium"
    else:
        return "high"


def determine_difficulty(score: float) -> str:
    """Returns challenge difficulty based on human-confidence score."""
    if score >= 0.8:
        return "none"      # skip challenge entirely
    elif score >= 0.65:
        return "easy"
    elif score >= 0.30:
        return "medium"
    else:
        return "hard"


def needs_challenge(score: float) -> bool:
    """True if user should be shown a challenge."""
    return score < 0.8