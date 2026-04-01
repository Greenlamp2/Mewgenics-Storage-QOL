"""
tests/test_newborn_filters.py
=============================
Unit tests for ``utils.cat_filters.filter_cats``.

All tests use lightweight ``_FakeCat`` stubs — no Qt, no save file, no
catalog.  Every behaviour documented in AGENTS.md is covered.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass, field
from typing import Optional

import pytest

from utils.cat_filters import filter_cats


# ---------------------------------------------------------------------------
# Minimal stub — only the attributes accessed by filter_cats
# ---------------------------------------------------------------------------

@dataclass
class _FakeCat:
    name: str = "TestCat"
    status: str = "In House"           # "In House"|"Adventure"|"In Bank"|"Gone"
    age: Optional[int] = 1
    gender: str = "male"               # "male"|"female"|"?"
    sexuality: str = "straight"
    disorders: list = field(default_factory=list)
    mutation_chip_items: list = field(default_factory=list)
    tags: list = field(default_factory=list)

    def _mutations(self, n: int) -> "_FakeCat":
        """Helper: set mutation_chip_items to n items and return self."""
        self.mutation_chip_items = [("Mut", "") for _ in range(n)]
        return self


def _baby(**kwargs) -> _FakeCat:
    """Shortcut: a 1-day-old In-House cat."""
    return _FakeCat(age=1, status="In House", **kwargs)


def _older(**kwargs) -> _FakeCat:
    """Shortcut: a 5-day-old In-House cat (not a newborn)."""
    return _FakeCat(age=5, status="In House", **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ids(cats) -> list[str]:
    return [c.name for c in cats]


# ===========================================================================
# Status filters — house / adventure / bank
# ===========================================================================

class TestStatusFilters:

    def test_house_returns_only_in_house(self):
        cats = [
            _FakeCat(name="A", status="In House", age=5),
            _FakeCat(name="B", status="Adventure", age=5),
            _FakeCat(name="C", status="In Bank", age=5),
            _FakeCat(name="D", status="Gone", age=5),
        ]
        result = filter_cats(cats, "house")
        assert _ids(result) == ["A"]

    def test_adventure_returns_only_adventure(self):
        cats = [
            _FakeCat(name="A", status="In House", age=5),
            _FakeCat(name="B", status="Adventure", age=5),
        ]
        result = filter_cats(cats, "adventure")
        assert _ids(result) == ["B"]

    def test_bank_returns_only_in_bank(self):
        cats = [
            _FakeCat(name="A", status="In House", age=5),
            _FakeCat(name="B", status="In Bank", age=5),
            _FakeCat(name="C", status="Adventure", age=5),
        ]
        result = filter_cats(cats, "bank")
        assert _ids(result) == ["B"]

    def test_empty_list_returns_empty(self):
        assert filter_cats([], "house") == []
        assert filter_cats([], "adventure") == []
        assert filter_cats([], "bank") == []
        assert filter_cats([], "newborns") == []

    def test_unknown_filter_returns_all(self):
        cats = [_FakeCat(name="A"), _FakeCat(name="B")]
        assert len(filter_cats(cats, "xyz")) == 2


# ===========================================================================
# Bank tag filter
# ===========================================================================

class TestBankTagFilter:

    def _banked(self, name, tags=None) -> _FakeCat:
        return _FakeCat(name=name, status="In Bank", age=5,
                        tags=tags or [])

    def test_tag_all_returns_all_banked(self):
        cats = [self._banked("A", ["keeper"]), self._banked("B")]
        result = filter_cats(cats, "bank", tag_filter="all")
        assert len(result) == 2

    def test_tag_no_tags_returns_untagged_only(self):
        cats = [self._banked("A", ["keeper"]), self._banked("B")]
        result = filter_cats(cats, "bank", tag_filter="__no_tags__")
        assert _ids(result) == ["B"]

    def test_tag_specific_returns_matching(self):
        cats = [
            self._banked("A", ["keeper"]),
            self._banked("B", ["sell"]),
            self._banked("C", ["keeper", "sell"]),
            self._banked("D"),
        ]
        result = filter_cats(cats, "bank", tag_filter="keeper")
        assert set(_ids(result)) == {"A", "C"}

    def test_tag_filter_does_not_include_non_banked(self):
        cats = [
            _FakeCat(name="A", status="In House", age=5, tags=["keeper"]),
            self._banked("B", ["keeper"]),
        ]
        result = filter_cats(cats, "bank", tag_filter="keeper")
        assert _ids(result) == ["B"]

    def test_no_tags_filter_excludes_cats_with_any_tag(self):
        cats = [
            self._banked("A", ["x"]),
            self._banked("B", ["y", "z"]),
            self._banked("C"),
        ]
        result = filter_cats(cats, "bank", tag_filter="__no_tags__")
        assert _ids(result) == ["C"]


# ===========================================================================
# Newborns base filter
# ===========================================================================

class TestNewbornsBase:

    def test_only_age_1_included(self):
        cats = [
            _baby(name="Baby"),
            _older(name="Older"),
        ]
        result = filter_cats(cats, "newborns")
        assert _ids(result) == ["Baby"]

    def test_gone_cats_excluded_even_if_age_1(self):
        cats = [
            _FakeCat(name="Gone", status="Gone", age=1),
            _baby(name="Alive"),
        ]
        result = filter_cats(cats, "newborns")
        assert _ids(result) == ["Alive"]

    def test_adventure_cats_excluded(self):
        cats = [
            _FakeCat(name="Adv", status="Adventure", age=1),
            _baby(name="Home"),
        ]
        result = filter_cats(cats, "newborns")
        assert _ids(result) == ["Home"]

    def test_banked_cats_excluded(self):
        cats = [
            _FakeCat(name="Banked", status="In Bank", age=1),
            _baby(name="Home"),
        ]
        result = filter_cats(cats, "newborns")
        assert _ids(result) == ["Home"]

    def test_none_age_excluded(self):
        cats = [
            _FakeCat(name="NoAge", status="In House", age=None),
            _baby(name="Baby"),
        ]
        result = filter_cats(cats, "newborns")
        assert _ids(result) == ["Baby"]


# ===========================================================================
# Newborns sub-filter (mutation / disorder)
# ===========================================================================

class TestNewbornsSubFilter:

    def _make_pool(self):
        """Return a varied pool of 1-day-old cats for sub-filter tests."""
        return [
            _baby(name="NoMut").   _mutations(0),
            _baby(name="Mut5").    _mutations(5),
            _baby(name="Mut7").    _mutations(7),
            _baby(name="Mut8a").   _mutations(8),
            _baby(name="Mut8b").   _mutations(8),
            _baby(name="Mut9").    _mutations(9),
            _baby(name="Mut10").   _mutations(10),
            _baby(name="Disorder", disorders=["BloodFrenzy"]),
        ]

    def test_sub_filter_all_returns_everything(self):
        pool = self._make_pool()
        result = filter_cats(pool, "newborns", sub_filter="all")
        assert len(result) == len(pool)

    def test_sub_filter_defects_returns_only_disordered(self):
        pool = self._make_pool()
        result = filter_cats(pool, "newborns", sub_filter="defects")
        assert _ids(result) == ["Disorder"]

    def test_sub_filter_defects_empty_when_none_have_disorders(self):
        cats = [_baby(name="A"), _baby(name="B")]
        result = filter_cats(cats, "newborns", sub_filter="defects")
        assert result == []

    def test_sub_filter_lt8(self):
        pool = self._make_pool()
        result = filter_cats(pool, "newborns", sub_filter="lt8")
        names = _ids(result)
        assert "NoMut"    in names
        assert "Mut5"     in names
        assert "Mut7"     in names
        assert "Disorder" in names   # 0 mutations < 8
        assert "Mut8a"    not in names
        assert "Mut9"     not in names
        assert "Mut10"    not in names

    def test_sub_filter_eq8(self):
        pool = self._make_pool()
        result = filter_cats(pool, "newborns", sub_filter="eq8")
        assert set(_ids(result)) == {"Mut8a", "Mut8b"}

    def test_sub_filter_eq9(self):
        pool = self._make_pool()
        result = filter_cats(pool, "newborns", sub_filter="eq9")
        assert _ids(result) == ["Mut9"]

    def test_sub_filter_eq10(self):
        pool = self._make_pool()
        result = filter_cats(pool, "newborns", sub_filter="eq10")
        assert _ids(result) == ["Mut10"]

    def test_sub_filter_eq10_empty(self):
        cats = [_baby(name="A")._mutations(9)]
        result = filter_cats(cats, "newborns", sub_filter="eq10")
        assert result == []

    def test_multiple_disorders_still_passes_defects(self):
        cat = _baby(name="MultiDis", disorders=["BloodFrenzy", "Paranoia"])
        result = filter_cats([cat], "newborns", sub_filter="defects")
        assert len(result) == 1


# ===========================================================================
# Newborns gender sub-filter
# ===========================================================================

class TestNewbornsGenderFilter:

    def _pool(self):
        return [
            _baby(name="M1", gender="male"),
            _baby(name="M2", gender="male"),
            _baby(name="F1", gender="female"),
            _baby(name="D1", gender="?"),
        ]

    def test_gender_all_returns_all(self):
        pool = self._pool()
        result = filter_cats(pool, "newborns", gender_filter="all")
        assert len(result) == 4

    def test_gender_male(self):
        result = filter_cats(self._pool(), "newborns", gender_filter="male")
        assert set(_ids(result)) == {"M1", "M2"}

    def test_gender_female(self):
        result = filter_cats(self._pool(), "newborns", gender_filter="female")
        assert _ids(result) == ["F1"]

    def test_gender_ditto_matches_question_mark(self):
        result = filter_cats(self._pool(), "newborns", gender_filter="ditto")
        assert _ids(result) == ["D1"]

    def test_gender_male_empty_when_no_males(self):
        cats = [_baby(name="F", gender="female")]
        result = filter_cats(cats, "newborns", gender_filter="male")
        assert result == []


# ===========================================================================
# Newborns sexuality sub-filter
# ===========================================================================

class TestNewbornsSexualityFilter:

    def _pool(self):
        return [
            _baby(name="Str1", sexuality="straight"),
            _baby(name="Str2", sexuality="straight"),
            _baby(name="Gay1", sexuality="gay"),
            _baby(name="Bi1",  sexuality="bi"),
            _baby(name="Def"),   # default attribute → "straight"
        ]

    def test_sexuality_all_returns_all(self):
        pool = self._pool()
        result = filter_cats(pool, "newborns", sexuality_filter="all")
        assert len(result) == len(pool)

    def test_sexuality_straight(self):
        result = filter_cats(self._pool(), "newborns", sexuality_filter="straight")
        names = _ids(result)
        assert "Str1" in names
        assert "Str2" in names
        assert "Def"  in names   # default is "straight"
        assert "Gay1" not in names

    def test_sexuality_gay(self):
        result = filter_cats(self._pool(), "newborns", sexuality_filter="gay")
        assert _ids(result) == ["Gay1"]

    def test_sexuality_bi(self):
        result = filter_cats(self._pool(), "newborns", sexuality_filter="bi")
        assert _ids(result) == ["Bi1"]

    def test_sexuality_missing_attribute_defaults_to_straight(self):
        """Cats without a ``sexuality`` attribute default to 'straight'."""
        class _NoSex:
            name = "NoSex"
            status = "In House"
            age = 1
            gender = "male"
            disorders = []
            mutation_chip_items = []
            tags = []
            # no 'sexuality' attribute at all

        result = filter_cats([_NoSex()], "newborns", sexuality_filter="straight")
        assert len(result) == 1

    def test_sexuality_missing_attribute_excluded_from_gay(self):
        class _NoSex:
            name = "NoSex"
            status = "In House"
            age = 1
            gender = "male"
            disorders = []
            mutation_chip_items = []
            tags = []

        result = filter_cats([_NoSex()], "newborns", sexuality_filter="gay")
        assert result == []


# ===========================================================================
# Newborns combined filters
# ===========================================================================

class TestNewbornsCombinedFilters:

    def test_gender_and_sexuality_combined(self):
        cats = [
            _baby(name="MStr", gender="male",   sexuality="straight"),
            _baby(name="MGay", gender="male",   sexuality="gay"),
            _baby(name="FStr", gender="female", sexuality="straight"),
            _baby(name="FGay", gender="female", sexuality="gay"),
        ]
        result = filter_cats(
            cats, "newborns",
            gender_filter="male",
            sexuality_filter="gay",
        )
        assert _ids(result) == ["MGay"]

    def test_sub_filter_and_gender_combined(self):
        cats = [
            _baby(name="M8",  gender="male")._mutations(8),
            _baby(name="F8",  gender="female")._mutations(8),
            _baby(name="M9",  gender="male")._mutations(9),
        ]
        result = filter_cats(
            cats, "newborns",
            sub_filter="eq8",
            gender_filter="male",
        )
        assert _ids(result) == ["M8"]

    def test_all_three_combined(self):
        cats = [
            _baby(name="Hit",  gender="female", sexuality="gay",      disorders=["X"]),
            _baby(name="Miss1",gender="male",   sexuality="gay",      disorders=["X"]),
            _baby(name="Miss2",gender="female", sexuality="straight", disorders=["X"]),
            _baby(name="Miss3",gender="female", sexuality="gay"),     # no disorders
        ]
        result = filter_cats(
            cats, "newborns",
            sub_filter="defects",
            gender_filter="female",
            sexuality_filter="gay",
        )
        assert _ids(result) == ["Hit"]

    def test_no_match_across_combined_filters_returns_empty(self):
        cats = [_baby(name="A", gender="male", sexuality="straight")]
        result = filter_cats(
            cats, "newborns",
            sub_filter="eq10",
            gender_filter="female",
        )
        assert result == []


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:

    def test_newborns_excludes_age_2(self):
        cats = [_FakeCat(name="Age2", status="In House", age=2)]
        assert filter_cats(cats, "newborns") == []

    def test_newborns_excludes_age_0(self):
        cats = [_FakeCat(name="Age0", status="In House", age=0)]
        assert filter_cats(cats, "newborns") == []

    def test_house_filter_includes_all_age_groups(self):
        cats = [
            _FakeCat(name="Baby",  status="In House", age=1),
            _FakeCat(name="Adult", status="In House", age=100),
            _FakeCat(name="Adv",   status="Adventure", age=5),
        ]
        result = filter_cats(cats, "house")
        assert set(_ids(result)) == {"Baby", "Adult"}

    def test_bank_tag_unknown_tag_returns_empty(self):
        cats = [_FakeCat(name="A", status="In Bank", age=5, tags=["keeper"])]
        result = filter_cats(cats, "bank", tag_filter="nonexistent_tag")
        assert result == []

    def test_mutation_chip_items_absent_counts_as_zero(self):
        """Cats without ``mutation_chip_items`` attribute count as 0 mutations."""
        class _NoBadge:
            name = "NoBadge"
            status = "In House"
            age = 1
            gender = "male"
            sexuality = "straight"
            disorders = []
            tags = []
            # no mutation_chip_items at all

        result = filter_cats([_NoBadge()], "newborns", sub_filter="lt8")
        assert len(result) == 1

    def test_mutation_chip_items_absent_excluded_from_eq8(self):
        class _NoBadge:
            name = "NoBadge"
            status = "In House"
            age = 1
            gender = "male"
            sexuality = "straight"
            disorders = []
            tags = []

        result = filter_cats([_NoBadge()], "newborns", sub_filter="eq8")
        assert result == []

    def test_filter_does_not_mutate_input_list(self):
        original = [_baby(name=str(i)) for i in range(5)]
        snapshot = list(original)
        filter_cats(original, "newborns", sub_filter="eq10")
        assert original == snapshot

