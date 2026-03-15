import re


def format_item_name(s: str) -> str:
    s = s.replace(" ", "_")

    parts = s.split("_")
    result = []

    for p in parts:
        if p.isupper() and p.endswith("DEVICE") and len(p) > 6:
            base = p[:-6].capitalize()
            result.append(base)
            result.append("Device")
        else:
            result.append(p.capitalize() if not p.isupper() else p)

    return "_".join(result)