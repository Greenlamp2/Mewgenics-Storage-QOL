import json
import os
import re
import struct
import sys
from pathlib import Path

from catalogs.visual_mutation_catalog import load_visual_mutation_names


_STAT_LABELS = {
    "str": "STR",
    "con": "CON",
    "int": "INT",
    "dex": "DEX",
    "spd": "SPD",
    "lck": "LCK",
    "cha": "CHA",
    "shield": "Shield",
    "divine_shield": "Holy Shield",
}

_VISUAL_MUTATION_FIELDS = [
    ("fur", 0, "fur", "texture", "fur", "Fur"),
    ("body", 3, "body", "body", "body", "Body"),
    ("head", 8, "head", "head", "head", "Head"),
    ("tail", 13, "tail", "tail", "tail", "Tail"),
    ("leg_L", 18, "legs", "legs", "legs", "Left Leg"),
    ("leg_R", 23, "legs", "legs", "legs", "Right Leg"),
    ("arm_L", 28, "arms", "legs", "legs", "Left Arm"),
    ("arm_R", 33, "arms", "legs", "legs", "Right Arm"),
    ("eye_L", 38, "eyes", "eyes", "eyes", "Left Eye"),
    ("eye_R", 43, "eyes", "eyes", "eyes", "Right Eye"),
    ("eyebrow_L", 48, "eyebrows", "eyebrows", "eyebrows", "Left Eyebrow"),
    ("eyebrow_R", 53, "eyebrows", "eyebrows", "eyebrows", "Right Eyebrow"),
    ("ear_L", 58, "ears", "ears", "ears", "Left Ear"),
    ("ear_R", 63, "ears", "ears", "ears", "Right Ear"),
    ("mouth", 68, "mouth", "mouth", "mouth", "Mouth"),
]

_VISUAL_MUTATION_PART_LABELS = {
    "fur": "Fur",
    "body": "Body",
    "head": "Head",
    "tail": "Tail",
    "legs": "Leg",
    "arms": "Arm",
    "eyes": "Eye",
    "eyebrows": "Eyebrow",
    "ears": "Ear",
    "mouth": "Mouth",
}

def _bundle_dir() -> str:
    """Return the directory containing bundled app resources."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _app_dir() -> str:
    """Return the directory containing the running script or built executable."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _steam_library_paths() -> list[str]:
    candidates = [
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Steam",
            "steamapps",
            "libraryfolders.vdf",
        ),
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Steam",
            "steamapps",
            "libraryfolders.vdf",
        ),
    ]
    libraries: list[str] = []
    for vdf_path in candidates:
        if not os.path.exists(vdf_path):
            continue
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                path = match.group(1).replace("\\\\", "\\")
                if path not in libraries:
                    libraries.append(path)
        except Exception:
            continue
    return libraries

APPDATA_CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", str(Path.home())),
    "MewgenicsBreedingManager",
)
APP_CONFIG_PATH = os.path.join(APPDATA_CONFIG_DIR, "settings.json")

def _load_app_config() -> dict:
    if not os.path.exists(APP_CONFIG_PATH):
        return {}
    try:
        with open(APP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _saved_gpak_path() -> str:
    data = _load_app_config()
    value = data.get("gpak_path", "")
    return value.strip() if isinstance(value, str) else ""

def _candidate_gpak_paths() -> list[str]:
    candidates: list[str] = []

    env_path = os.environ.get("MEWGENICS_GPAK_PATH", "").strip()
    if env_path:
        candidates.append(env_path)

    direct_paths = [
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Steam", "steamapps", "common", "Mewgenics", "resources.gpak",
        ),
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Steam", "steamapps", "common", "Mewgenics", "resources.gpak",
        ),
        r"D:\Games\Mewgenics\resources.gpak",
        os.path.join(os.getcwd(), "resources.gpak"),
        os.path.join(_app_dir(), "resources.gpak"),
        os.path.join(_bundle_dir(), "resources.gpak"),
        "/mnt/c/Program Files (x86)/Steam/steamapps/common/Mewgenics/resources.gpak",
        "/mnt/c/Program Files/Steam/steamapps/common/Mewgenics/resources.gpak",
    ]
    candidates.extend(direct_paths)

    for library in _steam_library_paths():
        candidates.append(os.path.join(library, "steamapps", "common", "Mewgenics", "resources.gpak"))

    saved_path = _saved_gpak_path()
    if saved_path:
        candidates.append(saved_path)

    ordered: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normcase(os.path.normpath(path))
        if norm in seen:
            continue
        seen.add(norm)
        ordered.append(path)
    return ordered

