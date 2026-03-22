from catalogs.visual_mutation_catalog import load_visual_mutation_names

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


_VISUAL_MUT_DATA = {}
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