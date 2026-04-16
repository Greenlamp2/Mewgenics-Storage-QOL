import math
import re
import struct

import lz4.block

from catalogs.stat_catalog import STAT_NAMES
from utils.loaders import load_house_infos, load_adventure_keys, load_cats, load_pedigree, load_current_day
from utils.readers import BinaryReader
from catalogs.mutation_catalog import _VISUAL_MUTATION_FIELDS, _read_visual_mutation_entries, \
    _visual_mutation_chip_items

_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_JUNK_STRINGS = frozenset({"none", "null", "", "defaultmove", "default_move"})


def _valid_str(s) -> bool:
    """Reject None, empty, and game filler strings like 'none' or 'defaultmove'."""
    return bool(s) and s.strip().lower() not in _JUNK_STRINGS

class Cat:
    parent_a = None
    parent_b = None
    generation = 0
    is_blacklisted = False
    must_breed = False
    passive_abilities = []

    def _normalize_gender(self, raw_gender):
        """
        Normalize save-data gender variants to app-level values:
          - maleX   -> "male"
          - femaleX -> "female"
          - spidercat (ditto-like) -> "?"
        """
        g = (raw_gender or "").strip().lower()
        if g.startswith("male"):
            return "male"
        if g.startswith("female"):
            return "female"
        if g == "spidercat":
            return "?"
        return "?"

    def _read_db_key_candidates(self, raw: bytes, self_key: int, offsets: tuple[int, ...], base_offset: int = 0) -> list[int]:
        keys: list[int] = []
        for off in offsets:
            pos = base_offset + off
            if pos < 0 or pos + 4 > len(raw):
                continue
            try:
                value = struct.unpack_from('<I', raw, pos)[0]
            except Exception:
                continue
            if value in (0, 0xFFFF_FFFF) or value == self_key:
                continue
            if value not in keys:
                keys.append(value)
        return keys

    def __init__(self, blob, cat_key, house_info, adventure_keys, current_day=None):
        uncomp_size = struct.unpack('<I', blob[:4])[0]
        raw = lz4.block.decompress(blob[4:], uncompressed_size=uncomp_size)
        r = BinaryReader(raw)
        self._raw = raw  # kept for parent-UID blob scan in parse_save
        self.db_key = cat_key

        # Location / status
        if cat_key in adventure_keys:
            self.status = "Adventure"
            self.room   = "Adventure"
        elif cat_key in house_info:
            self.status = "In House"
            self.room   = house_info[cat_key]
        else:
            self.status = "Gone"
            self.room   = ""

        # Blob fields
        self.breed_id = r.u32()
        self._uid_int = r.u64()            # cat's own unique id (seed)
        self.unique_id = hex(self._uid_int)
        self.name = r.utf16str()

        # Optional post-name tag string (empty for most cats). Some fields below
        # are anchored to the byte immediately after this string.
        self.name_tag = r.str() or ""
        personality_anchor = r.pos
        self._personality_anchor = personality_anchor  # kept for serializer

        # Possible parent UIDs — fixed-position attempt.
        # parse_save will run a blob scan as a fallback if these don't resolve.
        self._parent_uid_a = r.u64()
        self._parent_uid_b = r.u64()

        self.collar = r.str() or ""
        r.u32()

        r.skip(64)
        T = [r.u32() for _ in range(72)]
        self._T = T  # kept for serializer / verification
        self.body_parts = {"texture": T[0], "bodyShape": T[3], "headShape": T[8]}
        self.visual_mutation_slots = {
            slot_key: T[table_index]
            for slot_key, table_index, *_ in _VISUAL_MUTATION_FIELDS
            if table_index < len(T)
        }
        visual_entries = _read_visual_mutation_entries(T)
        visual_items = _visual_mutation_chip_items(visual_entries)
        self.visual_mutation_entries = visual_entries
        self.visual_mutation_ids = [int(entry["mutation_id"]) for entry in visual_entries
                                    if not entry.get("is_defect")]
        # Separate normal mutations from birth defects
        visual_display_names = [text for text, _, is_def in visual_items if not is_def]
        defect_display_names = [text for text, _, is_def in visual_items if is_def]

        self.gender_token_fields = tuple(r.u32() for _ in range(3))
        raw_gender = r.str()
        self.gender_token = (raw_gender or "").strip().lower()
        # Authoritative sex enum near the name block:
        #   0 = male, 1 = female, 2 = undefined/both (ditto-like)
        # This byte follows the optional post-name tag string, so use the
        # tag-aware anchor (personality_anchor), not name_end + fixed offset.
        sex_code = raw[personality_anchor] if personality_anchor < len(raw) else None
        gender_from_code = {0: "male", 1: "female", 2: "?"}.get(sex_code)
        if gender_from_code:
            self.gender = gender_from_code
            self.gender_source = "sex_code"
        else:
            self.gender = self._normalize_gender(raw_gender)
            self.gender_source = "token_fallback"
        r.f64()

        self._pos_stat_base = r.pos
        self.stat_base = [r.u32() for _ in range(7)]
        self._pos_stat_mod = r.pos
        self.stat_mod  = [r.i32() for _ in range(7)]
        self._pos_stat_sec = r.pos
        self.stat_sec  = [r.i32() for _ in range(7)]

        self.base_stats  = {n: self.stat_base[i] for i, n in enumerate(STAT_NAMES)}
        self.total_stats = {n: self.stat_base[i] + self.stat_mod[i] + self.stat_sec[i]
                            for i, n in enumerate(STAT_NAMES)}

        # Personality stats (age, aggression, libido, inbredness).
        # Libido and inbredness are doubles anchored after the post-name tag string.
        # Age is stored as creation_day at offset (blob_len - 103), then calculated as (current_day - creation_day).
        self.age         = None
        self.aggression  = None   # None = unknown
        self.libido      = None
        self.inbredness  = None

        def _read_personality(offset: int):
            i = personality_anchor + offset
            if i + 8 > len(raw):
                return None
            try:
                v = struct.unpack_from('<d', raw, i)[0]
            except Exception:
                return None
            if not math.isfinite(v) or not (0.0 <= v <= 1.0):
                return None
            return float(v)

        self.libido = _read_personality(32)
        self.inbredness = _read_personality(40)
        self.aggression = _read_personality(64)

        # Parsed baseline values (before any manual calibration overrides).
        # NOTE: parsed_age is set after age extraction below.
        self.parsed_gender = self.gender
        self.parsed_aggression = self.aggression
        self.parsed_libido = self.libido
        self.parsed_inbredness = self.inbredness

        # Relationship slots: direct db_key references relative to the byte
        # immediately after the optional post-name tag string.
        self._lover_uids = self._read_db_key_candidates(raw, self.db_key, (48,), base_offset=personality_anchor)
        self._hater_uids = self._read_db_key_candidates(raw, self.db_key, (72,), base_offset=personality_anchor)
        self.lovers:   list['Cat'] = []
        self.haters:   list['Cat'] = []
        self.children: list['Cat'] = []   # direct offspring; assigned by parse_save

        # ── Ability run — anchored on "DefaultMove" ─────────────────────────
        # The ability block is a u64-length-prefixed ASCII identifier run.
        # Structure (from open-source editor research):
        #   items[0]  = "DefaultMove"  (active slot 1 default)
        #   items[1-5] = active abilities 2-6
        #   items[6-9] = padding / unknown slots
        #   items[10]  = Passive1 mutation  (e.g. "Sturdy", "Longshot")
        #   After run:  u32 tier, then 3 × [u64 id][u32 tier] tail entries
        #               = Passive2, Disorder1, Disorder2
        curr = r.pos
        run_start = -1
        for i in range(curr, min(curr + 600, len(raw) - 19)):
            lo = struct.unpack_from('<I', raw, i)[0]
            hi = struct.unpack_from('<I', raw, i + 4)[0]
            if hi != 0 or not (1 <= lo <= 96):
                continue
            try:
                cand = raw[i + 8: i + 8 + lo].decode('ascii')
                if cand == 'DefaultMove':
                    run_start = i
                    break
            except Exception:
                continue

        if run_start != -1:
            r.seek(run_start)
            # Read the full run until a non-identifier is encountered
            run_items: list[str] = []
            for _ in range(32):
                saved = r.pos
                item = r.str()
                if item is None or not _IDENT_RE.match(item):
                    r.seek(saved)
                    break
                run_items.append(item)

            # Active abilities: items[1-5] (skip DefaultMove at [0])
            self.abilities = [x for x in run_items[1:6] if _valid_str(x)]

            # Passive1 is in run_items[10] (if the run is long enough)
            passives: list[str] = []
            for ri in run_items[10:]:
                if _valid_str(ri):
                    passives.append(ri)

            # After run: [u32 tier][string][u32 tier][string]...
            # Passive1 tier, then Passive2, Disorder1, Disorder2 each with tier.
            # Skip Passive1's tier first, then read 3 more string+tier pairs.
            try:
                r.u32()   # passive1 tier — discard
            except Exception:
                pass

            # Tail slots: index 0 = Passive2, indices 1–2 = Disorder1/Disorder2.
            # Passive2 goes into passives; disorders are kept separate so they
            # don't appear twice in the UI (once as ● passive, once as ⚠ disorder).
            disorders: list[str] = []
            for tail_idx in range(3):
                try:
                    item = r.str()
                except Exception:
                    break
                if item is not None and _IDENT_RE.match(item) and _valid_str(item):
                    if tail_idx == 0:
                        if item not in passives:
                            passives.append(item)
                    else:
                        disorders.append(item)
                try:
                    r.u32()
                except Exception:
                    break

            self.passive_abilities = passives
            self.disorders = disorders

            # ── Equipment inventory (embedded after disorder data) ────────────
            # Format: u32 count, then items identical to inventory_storage
            # but WITHOUT a leading version u32.
            # Slots include all equipped items (weapons, armour, face, parasites…).
            # "None" placeholders are filtered out by _valid_str.
            self.equipment: list[str] = []
            try:
                eq_count = r.u32()
                if 1 <= eq_count <= 10:  # sanity check
                    for eq_i in range(eq_count):
                        r.skip(1)       # flag byte (always 1)
                        eq_name = r.str() or ""
                        r.str()         # subname (discard)
                        r.i32()         # charges
                        r.u32()         # field1
                        r.u32()         # field2
                        r.u32()         # seqId
                        r.u8()          # tailByte
                        r.u8()          # sep_flag
                        if eq_i < eq_count - 1:
                            r.u32()     # version separator between items
                        if eq_name and _valid_str(eq_name):
                            self.equipment.append(eq_name)
                else:
                    self.equipment = []
            except Exception:
                self.equipment = []

        else:
            # Fallback: old heuristic scan for any uppercase-starting ASCII string
            found = -1
            for i in range(curr, min(curr + 500, len(raw) - 9)):
                length = struct.unpack_from('<I', raw, i)[0]
                if (0 < length < 64
                        and struct.unpack_from('<I', raw, i + 4)[0] == 0
                        and 65 <= raw[i + 8] <= 90):
                    found = i
                    break
            if found != -1:
                r.seek(found)

            self.abilities = [a for a in [r.str() for _ in range(6)] if _valid_str(a)]
            self.equipment = [s for s in [r.str() for _ in range(4)] if _valid_str(s)]

            self.passive_abilities = []
            self.disorders = []
            first = r.str()
            if _valid_str(first):
                self.passive_abilities.append(first)
            for _ in range(13):
                if r.remaining() < 12:
                    break
                flag = r.u32()
                if flag == 0:
                    break
                p = r.str()
                if _valid_str(p):
                    self.passive_abilities.append(p)

        self.mutations = visual_display_names
        self.mutation_chip_items = [(text, tip) for text, tip, is_def in visual_items if not is_def]
        self.defects = defect_display_names
        self.defect_chip_items = [(text, tip) for text, tip, is_def in visual_items if is_def]
        # Extract age from creation_day stored near the end of the blob (around blob_len - 103).
        # Search a small window around the typical offset to handle varying blob structures.
        # _pos_creation_day is stored so strip_genealogy can patch it directly without a
        # fragile re-search that may fail when the blob comes from a save with a higher day.
        self._pos_creation_day: int | None = None
        _OFFSETS = [103, 102, 104, 101, 105, 100, 106, 107, 108, 109, 110]
        try:
            # Pass 1 (strict): creation_day must be in [0, current_day] with age in [0, 100]
            if current_day is not None:
                for offset_from_end in _OFFSETS:
                    pos = len(raw) - offset_from_end
                    if pos + 4 > len(raw) or pos < 0:
                        continue
                    creation_day = struct.unpack_from('<I', raw, pos)[0]
                    if 0 <= creation_day <= current_day:
                        age = current_day - creation_day
                        if 0 <= age <= 100:
                            self.age = age
                            self._pos_creation_day = pos
                            break

            # Pass 2 (relaxed): any plausible day value in [0, 200000]; used when the blob
            # comes from a save whose current_day exceeds ours (e.g., a received gift cat).
            if self._pos_creation_day is None:
                for offset_from_end in _OFFSETS:
                    pos = len(raw) - offset_from_end
                    if pos + 4 > len(raw) or pos < 0:
                        continue
                    val = struct.unpack_from('<I', raw, pos)[0]
                    if 0 <= val <= 200_000:
                        self._pos_creation_day = pos
                        # Don't set self.age here — we don't know the true current_day
                        break
        except Exception:
            pass

        self.parsed_age = self.age
        self.sexuality: str = "straight"  # bi / gay / straight — defaults to straight

        # Legacy token fallback is already handled above when sex_code is unavailable.

    def parse(self, path):
        pass

    # ── Genealogy strip ──────────────────────────────────────────────────────

    def strip_genealogy(self, current_day: int) -> None:
        """Zero-out all genealogy-related fields in the raw blob and reset
        in-memory relationship / lineage attributes.

        Should be called just before ``to_blob()`` when exporting a cat as a
        gift, so the recipient receives a clean cat with no family ties.

        Fields patched in ``_raw``:
          - ``_parent_uid_a`` / ``_parent_uid_b`` → u64 0
          - lover / hater db_keys (u32 @ anchor+48, anchor+72) → 0
          - inbredness (f64 @ anchor+40) → 0.0
          - creation_day (near blob end) → ``current_day - 2``  (age = 2)

        In-memory fields reset:
          ``parent_a``, ``parent_b``, ``lovers``, ``haters``, ``children``,
          ``generation``, ``_parent_uid_a``, ``_parent_uid_b``,
          ``_lover_uids``, ``_hater_uids``, ``inbredness``, ``age``.
        """
        buf    = bytearray(self._raw)
        anchor = self._personality_anchor

        # ── Reset parent UIDs (u64 each) ─────────────────────────────────────
        # 4294967297 (0x1_0000_0001) is the game's "no parent" sentinel for _parent_uid_a.
        if anchor + 16 <= len(buf):
            struct.pack_into('<Q', buf, anchor,     4294967297)  # _parent_uid_a — game sentinel
            struct.pack_into('<Q', buf, anchor + 8, 0)          # _parent_uid_b — zero

        # ── Zero lover / hater db_keys (u32 each) ───────────────────────────
        if anchor + 52 <= len(buf):
            struct.pack_into('<I', buf, anchor + 48, 0)  # lover
        if anchor + 76 <= len(buf):
            struct.pack_into('<I', buf, anchor + 72, 0)  # hater

        # ── Reset inbredness to 0.0 (f64) ───────────────────────────────────
        if anchor + 48 <= len(buf):
            struct.pack_into('<d', buf, anchor + 40, 0.0)

        # ── Patch creation_day so age == 2 ──────────────────────────────────
        # Use the position stored during parsing; fall back to a relaxed scan only
        # if the object was constructed without a known current_day (e.g., legacy paths).
        target_creation = max(0, current_day - 2)
        pos_cd = getattr(self, '_pos_creation_day', None)
        if pos_cd is None:
            # Relaxed fallback: find first plausible u32 in [0, 200000] near blob end
            for offset_from_end in [103, 102, 104, 101, 105, 100, 106, 107, 108, 109, 110]:
                pos = len(buf) - offset_from_end
                if pos < 0 or pos + 4 > len(buf):
                    continue
                val = struct.unpack_from('<I', buf, pos)[0]
                if 0 <= val <= 200_000:
                    pos_cd = pos
                    break
        if pos_cd is not None and pos_cd + 4 <= len(buf):
            struct.pack_into('<I', buf, pos_cd, target_creation)
            self._pos_creation_day = pos_cd  # keep in sync

        self._raw = bytes(buf)

        # ── Reset in-memory relationship / lineage fields ────────────────────
        self._parent_uid_a = 0  # game's "no parent" sentinel
        self._parent_uid_b = 0
        self._lover_uids   = []
        self._hater_uids   = []
        self.parent_a      = None
        self.parent_b      = None
        self.lovers        = []
        self.haters        = []
        self.children      = []
        self.generation    = 0
        self.inbredness    = 0.0
        self.age           = 2

    # ── Age reset ────────────────────────────────────────────────────────────

    def reset_age(self, current_day: int) -> None:
        """Patch *creation_day* in the raw blob so that ``age == 2``.

        Only the creation_day field is modified — no genealogy fields are
        touched.  Uses the same logic as ``strip_genealogy``.
        Call ``to_blob()`` + ``save_cat()`` afterwards to persist.
        """
        target_creation = max(0, current_day - 2)
        buf = bytearray(self._raw)
        pos_cd = getattr(self, '_pos_creation_day', None)
        if pos_cd is None:
            # Relaxed fallback: same scan as strip_genealogy
            for offset_from_end in [103, 102, 104, 101, 105, 100, 106, 107, 108, 109, 110]:
                pos = len(buf) - offset_from_end
                if pos < 0 or pos + 4 > len(buf):
                    continue
                val = struct.unpack_from('<I', buf, pos)[0]
                if 0 <= val <= 200_000:
                    pos_cd = pos
                    break
        if pos_cd is not None and pos_cd + 4 <= len(buf):
            struct.pack_into('<I', buf, pos_cd, target_creation)
            self._pos_creation_day = pos_cd
            self._raw = bytes(buf)
        self.age = 2

    # ── Disorder removal ─────────────────────────────────────────────────────

    def remove_disorder_from_blob(self, disorder_name: str) -> bool:
        """Remove *disorder_name* from the raw blob by locating its disorder tail slot.

        Mirrors the JS ``patchU64TierEntry(blob, recordOffset, byteLength, 'None', 1)``:
        the matched slot is replaced with ``[u64:4]["None"][u32:1]`` — the same
        placeholder the game itself writes for empty ability/disorder slots — so
        the game renders nothing for that entry rather than showing a nameless passive.

        The DefaultMove scan starts from ``_pos_stat_sec + 28`` (same origin as
        ``__init__``) to avoid false positives inside the T-array / stat region.

        Returns True if the disorder slot was found and patched, False otherwise.
        """
        raw = self._raw

        # ── Re-locate DefaultMove run_start (start AFTER stat arrays) ────────
        scan_start = self._pos_stat_sec + 7 * 4   # same origin as __init__
        run_start = -1
        for i in range(scan_start, len(raw) - 19):
            lo = struct.unpack_from('<I', raw, i)[0]
            hi = struct.unpack_from('<I', raw, i + 4)[0]
            if hi != 0 or not (1 <= lo <= 96):
                continue
            try:
                cand = raw[i + 8: i + 8 + lo].decode('ascii')
                if cand == 'DefaultMove':
                    run_start = i
                    break
            except Exception:
                continue

        if run_start == -1:
            return False

        # ── Skip the run ─────────────────────────────────────────────────────
        r = BinaryReader(raw)
        r.seek(run_start)
        for _ in range(32):
            saved = r.pos
            item = r.str()
            if item is None or not _IDENT_RE.match(item):
                r.seek(saved)
                break

        # Skip passive1 tier (u32 immediately after the run)
        try:
            r.u32()
        except Exception:
            return False

        # ── Collect byte ranges for the 3 tail entries ───────────────────────
        # Each entry: [u64 str prefix + content][u32 tier]
        # tail_idx 0 = Passive2, tail_idx 1 = Disorder1, tail_idx 2 = Disorder2
        # We record (str_start, str_end, tier_end, value) for each.
        tail_slots: list[tuple[int, int, int, str | None]] = []
        for _ in range(3):
            str_start = r.pos
            try:
                item = r.str()
            except Exception:
                break
            str_end = r.pos
            try:
                r.u32()
            except Exception:
                tail_slots.append((str_start, str_end, str_end, item))
                break
            tier_end = r.pos   # str_end + 4
            tail_slots.append((str_start, str_end, tier_end, item))

        # ── Patch the first matching disorder slot (tail_idx 1 or 2) ─────────
        # JS reference: patchU64TierEntry(blob, entry.offset, entry.byteLength, 'None', 1)
        #   oldTotal  = 8 + byteLength + 4
        #   newRecord = [u64:4]["None"][u32:1]  =  16 bytes
        #   net shift = 16 - oldTotal = 4 - byteLength
        FILLER = struct.pack('<Q', 4) + b'None' + struct.pack('<I', 1)   # 16 bytes

        for tail_idx, (str_start, str_end, tier_end, item) in enumerate(tail_slots):
            if tail_idx == 0:
                continue   # Passive2 slot — do not touch
            if item != disorder_name:
                continue

            content_len = (str_end - str_start) - 8   # bytes of the ASCII content
            # old entry = 8 (prefix) + content_len + 4 (tier) bytes
            # new entry = 16 bytes  →  blob shrinks by (content_len - 4)
            net_shift = content_len - 4   # positive ⇒ blob shrinks

            buf = bytearray(raw)
            buf = buf[:str_start] + bytearray(FILLER) + buf[tier_end:]
            self._raw = bytes(buf)

            # Adjust the stored creation_day absolute offset
            if net_shift != 0 and self._pos_creation_day is not None and self._pos_creation_day > str_start:
                self._pos_creation_day -= net_shift

            # Update in-memory disorder list
            try:
                self.disorders.remove(disorder_name)
            except ValueError:
                pass

            return True

        return False

    # ── Rename ───────────────────────────────────────────────────────────────

    def rename_in_blob(self, new_name: str) -> None:
        """Patch the cat name inside ``_raw`` and shift all stored byte offsets.

        After calling this method, ``self.name`` is updated and ``to_blob()``
        will produce a blob containing the new name.  All subsequent parseable
        fields (stat positions, personality anchor …) remain valid.
        """
        NAME_OFFSET = 12  # breed_id (u32 4 B) + uid (u64 8 B) = 12
        old_char_count: int = struct.unpack_from('<Q', self._raw, NAME_OFFSET)[0]
        old_name_bytes = old_char_count * 2

        new_encoded = new_name.encode('utf-16-le')
        new_char_count = len(new_name)   # char count, not byte count

        # Reconstruct raw bytes: [before name] + [new u64 char count] + [new chars] + [rest]
        before = self._raw[:NAME_OFFSET]
        new_header = struct.pack('<Q', new_char_count)
        after  = self._raw[NAME_OFFSET + 8 + old_name_bytes:]
        self._raw = before + new_header + new_encoded + after

        # Propagate byte shift to all position fields that follow the name
        shift = len(new_encoded) - old_name_bytes
        if shift:
            self._personality_anchor += shift
            self._pos_stat_base      += shift
            self._pos_stat_mod       += shift
            self._pos_stat_sec       += shift

        self.name = new_name

    # ── Serialization ────────────────────────────────────────────────────────

    def to_raw(self) -> bytes:
        """Return the decompressed cat blob with patchable numeric fields written back.

        Safe to modify before calling to_raw():
            stat_base  — list[int]   7 × u32
            stat_mod   — list[int]   7 × i32
            stat_sec   — list[int]   7 × i32
            libido     — float|None  f64 at personality_anchor + 32
            inbredness — float|None  f64 at personality_anchor + 40
            aggression — float|None  f64 at personality_anchor + 64

        String fields (name, collar, name_tag) are fixed-length in the blob;
        changing them would shift every subsequent byte offset and is not supported.
        """
        buf = bytearray(self._raw)
        anchor = self._personality_anchor

        # Patch stat arrays
        pos = self._pos_stat_base
        for v in self.stat_base:
            struct.pack_into('<I', buf, pos, max(0, int(v)))
            pos += 4

        pos = self._pos_stat_mod
        for v in self.stat_mod:
            struct.pack_into('<i', buf, pos, int(v))
            pos += 4

        pos = self._pos_stat_sec
        for v in self.stat_sec:
            struct.pack_into('<i', buf, pos, int(v))
            pos += 4

        # Patch personality floats (embedded in the 64-byte reserved region)
        if self.libido is not None and anchor + 40 <= len(buf):
            struct.pack_into('<d', buf, anchor + 32, float(self.libido))
        if self.inbredness is not None and anchor + 48 <= len(buf):
            struct.pack_into('<d', buf, anchor + 40, float(self.inbredness))
        if self.aggression is not None and anchor + 72 <= len(buf):
            struct.pack_into('<d', buf, anchor + 64, float(self.aggression))

        return bytes(buf)

    def to_blob(self) -> bytes:
        """Return a saveable LZ4-compressed blob for the 'cats' SQLite table.

        Format: [u32 LE uncompressed_size] + [LZ4 block-compressed payload]

        Usage:
            blob = cat.to_blob()
            conn.execute("UPDATE cats SET data=? WHERE key=?", (blob, cat.db_key))
        """
        raw = self.to_raw()
        compressed = lz4.block.compress(raw, store_size=False)
        return struct.pack('<I', len(raw)) + compressed

    @classmethod
    def verify_roundtrip(
        cls,
        blob: bytes,
        cat_key: int,
        house_info: dict | None = None,
        adventure_keys: set | None = None,
        current_day=None,
    ) -> tuple[bool, list[str]]:
        """Parse *blob* → Cat → to_blob() → re-parse → compare all fields.

        Returns ``(ok, mismatches)`` where *ok* is True when the round-trip
        is fully lossless (raw bytes identical, every parsed field equal).

        Example::

            ok, issues = Cat.verify_roundtrip(blob, cat_key)
            if not ok:
                for line in issues:
                    print("  MISMATCH:", line)
        """
        if house_info is None:
            house_info = {}
        if adventure_keys is None:
            adventure_keys = set()

        cat1 = cls(blob, cat_key, house_info, adventure_keys, current_day)
        new_blob = cat1.to_blob()
        cat2 = cls(new_blob, cat_key, house_info, adventure_keys, current_day)

        mismatches: list[str] = []

        def check(name: str, v1, v2, tol: float | None = None) -> None:
            if tol is not None:
                if v1 is None and v2 is None:
                    return
                if v1 is None or v2 is None or abs(v1 - v2) > tol:
                    mismatches.append(f"{name}: {v1!r} → {v2!r}")
            elif v1 != v2:
                mismatches.append(f"{name}: {v1!r} → {v2!r}")

        check("breed_id",            cat1.breed_id,            cat2.breed_id)
        check("unique_id",           cat1._uid_int,            cat2._uid_int)
        check("name",                cat1.name,                cat2.name)
        check("name_tag",            cat1.name_tag,            cat2.name_tag)
        check("collar",              cat1.collar,              cat2.collar)
        check("_parent_uid_a",       cat1._parent_uid_a,       cat2._parent_uid_a)
        check("_parent_uid_b",       cat1._parent_uid_b,       cat2._parent_uid_b)
        check("T[72]",               cat1._T,                  cat2._T)
        check("gender_token_fields", cat1.gender_token_fields, cat2.gender_token_fields)
        check("gender_token",        cat1.gender_token,        cat2.gender_token)
        check("stat_base",           cat1.stat_base,           cat2.stat_base)
        check("stat_mod",            cat1.stat_mod,            cat2.stat_mod)
        check("stat_sec",            cat1.stat_sec,            cat2.stat_sec)
        check("libido",              cat1.libido,              cat2.libido,      tol=1e-12)
        check("inbredness",          cat1.inbredness,          cat2.inbredness,  tol=1e-12)
        check("aggression",          cat1.aggression,          cat2.aggression,  tol=1e-12)
        check("abilities",           cat1.abilities,           cat2.abilities)
        check("passive_abilities",   cat1.passive_abilities,   cat2.passive_abilities)
        check("disorders",           cat1.disorders,           cat2.disorders)
        check("mutations",           cat1.mutations,           cat2.mutations)
        check("defects",             cat1.defects,             cat2.defects)

        # Strictest test: raw decompressed bytes must be bit-for-bit identical
        raw1, raw2 = cat1._raw, cat2._raw
        if raw1 != raw2:
            diff_pos = [i for i, (a, b) in enumerate(zip(raw1, raw2)) if a != b]
            length_note = (
                f", length {len(raw1)} vs {len(raw2)}" if len(raw1) != len(raw2) else ""
            )
            mismatches.append(
                f"raw bytes: {len(diff_pos)} byte(s) differ"
                f" (first 10 offsets: {diff_pos[:10]}){length_note}"
            )

        return len(mismatches) == 0, mismatches
