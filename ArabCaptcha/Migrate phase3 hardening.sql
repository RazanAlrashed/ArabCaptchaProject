-- ─────────────────────────────────────────────────────────────
-- migrate_phase3_hardening.sql
-- Run ONCE on your arabcaptcha.db
--
-- Adds:
--   challenge.composite_image_url  — path to the stitched distorted PNG
--   challenge.ref_end_x            — pixel x where ref word ends in composite
--   site_session.bot_score_final   — bot score computed during challenge
--   site_session.needs_challenge   — (already in phase2 migration, safe to re-run)
-- ─────────────────────────────────────────────────────────────

-- challenge table additions
ALTER TABLE challenge ADD COLUMN composite_image_url TEXT;
ALTER TABLE challenge ADD COLUMN ref_end_x           INTEGER DEFAULT -1;

-- site_session table additions
ALTER TABLE site_session ADD COLUMN bot_score_final  REAL;
ALTER TABLE site_session ADD COLUMN needs_challenge  BOOLEAN DEFAULT 1;

-- ─────────────────────────────────────────────────────────────
-- Phase 3 training view (extends the Phase 2 view)
-- Adds bot_score_final and the escalation delta signal.
-- ─────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_training_export;

CREATE VIEW v_training_export AS
SELECT
    s.session_id,
    s.bot_score_initial,
    s.bot_score_final,
    -- Escalation delta: how much the score changed during the challenge
    -- Large positive value = bot that passed initial checks
    ROUND(COALESCE(s.bot_score_initial, 0.5) - COALESCE(s.bot_score_final, 0.5), 4)
        AS score_escalation_delta,
    s.needs_challenge,
    s.risk_level,
    b.signals_json,
    c.difficulty,
    c.composite_image_url,
    -- Ground truth label for ML training
    CASE
        WHEN s.needs_challenge = 0 THEN NULL    -- trusted, never challenged
        WHEN c.is_human_verified = 1 THEN 1     -- passed → human
        WHEN c.status = 'failed'    THEN 0      -- failed → bot
        ELSE NULL
    END AS outcome
FROM site_session s
LEFT JOIN behavior_log b
       ON b.session_id = s.session_id
      AND b.event_type = 'session_init'
LEFT JOIN challenge c
       ON c.session_id = s.session_id
ORDER BY s.session_created_at DESC;

-- ─────────────────────────────────────────────────────────────
-- Index to speed up consensus lookups
-- ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_challenge_session  ON challenge(session_id);
CREATE INDEX IF NOT EXISTS idx_challenge_status   ON challenge(status);
CREATE INDEX IF NOT EXISTS idx_attempt_challenge  ON attempt(challenge_id);