def _load_gpak_text_strings(file_obj, file_offsets: dict[str, tuple[int, int]]) -> dict[str, str]:
    import csv as _csv
    import io as _io

    strings: dict[str, str] = {}
    for fname, (csv_off, csv_sz) in file_offsets.items():
        if not (fname.startswith("data/text/") and fname.endswith(".csv")):
            continue
        file_obj.seek(csv_off)
        raw_csv = file_obj.read(csv_sz).decode("utf-8-sig", errors="replace")
        for row in _csv.reader(_io.StringIO(raw_csv)):
            if len(row) >= 2 and row[0] and not row[0].startswith("//"):
                strings[row[0]] = row[1]
    return strings

def _load_ability_descriptions() -> dict[str, str]:
    """
    Build {normalized_ability_id: english_desc} by reading ability/passive GON files
    and combined.csv from the game's gpak. Returns {} if gpak is unavailable.
    """
    if not _GPAK_PATH:
        return {}
    try:
        with open(_GPAK_PATH, "rb") as f:
            count = struct.unpack("<I", f.read(4))[0]
            entries = []
            for _ in range(count):
                name_len = struct.unpack("<H", f.read(2))[0]
                name = f.read(name_len).decode("utf-8", errors="replace")
                size = struct.unpack("<I", f.read(4))[0]
                entries.append((name, size))
            dir_end = f.tell()

            file_offsets: dict[str, tuple[int, int]] = {}
            offset = dir_end
            for name, size in entries:
                file_offsets[name] = (offset, size)
                offset += size

            game_strings = _load_gpak_text_strings(f, file_offsets)

            block_re = re.compile(r'^([A-Za-z]\w*)\s*\{', re.MULTILINE)
            desc_re = re.compile(r'^\s*desc\s+"([^"]*)"', re.MULTILINE)

            def _clean(text: str) -> str:
                text = re.sub(r'\[img:[^\]]+\]', '', text)
                text = re.sub(r'\[s:[^\]]*\]|\[/s\]', '', text)
                text = re.sub(r'\[c:[^\]]*\]|\[/c\]', '', text)
                return re.sub(r'\s+', ' ', text).strip()

            result: dict[str, str] = {}
            for fname, (foff, fsz) in file_offsets.items():
                if not (
                    (fname.startswith("data/abilities/") or fname.startswith("data/passives/"))
                    and fname.endswith(".gon")
                ):
                    continue
                f.seek(foff)
                content = f.read(fsz).decode("utf-8", errors="replace")
                for bm in block_re.finditer(content):
                    ability_id = bm.group(1)
                    block_start = bm.end()
                    depth, idx = 1, block_start
                    while idx < len(content) and depth > 0:
                        if content[idx] == '{':
                            depth += 1
                        elif content[idx] == '}':
                            depth -= 1
                        idx += 1
                    block = content[block_start:idx - 1]
                    dm = desc_re.search(block)
                    if not dm:
                        continue
                    desc_val = dm.group(1)
                    desc_val = _resolve_game_string(desc_val, game_strings)
                    if not desc_val or desc_val == "nothing":
                        continue
                    result[ability_id.lower()] = _clean(desc_val)
        return result
    except Exception:
        return {}

def _resolve_game_string(value: str, game_strings: dict[str, str]) -> str:
    resolved = value
    seen: set[str] = set()
    while resolved in game_strings and resolved not in seen:
        seen.add(resolved)
        nxt = game_strings[resolved].strip()
        if not nxt:
            break
        resolved = nxt
    return resolved

