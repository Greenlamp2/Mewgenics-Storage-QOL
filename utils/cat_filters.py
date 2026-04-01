"""
utils/cat_filters.py
====================
Pure filtering logic for the cat list — zero UI dependencies.

Extracted from ``ui/cat_manager.py:CatManagerWindow._filtered_cats`` so that
the rules can be unit-tested without instantiating any Qt widgets.

Public API
----------
filter_cats(cats, filter_type, *, sub_filter, gender_filter,
            sexuality_filter, tag_filter) -> list[Cat]
"""

from __future__ import annotations

from typing import Any


def filter_cats(
    cats: list,
    filter_type: str,
    *,
    sub_filter: str = "all",
    gender_filter: str = "all",
    sexuality_filter: str = "all",
    tag_filter: str = "all",
) -> list:
    """Return the subset of *cats* that matches the current filter state.

    Parameters
    ----------
    cats:
        Full list of Cat objects (or duck-typed equivalents).
    filter_type:
        One of ``"house"``, ``"adventure"``, ``"bank"``, ``"newborns"``.
    sub_filter:
        Newborns sub-filter key: ``"all"``, ``"defects"``,
        ``"lt8"``, ``"eq8"``, ``"eq9"``, ``"eq10"``.
    gender_filter:
        ``"all"``, ``"male"``, ``"female"``, ``"ditto"``.
    sexuality_filter:
        ``"all"``, ``"straight"``, ``"gay"``, ``"bi"``.
    tag_filter:
        Bank tag filter: ``"all"``, ``"__no_tags__"``, or a tag string.
    """
    if filter_type == "house":
        return [c for c in cats if c.status == "In House"]

    if filter_type == "adventure":
        return [c for c in cats if c.status == "Adventure"]

    if filter_type == "bank":
        banked = [c for c in cats if c.status == "In Bank"]
        if tag_filter == "__no_tags__":
            banked = [c for c in banked if not getattr(c, "tags", [])]
        elif tag_filter != "all":
            banked = [c for c in banked if tag_filter in getattr(c, "tags", [])]
        return banked

    if filter_type == "newborns":
        babies = [
            c for c in cats
            if getattr(c, "age", None) == 1 and c.status == "In House"
        ]

        # ── Mutation / disorder sub-filter ────────────────────────────────
        def _mut_count(c: Any) -> int:
            return len(getattr(c, "mutation_chip_items", []))

        if sub_filter == "defects":
            babies = [c for c in babies if getattr(c, "disorders", [])]
        elif sub_filter == "lt8":
            babies = [c for c in babies if _mut_count(c) < 8]
        elif sub_filter == "eq8":
            babies = [c for c in babies if _mut_count(c) == 8]
        elif sub_filter == "eq9":
            babies = [c for c in babies if _mut_count(c) == 9]
        elif sub_filter == "eq10":
            babies = [c for c in babies if _mut_count(c) == 10]
        # "all" → no mutation filter

        # ── Gender sub-filter ─────────────────────────────────────────────
        if gender_filter == "male":
            babies = [c for c in babies if c.gender == "male"]
        elif gender_filter == "female":
            babies = [c for c in babies if c.gender == "female"]
        elif gender_filter == "ditto":
            babies = [c for c in babies if c.gender == "?"]

        # ── Sexuality sub-filter ──────────────────────────────────────────
        if sexuality_filter != "all":
            babies = [
                c for c in babies
                if getattr(c, "sexuality", "straight") == sexuality_filter
            ]

        return babies

    # Fallback: return everything
    return list(cats)

