-- emoji-db-cleanup.sql — REVIEW BEFORE RUNNING. Nothing here has been executed.
--
-- Produced by the Step 3 read-only audit, which scanned all 74 text / varchar /
-- json / jsonb columns across all 12 public tables on the DIRECT Neon endpoint
-- (ep-…-aghgayzr.c-2…, not the -pooler host) for characters in:
--     U+1F300-U+1FAFF, U+2600-U+27BF, U+2190-U+21FF, U+2B00-U+2BFF,
--     U+FE0F, U+FE0E, U+200D
--
-- Exactly two rows matched. The decision tree itself is clean: categories
-- .tree_json, every scenarios.* text and JSONB column, and questions
-- .wizard_path contain no flagged characters at all.
--
-- The ranges are written as U& escapes rather than pasted literals, so this
-- file stays correct through any editor, terminal or clipboard that would
-- otherwise mangle an astral-plane character.
--
-- Run inside the transaction below and read the verification SELECTs before
-- you swap ROLLBACK for COMMIT.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. categories.icon, id = 11 (slug 'moving_in')  —  U+1F511  KEY
--
-- This column already stores Lucide icon NAMES elsewhere: id=3 holds 'tool',
-- id=5 holds 'file-text'. Row 11 is the only one holding a literal emoji, so
-- the consistent fix is the matching Lucide name, not a blank.
--
-- Know this before running: templates/core/dashboard.html does NOT read this
-- column. It selects its icon from a hardcoded {% if cat.slug %} chain, which
-- the Step 2 pass converted to inline Lucide SVG. This row is therefore inert
-- today — updating it changes no rendered page, but it stops the emoji
-- resurfacing if the column is ever wired up.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE categories
   SET icon = 'key'
 WHERE id = 11
   AND icon = U&'\+01F511';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. lawyer_profiles.office_address, id = 22  —  U+2192 RIGHTWARDS ARROW,
--                                                U+273B TEARDROP ASTERISK
--
-- READ THIS BEFORE CHOOSING. The field does not contain an address. It holds
-- roughly 37 KB of a pasted Claude Code terminal transcript — shell commands,
-- pip install output, stack traces — and the two flagged characters are that
-- terminal's own UI chrome, not text anyone typed deliberately.
--
-- So stripping the two characters would satisfy the emoji scan while leaving
-- 37 KB of garbage in a public-facing profile field. Option B is almost
-- certainly what you want. Pick one; do not run both.
--
-- Separately worth a look: a varchar/text profile field accepted a 37 KB paste
-- with no length validation. That is a real input-validation gap, not part of
-- this cleanup.

-- Option A — minimal: strip only the flagged characters, keep the text.
-- UPDATE lawyer_profiles
--    SET office_address = regexp_replace(
--          office_address,
--          U&'[\+01F300-\+01FAFF\2600-\27BF\2190-\21FF\2B00-\2BFF\FE0E\FE0F\200D]',
--          '', 'g')
--  WHERE id = 22;

-- Option B — recommended: the field is junk test data, so clear it.
-- UPDATE lawyer_profiles
--    SET office_address = NULL
--  WHERE id = 22;

-- ─────────────────────────────────────────────────────────────────────────────
-- Verification. Both must return zero rows before you COMMIT.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT id, slug, icon
  FROM categories
 WHERE icon ~ U&'[\+01F300-\+01FAFF\2600-\27BF\2190-\21FF\2B00-\2BFF\FE0E\FE0F\200D]';

SELECT id, left(office_address, 80) AS office_address_head
  FROM lawyer_profiles
 WHERE office_address ~ U&'[\+01F300-\+01FAFF\2600-\27BF\2190-\21FF\2B00-\2BFF\FE0E\FE0F\200D]';

-- Swap these two lines once the SELECTs above come back empty.
ROLLBACK;
-- COMMIT;