def _parse_mutation_gon(content: str, game_strings: dict[str, str], category: str) -> dict[int, tuple[str, str]]:
    """Parse a mutation GON file into {slot_id: (display_name, stat_desc)}.

    Covers normal mutations (300-699), birth defects (700-706, and the
    special -2 "completely missing part" defect stored as 0xFFFFFFFE in
    the T table), and special/rare mutations (750+).
    IDs < 300 are base appearance variants handled separately.
    """
    result: dict[int, tuple[str, str]] = {}
    csv_prefix = f"MUTATION_{category.upper()}_"

    def _extract_block(start_pos: int) -> tuple[str, int]:
        """Extract the brace-delimited block starting at start_pos (after '{')."""
        depth, end = 1, start_pos
        while end < len(content) and depth > 0:
            if content[end] == '{':
                depth += 1
            elif content[end] == '}':
                depth -= 1
            end += 1
        return content[start_pos:end - 1], end

    def _block_to_entry(slot_id: int, block: str):
        """Parse a single mutation block into (display_name, stat_desc)."""
        name_match = re.search(r'//\s*(.+)', block)
        raw_name = name_match.group(1).strip().title() if name_match else f"Mutation {slot_id}"
        # Trim parenthetical dev comments, e.g., "No Eyes (Frame 703, ...)" → "No Eyes"
        raw_name = re.sub(r'\s*\(.*', '', raw_name).strip() or raw_name
        csv_key = f"{csv_prefix}{slot_id}_DESC"
        if csv_key in game_strings:
            stat_desc = _resolve_game_string(game_strings[csv_key], game_strings).strip().rstrip(".")
        else:
            header = block.split('{')[0]
            stats: list[str] = []
            for key, label in _STAT_LABELS.items():
                stat_match = re.search(rf'(?<!\w){re.escape(key)}\s+(-?\d+)', header)
                if stat_match:
                    value = int(stat_match.group(1))
                    stats.append(f"{'+' if value > 0 else ''}{value} {label}")
            stat_desc = ", ".join(stats)
        result[slot_id] = (raw_name, stat_desc)

    # ── Main numeric IDs (300+) ──────────────────────────────────────────
    # IDs < 300 are base appearance variants, not mutations — skip them.
    idx = 0
    while idx < len(content):
        match = re.search(r'(?<!\w)(\d{3,})\s*\{', content[idx:])
        if not match:
            break
        slot_id = int(match.group(1))
        block, idx = _extract_block(idx + match.end())
        if slot_id < 300:
            continue
        _block_to_entry(slot_id, block)

    # ── Special -2 entry ("completely missing part" birth defect) ────────
    # The GON files use `-2 {` for body parts that are entirely absent.
    # In the save's visual-mutation T table this is stored as the u32
    # value 0xFFFFFFFE (unsigned representation of -2).
    m2_match = re.search(r'(?<!\w)-2\s*\{', content)
    if m2_match:
        block, _ = _extract_block(m2_match.end())
        # Try the game-string key "MUTATION_EYES_M2_DESC" etc.
        csv_key_m2 = f"{csv_prefix}M2_DESC"
        if csv_key_m2 in game_strings:
            name_match = re.search(r'//\s*(.+)', block)
            raw_name = name_match.group(1).strip().title() if name_match else "Missing Part"
            # Trim parenthetical dev comments from the name
            raw_name = re.sub(r'\s*\(.*', '', raw_name).strip() or raw_name
            stat_desc = _resolve_game_string(game_strings[csv_key_m2], game_strings).strip().rstrip(".")
            result[0xFFFFFFFE] = (raw_name, stat_desc)
        else:
            _block_to_entry(0xFFFFFFFE, block)

    return result


def _load_visual_mut_data() -> dict[str, dict[int, tuple[str, str]]]:
    """Load {gon_category: {slot_id: (name, stat_desc)}} from resources.gpak."""
    if not _GPAK_PATH:
        return {}
    try:
        with open(_GPAK_PATH, "rb") as f:
            count = struct.unpack("<I", f.read(4))[0]
            entries = []
            for _ in range(count):
                name_len = struct.unpack("<H", f.read(2))[0]
                name = f.read(name_len).decode("utf-8", errors="replace")
                size = struct.unpack("<I", f.read(4))[0]
                entries.append((name, size))
            dir_end = f.tell()

            file_offsets: dict[str, tuple[int, int]] = {}
            offset = dir_end
            for name, size in entries:
                file_offsets[name] = (offset, size)
                offset += size

            game_strings = _load_gpak_text_strings(f, file_offsets)

            result: dict[str, dict[int, tuple[str, str]]] = {}
            for fname, (foff, fsz) in file_offsets.items():
                if not (fname.startswith("data/mutations/") and fname.endswith(".gon")):
                    continue
                category = fname.split("/")[-1].replace(".gon", "")
                f.seek(foff)
                content = f.read(fsz).decode("utf-8", errors="replace")
                result[category] = _parse_mutation_gon(content, game_strings, category)
        return result
    except Exception:
        return {}

