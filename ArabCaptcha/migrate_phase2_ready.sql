-- ─────────────────────────────────────────────────────────────
-- migrate_phase2_ready.sql
-- Run this ONCE on your existing arabcaptcha.db
-- ─────────────────────────────────────────────────────────────

-- 1. Add needs_challenge to site_session
--    (so you can query it later without re-scoring)
ALTER TABLE site_session ADD COLUMN needs_challenge BOOLEAN DEFAULT 1;

-- 2. Create a Phase 2 training view.
--    When you have 100+ sessions, run:
--      SELECT * FROM v_training_export;
--    and use that CSV to train your ML model.
--
--    Columns:
--      session_id       — row identifier
--      bot_score        — the score we gave (your current label proxy)
--      needs_challenge  — what decision we made
--      risk_level       — trusted / low / medium / high
--      signals_json     — raw signals + breakdown (your feature vector)
--      outcome          — did they pass the challenge? (ground truth label)
--
CREATE VIEW IF NOT EXISTS v_training_export AS
SELECT
    s.session_id,
    s.bot_score_initial          AS bot_score,
    s.needs_challenge,
    s.risk_level,
    b.signals_json,              -- contains raw_signals + score_breakdown
    -- outcome: 1 = human confirmed, 0 = failed/bot, NULL = skipped challenge
    CASE
        WHEN s.needs_challenge = 0 THEN NULL   -- trusted, no challenge shown
        WHEN c.is_human_verified = 1 THEN 1    -- passed challenge → human
        WHEN c.status = 'failed'     THEN 0    -- failed challenge → bot
        ELSE NULL
    END AS outcome
FROM site_session s
LEFT JOIN behavior_log b
       ON b.session_id = s.session_id
      AND b.event_type = 'session_init'
LEFT JOIN challenge c
       ON c.session_id = s.session_id
ORDER BY s.session_created_at DESC;