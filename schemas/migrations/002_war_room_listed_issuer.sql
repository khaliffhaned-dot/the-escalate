-- NADI — listed-issuer state on war rooms (Bursa Malaysia Main / ACE Market).
-- Run after 001. Adds one nullable JSONB column; existing rows are untouched.
--
-- `listed` holds the materiality assessment, insider lock, regulatory clock board
-- and trading-halt record (see src/nadi/domain/listed.py). The row-level-security
-- policy from 001 already covers the whole row, so nothing new is needed there.
--
-- Same discipline as the other product invariants: the database itself refuses a
-- row that claims the app files with a regulator on anyone's behalf.

ALTER TABLE war_rooms ADD COLUMN IF NOT EXISTS listed JSONB;

ALTER TABLE war_rooms DROP CONSTRAINT IF EXISTS chk_war_room_listed_no_auto_file;
ALTER TABLE war_rooms ADD CONSTRAINT chk_war_room_listed_no_auto_file
    CHECK ((listed->>'auto_file')::boolean IS NOT TRUE);