def _reload_game_data():
    global _GPAK_SEARCH_PATHS, _GPAK_PATH, _ABILITY_DESC, _VISUAL_MUT_DATA
    _GPAK_SEARCH_PATHS = _candidate_gpak_paths()
    _GPAK_PATH = next((p for p in _GPAK_SEARCH_PATHS if os.path.exists(p)), None)
    _ABILITY_DESC = _load_ability_descriptions()
    _VISUAL_MUT_DATA = _load_visual_mut_data()


_VISUAL_MUT_DATA = {}
_reload_game_data()
def _read_visual_mutation_entries(table: list[int]) -> list[dict[str, object]]:
    fallback_names = load_visual_mutation_names()
    entries: list[dict[str, object]] = []
    for slot_key, table_index, group_key, gpak_category, fallback_part, slot_label in _VISUAL_MUTATION_FIELDS:
        mutation_id = table[table_index] if table_index < len(table) else 0
        if mutation_id in (0, 0xFFFF_FFFF):
            continue

        # IDs < 300 are base appearance variants (normal cat looks), not mutations.
        # Actual mutations start at 300; birth defects are in the 700-706 range.
        # 0xFFFFFFFE (-2 as u32) = "completely missing part" birth defect.
        display_name = ""
        detail = ""
        gpak_info = _VISUAL_MUT_DATA.get(gpak_category, {}).get(mutation_id)
        if gpak_info:
            raw_name, stat_desc = gpak_info
            if re.match(r'^Mutation \d+$', raw_name):
                display_name = f"{_VISUAL_MUTATION_PART_LABELS.get(group_key, slot_label)} Mutation"
            else:
                display_name = raw_name
            detail = stat_desc
        else:
            fallback_name = fallback_names.get((fallback_part, mutation_id))
            if fallback_name is None:
                if mutation_id < 300:
                    continue
                if mutation_id == 0xFFFF_FFFE:
                    fallback_name = f"No {_VISUAL_MUTATION_PART_LABELS.get(group_key, slot_label)}"
                else:
                    fallback_name = f"{_VISUAL_MUTATION_PART_LABELS.get(group_key, slot_label)} {mutation_id}"
            display_name = fallback_name

        is_defect = (700 <= mutation_id <= 706) or mutation_id == 0xFFFF_FFFE

        display_name = str(display_name).strip() or f"{slot_label} {mutation_id}"
        entries.append({
            "slot_key": slot_key,
            "slot_label": slot_label,
            "group_key": group_key,
            "part_label": _VISUAL_MUTATION_PART_LABELS.get(group_key, slot_label),
            "mutation_id": mutation_id,
            "name": display_name,
            "detail": str(detail).strip(),
            "is_defect": is_defect,
        })
    return entries

def _visual_mutation_chip_items(entries: list[dict[str, object]]) -> list[tuple[str, str, bool]]:
    """Return [(display_text, tooltip, is_defect), ...] from visual mutation entries."""
    grouped: dict[tuple[str, int], list[dict[str, object]]] = {}
    order: list[tuple[str, int]] = []
    for entry in entries:
        key = (str(entry["group_key"]), int(entry["mutation_id"]))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(entry)

    groups: list[dict[str, object]] = []
    for key in order:
        items = grouped[key]
        slot_labels = [str(item["slot_label"]) for item in items]
        name = str(items[0]["name"])
        mutation_id = int(items[0]["mutation_id"])
        part_label = str(items[0]["part_label"])
        detail = str(items[0]["detail"]).strip()
        is_defect = bool(items[0].get("is_defect", False))
        title_label = part_label if len(slot_labels) > 1 else str(items[0]["slot_label"])
        kind = "Birth Defect" if is_defect else "Mutation"
        id_str = "-2" if mutation_id == 0xFFFF_FFFE else str(mutation_id)
        tooltip = f"{title_label} {kind} (ID {id_str})\n{name}"
        if detail:
            tooltip = f"{tooltip}\n{detail}"
        if len(slot_labels) > 1:
            tooltip = f"{tooltip}\nAffects: {', '.join(slot_labels)}"
        groups.append({
            "text": name,
            "tooltip": tooltip,
            "slot_labels": slot_labels,
            "is_defect": is_defect,
        })

    text_counts: dict[str, int] = {}
    for group in groups:
        text = str(group["text"])
        text_counts[text] = text_counts.get(text, 0) + 1

    chip_items: list[tuple[str, str, bool]] = []
    for group in groups:
        text = str(group["text"])
        if text_counts[text] > 1:
            text = f"{text} ({' / '.join(group['slot_labels'])})"
        chip_items.append((text, str(group["tooltip"]), bool(group["is_defect"])))
    return chip_items