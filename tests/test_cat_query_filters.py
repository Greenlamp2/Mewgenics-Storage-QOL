"""
tests/test_cat_query_filters.py
================================
Comprehensive unit tests for ``utils.cat_query_filters`` — the advanced
modular filter-builder system.

All tests use lightweight ``_FakeCat`` stubs — no Qt, no save file, no
catalog.  The test suite covers:

  1. Basic filtering — single blocks, all operators.
  2. Logical combinations — AND / OR groups.
  3. Nested groups — groups inside groups, mixed AND/OR.
  4. Edge cases — empty tree, invalid operators, missing attributes.
  5. Serialisation round-trip — group_to_dict → JSON → group_from_dict.
  6. Preset system — save / load / list / delete / overwrite.
  7. Complex end-to-end example — realistic newborn breeder filter.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dataclasses import dataclass, field
from typing import Optional

from utils.cat_query_filters import (
    FilterBlock,
    FilterGroup,
    FilterType,
    Operator,
    LogicalOp,
    FilterEvaluationError,
    evaluate_filter,
    filter_cats_query,
    group_to_dict,
    group_from_dict,
    save_preset,
    load_preset,
    list_presets,
    delete_preset,
)


# ---------------------------------------------------------------------------
# Minimal _FakeCat stub
# ---------------------------------------------------------------------------

@dataclass
class _FakeCat:
    """Lightweight stub exposing every attribute accessed by the filter engine."""
    name:              str           = "TestCat"
    status:            str           = "In House"
    age:               Optional[int] = 1
    gender:            str           = "male"
    sexuality:         str           = "straight"
    room:              str           = "Living Room"
    abilities:         list          = field(default_factory=list)
    passive_abilities: list          = field(default_factory=list)
    mutations:         list          = field(default_factory=list)
    mutation_chip_items: list        = field(default_factory=list)
    defects:           list          = field(default_factory=list)
    defect_chip_items: list          = field(default_factory=list)
    disorders:         list          = field(default_factory=list)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _cat(**kwargs) -> _FakeCat:
    return _FakeCat(**kwargs)


def _with_mutations(cat: _FakeCat, names: list[str]) -> _FakeCat:
    cat.mutations = list(names)
    cat.mutation_chip_items = [(n, "") for n in names]
    return cat


def _with_defects(cat: _FakeCat, names: list[str]) -> _FakeCat:
    cat.defects = list(names)
    cat.defect_chip_items = [(n, "") for n in names]
    return cat


def _with_abilities(cat: _FakeCat, abilities: list[str]) -> _FakeCat:
    cat.abilities = list(abilities)
    return cat


def _with_passives(cat: _FakeCat, passives: list[str]) -> _FakeCat:
    cat.passive_abilities = list(passives)
    return cat


def _with_disorders(cat: _FakeCat, disorders: list[str]) -> _FakeCat:
    cat.disorders = list(disorders)
    return cat


def _block(ft: FilterType | str, op: Operator | str, value=None) -> FilterBlock:
    """Shorthand constructor for FilterBlock."""
    return FilterBlock(
        filter_type=ft if isinstance(ft, str) else ft.value,
        operator=op if isinstance(op, str) else op.value,
        value=value,
    )


def _group(*children, op: LogicalOp = LogicalOp.AND) -> FilterGroup:
    """Shorthand constructor for FilterGroup."""
    return FilterGroup(
        logical_op=op.value,
        children=list(children),
    )


def _names(cats) -> list[str]:
    return [c.name for c in cats]


# ===========================================================================
# 1. Basic filtering — list fields
# ===========================================================================

class TestListFieldFiltering:
    """Single-block filters on list-type attributes."""

    # ── abilities ─────────────────────────────────────────────────────────

    def test_abilities_contains_match(self):
        cat = _with_abilities(_cat(name="A"), ["Slash", "Fireball"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.CONTAINS, "Slash"))

    def test_abilities_contains_no_match(self):
        cat = _with_abilities(_cat(), ["Slash"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.CONTAINS, "Fireball")) == []

    def test_abilities_not_contains_match(self):
        cat = _with_abilities(_cat(), ["Slash"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.NOT_CONTAINS, "Fireball"))

    def test_abilities_not_contains_no_match(self):
        cat = _with_abilities(_cat(), ["Slash"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.NOT_CONTAINS, "Slash")) == []

    def test_abilities_any_of_match(self):
        cat = _with_abilities(_cat(), ["Slash", "Kick"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.ANY_OF, ["Kick", "Throw"]))

    def test_abilities_any_of_no_match(self):
        cat = _with_abilities(_cat(), ["Slash"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.ANY_OF, ["Throw", "Kick"])) == []

    def test_abilities_none_of_match(self):
        cat = _with_abilities(_cat(), ["Slash"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.NONE_OF, ["Fireball", "Kick"]))

    def test_abilities_none_of_no_match_when_overlap(self):
        cat = _with_abilities(_cat(), ["Slash", "Fireball"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.NONE_OF, ["Fireball"])) == []

    def test_abilities_is_empty_match(self):
        cat_empty = _cat(name="E")
        cat_full  = _with_abilities(_cat(name="F"), ["Slash"])
        result = filter_cats_query([cat_empty, cat_full], _block(FilterType.ABILITIES, Operator.IS_EMPTY))
        assert _names(result) == ["E"]

    def test_abilities_is_not_empty_match(self):
        cat_empty = _cat(name="E")
        cat_full  = _with_abilities(_cat(name="F"), ["Slash"])
        result = filter_cats_query([cat_empty, cat_full], _block(FilterType.ABILITIES, Operator.IS_NOT_EMPTY))
        assert _names(result) == ["F"]

    # ── passives ──────────────────────────────────────────────────────────

    def test_passives_contains_match(self):
        cat = _with_passives(_cat(), ["Sturdy"])
        assert filter_cats_query([cat], _block(FilterType.PASSIVES, Operator.CONTAINS, "Sturdy"))

    def test_passives_is_empty(self):
        cat = _with_passives(_cat(name="NP"), [])
        assert filter_cats_query([cat], _block(FilterType.PASSIVES, Operator.IS_EMPTY))

    def test_passives_any_of(self):
        cat = _with_passives(_cat(), ["Sturdy", "Longshot"])
        assert filter_cats_query([cat], _block(FilterType.PASSIVES, Operator.ANY_OF, ["Longshot", "Swiftfoot"]))

    def test_passives_none_of(self):
        cat = _with_passives(_cat(), ["Sturdy"])
        assert filter_cats_query([cat], _block(FilterType.PASSIVES, Operator.NONE_OF, ["Longshot"]))

    # ── mutations ─────────────────────────────────────────────────────────

    def test_mutation_contains_match(self):
        cat = _with_mutations(_cat(), ["Extra Limb", "Scales"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION, Operator.CONTAINS, "Extra Limb"))

    def test_mutation_not_contains(self):
        cat = _with_mutations(_cat(), ["Extra Limb"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION, Operator.NOT_CONTAINS, "Scales"))

    def test_mutation_is_empty(self):
        cat = _cat(name="Clean")
        assert filter_cats_query([cat], _block(FilterType.MUTATION, Operator.IS_EMPTY))

    def test_mutation_any_of(self):
        cat = _with_mutations(_cat(), ["Scales", "Claws"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION, Operator.ANY_OF, ["Claws", "Wings"]))

    def test_mutation_none_of(self):
        cat = _with_mutations(_cat(), ["Scales"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION, Operator.NONE_OF, ["Claws", "Wings"]))

    # ── defects ───────────────────────────────────────────────────────────

    def test_defects_contains_match(self):
        cat = _with_defects(_cat(), ["Brittle Bones"])
        assert filter_cats_query([cat], _block(FilterType.DEFECTS, Operator.CONTAINS, "Brittle Bones"))

    def test_defects_is_empty_match(self):
        cat = _cat(name="Healthy")
        assert filter_cats_query([cat], _block(FilterType.DEFECTS, Operator.IS_EMPTY))

    def test_defects_is_not_empty_match(self):
        cat = _with_defects(_cat(), ["Weak Heart"])
        assert filter_cats_query([cat], _block(FilterType.DEFECTS, Operator.IS_NOT_EMPTY))

    # ── disorders ─────────────────────────────────────────────────────────

    def test_disorder_contains_match(self):
        cat = _with_disorders(_cat(), ["BloodFrenzy"])
        assert filter_cats_query([cat], _block(FilterType.DISORDER, Operator.CONTAINS, "BloodFrenzy"))

    def test_disorder_none_of(self):
        cat = _with_disorders(_cat(), ["Paranoia"])
        assert filter_cats_query([cat], _block(FilterType.DISORDER, Operator.NONE_OF, ["BloodFrenzy"]))

    def test_disorder_is_empty(self):
        cat = _cat(name="Sane")
        assert filter_cats_query([cat], _block(FilterType.DISORDER, Operator.IS_EMPTY))


# ===========================================================================
# 2. Basic filtering — count fields
# ===========================================================================

class TestCountFieldFiltering:
    """Single-block filters on integer count attributes."""

    # ── mutation_count ────────────────────────────────────────────────────

    def test_mutation_count_eq_match(self):
        cat = _with_mutations(_cat(), ["A", "B", "C"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.EQ, 3))

    def test_mutation_count_eq_no_match(self):
        cat = _with_mutations(_cat(), ["A"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.EQ, 3)) == []

    def test_mutation_count_ne(self):
        cat = _with_mutations(_cat(), ["A"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.NE, 3))

    def test_mutation_count_lt_match(self):
        cat = _with_mutations(_cat(), ["A", "B"])
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.LT, 5))

    def test_mutation_count_lt_no_match_at_boundary(self):
        cat = _with_mutations(_cat(), ["x"] * 5)
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.LT, 5)) == []

    def test_mutation_count_lte_at_boundary(self):
        cats = [
            _with_mutations(_cat(name="A"), ["x"] * 4),
            _with_mutations(_cat(name="B"), ["x"] * 5),
            _with_mutations(_cat(name="C"), ["x"] * 6),
        ]
        result = filter_cats_query(cats, _block(FilterType.MUTATION_COUNT, Operator.LTE, 5))
        assert set(_names(result)) == {"A", "B"}

    def test_mutation_count_gt(self):
        cats = [
            _with_mutations(_cat(name="A"), ["x"] * 7),
            _with_mutations(_cat(name="B"), ["x"] * 9),
            _with_mutations(_cat(name="C"), ["x"] * 5),
        ]
        result = filter_cats_query(cats, _block(FilterType.MUTATION_COUNT, Operator.GT, 7))
        assert _names(result) == ["B"]

    def test_mutation_count_gte_at_boundary(self):
        cats = [
            _with_mutations(_cat(name="A"), ["x"] * 8),
            _with_mutations(_cat(name="B"), ["x"] * 7),
        ]
        result = filter_cats_query(cats, _block(FilterType.MUTATION_COUNT, Operator.GTE, 8))
        assert _names(result) == ["A"]

    # ── defects_count ─────────────────────────────────────────────────────

    def test_defects_count_eq(self):
        cat = _with_defects(_cat(), ["X", "Y"])
        assert filter_cats_query([cat], _block(FilterType.DEFECTS_COUNT, Operator.EQ, 2))

    def test_defects_count_gt(self):
        cats = [
            _with_defects(_cat(name="A"), ["X"]),
            _with_defects(_cat(name="B"), ["X", "Y", "Z"]),
        ]
        result = filter_cats_query(cats, _block(FilterType.DEFECTS_COUNT, Operator.GT, 1))
        assert _names(result) == ["B"]

    def test_defects_count_lte(self):
        cats = [
            _with_defects(_cat(name="A"), []),
            _with_defects(_cat(name="B"), ["X"]),
            _with_defects(_cat(name="C"), ["X", "Y"]),
        ]
        result = filter_cats_query(cats, _block(FilterType.DEFECTS_COUNT, Operator.LTE, 1))
        assert set(_names(result)) == {"A", "B"}


# ===========================================================================
# 3. Basic filtering — string fields
# ===========================================================================

class TestStringFieldFiltering:
    """Single-block filters on string attributes (gender, sexuality, room)."""

    def test_gender_eq_match(self):
        cats = [_cat(name="M", gender="male"), _cat(name="F", gender="female")]
        result = filter_cats_query(cats, _block(FilterType.GENDER, Operator.EQ, "male"))
        assert _names(result) == ["M"]

    def test_gender_ne(self):
        cats = [_cat(name="M", gender="male"), _cat(name="F", gender="female")]
        result = filter_cats_query(cats, _block(FilterType.GENDER, Operator.NE, "male"))
        assert _names(result) == ["F"]

    def test_sexuality_eq_gay(self):
        cats = [_cat(name="S", sexuality="straight"), _cat(name="G", sexuality="gay")]
        result = filter_cats_query(cats, _block(FilterType.SEXUALITY, Operator.EQ, "gay"))
        assert _names(result) == ["G"]

    def test_sexuality_ne(self):
        cats = [_cat(name="S", sexuality="straight"), _cat(name="B", sexuality="bi")]
        result = filter_cats_query(cats, _block(FilterType.SEXUALITY, Operator.NE, "straight"))
        assert _names(result) == ["B"]

    def test_room_eq_match(self):
        cats = [_cat(name="A", room="Kitchen"), _cat(name="B", room="Garden")]
        result = filter_cats_query(cats, _block(FilterType.ROOM, Operator.EQ, "Kitchen"))
        assert _names(result) == ["A"]

    def test_room_ne_match(self):
        cats = [_cat(name="A", room="Kitchen"), _cat(name="B", room="Garden")]
        result = filter_cats_query(cats, _block(FilterType.ROOM, Operator.NE, "Kitchen"))
        assert _names(result) == ["B"]

    def test_room_contains_case_insensitive(self):
        cats = [_cat(name="A", room="Living Room"), _cat(name="B", room="Kitchen")]
        result = filter_cats_query(cats, _block(FilterType.ROOM, Operator.CONTAINS, "living"))
        assert _names(result) == ["A"]

    def test_room_not_contains(self):
        cats = [_cat(name="A", room="Living Room"), _cat(name="B", room="Kitchen")]
        result = filter_cats_query(cats, _block(FilterType.ROOM, Operator.NOT_CONTAINS, "kitchen"))
        assert _names(result) == ["A"]

    def test_room_contains_partial_match(self):
        cats = [_cat(name="A", room="Breeding Chamber"), _cat(name="B", room="Storage")]
        result = filter_cats_query(cats, _block(FilterType.ROOM, Operator.CONTAINS, "Chamber"))
        assert _names(result) == ["A"]


# ===========================================================================
# 4. AND logical combinations
# ===========================================================================

class TestAndLogic:
    """All children must match (AND group)."""

    def test_and_both_true_passes(self):
        cat = _with_abilities(_cat(gender="male"), ["Slash"])
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.ABILITIES, Operator.CONTAINS, "Slash"),
        )
        assert evaluate_filter(cat, tree) is True

    def test_and_one_false_fails(self):
        cat = _with_abilities(_cat(gender="male"), ["Slash"])
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.ABILITIES, Operator.CONTAINS, "Fireball"),  # absent
        )
        assert evaluate_filter(cat, tree) is False

    def test_and_all_false_fails(self):
        cat = _cat(gender="female")
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.ABILITIES, Operator.IS_NOT_EMPTY),
        )
        assert evaluate_filter(cat, tree) is False

    def test_and_three_conditions_all_true(self):
        cat = _with_mutations(_with_abilities(_cat(gender="female"), ["Kick"]), ["Extra Limb"])
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "female"),
            _block(FilterType.ABILITIES, Operator.CONTAINS, "Kick"),
            _block(FilterType.MUTATION, Operator.CONTAINS, "Extra Limb"),
        )
        assert evaluate_filter(cat, tree) is True

    def test_and_short_circuits_on_first_false(self):
        """AND stops at the first False — remaining children are not evaluated."""
        evaluated = []

        class _TrackingCat:
            gender = "female"
            abilities = []
            passive_abilities = []
            mutations = []
            mutation_chip_items = []
            defects = []
            defect_chip_items = []
            disorders = []
            sexuality = "straight"
            room = ""

        # The second block would raise if reached; confirm no exception.
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),  # False → stop
            _block(FilterType.GENDER, Operator.EQ, "male"),  # not reached
        )
        assert evaluate_filter(_TrackingCat(), tree) is False


# ===========================================================================
# 5. OR logical combinations
# ===========================================================================

class TestOrLogic:
    """At least one child must match (OR group)."""

    def test_or_first_true_passes(self):
        cat = _cat(gender="male", sexuality="straight")
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.SEXUALITY, Operator.EQ, "gay"),
            op=LogicalOp.OR,
        )
        assert evaluate_filter(cat, tree) is True

    def test_or_second_true_passes(self):
        cat = _cat(gender="female", sexuality="gay")
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.SEXUALITY, Operator.EQ, "gay"),
            op=LogicalOp.OR,
        )
        assert evaluate_filter(cat, tree) is True

    def test_or_all_false_fails(self):
        cat = _cat(gender="female", sexuality="straight")
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.SEXUALITY, Operator.EQ, "gay"),
            op=LogicalOp.OR,
        )
        assert evaluate_filter(cat, tree) is False

    def test_or_all_true_passes(self):
        cat = _with_abilities(_cat(gender="male"), ["Slash"])
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.ABILITIES, Operator.CONTAINS, "Slash"),
            op=LogicalOp.OR,
        )
        assert evaluate_filter(cat, tree) is True

    def test_or_filters_multiple_cats(self):
        cats = [
            _cat(name="M",  gender="male",   sexuality="straight"),
            _cat(name="FG", gender="female", sexuality="gay"),
            _cat(name="FS", gender="female", sexuality="straight"),
        ]
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            _block(FilterType.SEXUALITY, Operator.EQ, "gay"),
            op=LogicalOp.OR,
        )
        result = filter_cats_query(cats, tree)
        assert set(_names(result)) == {"M", "FG"}


# ===========================================================================
# 6. Nested groups
# ===========================================================================

class TestNestedGroups:
    """Groups inside groups — mixed AND/OR logic at multiple depths."""

    def test_and_of_two_or_groups_passes(self):
        """(male OR female) AND (has Slash OR has Kick)."""
        cat = _with_abilities(_cat(gender="male"), ["Kick"])
        tree = _group(
            _group(
                _block(FilterType.GENDER, Operator.EQ, "male"),
                _block(FilterType.GENDER, Operator.EQ, "female"),
                op=LogicalOp.OR,
            ),
            _group(
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Slash"),
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Kick"),
                op=LogicalOp.OR,
            ),
        )
        assert evaluate_filter(cat, tree) is True

    def test_and_of_two_or_groups_outer_fails(self):
        """Ability OR condition fails → outer AND fails."""
        cat = _with_abilities(_cat(gender="male"), ["Slash"])
        tree = _group(
            _group(
                _block(FilterType.GENDER, Operator.EQ, "male"),
                _block(FilterType.GENDER, Operator.EQ, "female"),
                op=LogicalOp.OR,
            ),
            _group(
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Fireball"),
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Throw"),
                op=LogicalOp.OR,
            ),
        )
        assert evaluate_filter(cat, tree) is False

    def test_three_level_nesting(self):
        """((female AND gay) OR (male AND straight)) AND has mutation."""
        cat_a = _with_mutations(_cat(name="A", gender="female", sexuality="gay"), ["X"])
        cat_b = _with_mutations(_cat(name="B", gender="male",   sexuality="straight"), ["X"])
        cat_c = _with_mutations(_cat(name="C", gender="male",   sexuality="gay"), ["X"])    # wrong combo
        cat_d = _cat(name="D", gender="female", sexuality="gay")                             # no mutation

        combo_condition = _group(
            _group(
                _block(FilterType.GENDER, Operator.EQ, "female"),
                _block(FilterType.SEXUALITY, Operator.EQ, "gay"),
            ),
            _group(
                _block(FilterType.GENDER, Operator.EQ, "male"),
                _block(FilterType.SEXUALITY, Operator.EQ, "straight"),
            ),
            op=LogicalOp.OR,
        )
        tree = _group(combo_condition, _block(FilterType.MUTATION, Operator.IS_NOT_EMPTY))

        result = filter_cats_query([cat_a, cat_b, cat_c, cat_d], tree)
        assert set(_names(result)) == {"A", "B"}

    def test_deeply_nested_a_and_b_or_c_and_d(self):
        """a AND (b OR (c AND d))."""
        cat = _with_abilities(_with_mutations(_cat(gender="male"), ["Mut1"]), ["Slash"])
        cat.disorders = ["Rage"]

        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),             # a — True
            _group(
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Throw"),   # b — False
                _group(                                                       # c AND d
                    _block(FilterType.MUTATION, Operator.CONTAINS, "Mut1"),  # c — True
                    _block(FilterType.DISORDER, Operator.CONTAINS, "Rage"),  # d — True
                ),
                op=LogicalOp.OR,
            ),
        )
        assert evaluate_filter(cat, tree) is True

    def test_nested_group_all_cats_dataset(self):
        """Validate that nesting correctly partitions a multi-cat dataset."""
        cats = [
            _cat(name="MStr", gender="male",   sexuality="straight"),
            _cat(name="MGay", gender="male",   sexuality="gay"),
            _cat(name="FBi",  gender="female", sexuality="bi"),
            _cat(name="FStr", gender="female", sexuality="straight"),
        ]
        # (male AND straight) OR (female AND bi)
        tree = _group(
            _group(
                _block(FilterType.GENDER, Operator.EQ, "male"),
                _block(FilterType.SEXUALITY, Operator.EQ, "straight"),
            ),
            _group(
                _block(FilterType.GENDER, Operator.EQ, "female"),
                _block(FilterType.SEXUALITY, Operator.EQ, "bi"),
            ),
            op=LogicalOp.OR,
        )
        result = filter_cats_query(cats, tree)
        assert set(_names(result)) == {"MStr", "FBi"}

    def test_empty_inner_group_acts_as_passthrough(self):
        """An empty inner group always returns True, so AND with it still passes."""
        cat = _cat(gender="male")
        tree = _group(
            _block(FilterType.GENDER, Operator.EQ, "male"),
            FilterGroup(),  # empty group → True
        )
        assert evaluate_filter(cat, tree) is True


# ===========================================================================
# 7. Edge cases
# ===========================================================================

class TestEdgeCases:

    def test_none_tree_returns_all_cats(self):
        cats = [_cat(name=str(i)) for i in range(5)]
        result = filter_cats_query(cats, None)
        assert len(result) == 5

    def test_empty_filter_group_passes_all(self):
        cats = [_cat(name=str(i)) for i in range(3)]
        result = filter_cats_query(cats, FilterGroup())
        assert len(result) == 3

    def test_empty_and_group_evaluates_true(self):
        assert evaluate_filter(_cat(), _group(op=LogicalOp.AND)) is True

    def test_empty_or_group_evaluates_true(self):
        assert evaluate_filter(_cat(), _group(op=LogicalOp.OR)) is True

    def test_empty_cat_list_returns_empty(self):
        tree = _block(FilterType.GENDER, Operator.EQ, "male")
        assert filter_cats_query([], tree) == []

    def test_invalid_operator_list_field_raises(self):
        cat = _with_abilities(_cat(), ["Slash"])
        block = _block(FilterType.ABILITIES, "bad_op", "Slash")
        with pytest.raises(FilterEvaluationError):
            evaluate_filter(cat, block)

    def test_invalid_operator_numeric_field_raises(self):
        cat = _with_mutations(_cat(), ["X"])
        block = _block(FilterType.MUTATION_COUNT, "bad_op", 3)
        with pytest.raises(FilterEvaluationError):
            evaluate_filter(cat, block)

    def test_invalid_operator_string_field_raises(self):
        cat = _cat(gender="male")
        block = _block(FilterType.GENDER, "bad_op", "male")
        with pytest.raises(FilterEvaluationError):
            evaluate_filter(cat, block)

    def test_unknown_filter_type_raises(self):
        cat = _cat()
        block = FilterBlock(filter_type="unknown_field", operator="eq", value="x")
        with pytest.raises(FilterEvaluationError):
            evaluate_filter(cat, block)

    def test_missing_abilities_attr_treated_as_empty(self):
        class _NoCat:
            name = "NoCat"
        result = filter_cats_query([_NoCat()], _block(FilterType.ABILITIES, Operator.IS_EMPTY))
        assert len(result) == 1

    def test_missing_mutation_chip_items_counted_as_zero(self):
        class _NoCat:
            name = "NoCat"
        result = filter_cats_query([_NoCat()], _block(FilterType.MUTATION_COUNT, Operator.EQ, 0))
        assert len(result) == 1

    def test_missing_gender_falls_back_to_empty_string(self):
        class _NoCat:
            name = "NoCat"
        result = filter_cats_query([_NoCat()], _block(FilterType.GENDER, Operator.EQ, ""))
        assert len(result) == 1

    def test_missing_sexuality_not_equal_to_gay(self):
        class _NoCat:
            name = "NoCat"
        # default for missing sexuality is "straight", not "gay"
        result = filter_cats_query([_NoCat()], _block(FilterType.SEXUALITY, Operator.EQ, "gay"))
        assert result == []

    def test_missing_room_falls_back_to_empty_string(self):
        class _NoCat:
            name = "NoCat"
        result = filter_cats_query([_NoCat()], _block(FilterType.ROOM, Operator.EQ, ""))
        assert len(result) == 1

    def test_filter_does_not_mutate_input_list(self):
        cats = [_cat(name=str(i)) for i in range(5)]
        snapshot = list(cats)
        filter_cats_query(cats, _block(FilterType.ABILITIES, Operator.IS_NOT_EMPTY))
        assert cats == snapshot

    def test_numeric_value_passed_as_string_is_coerced(self):
        """Passing "8" (str) instead of 8 (int) must still work."""
        cat = _with_mutations(_cat(), ["x"] * 8)
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.EQ, "8"))

    def test_any_of_with_empty_list_never_matches(self):
        cat = _with_abilities(_cat(), ["Slash"])
        result = filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.ANY_OF, []))
        assert result == []

    def test_none_of_with_empty_list_always_passes(self):
        """none_of [] means 'none of nothing', which is vacuously True."""
        cat = _with_abilities(_cat(), ["Slash"])
        assert filter_cats_query([cat], _block(FilterType.ABILITIES, Operator.NONE_OF, []))

    def test_none_value_for_numeric_eq_zero(self):
        cat = _with_mutations(_cat(), [])
        assert filter_cats_query([cat], _block(FilterType.MUTATION_COUNT, Operator.EQ, None))

    def test_is_empty_on_none_attribute_passes(self):
        """Attribute returning None is treated as empty list."""
        class _NullCat:
            abilities = None
        result = filter_cats_query([_NullCat()], _block(FilterType.ABILITIES, Operator.IS_EMPTY))
        assert len(result) == 1

    def test_is_not_empty_on_none_attribute_fails(self):
        class _NullCat:
            abilities = None
        result = filter_cats_query([_NullCat()], _block(FilterType.ABILITIES, Operator.IS_NOT_EMPTY))
        assert result == []

    def test_single_block_used_as_tree_root(self):
        """filter_cats_query accepts a bare FilterBlock as root (not just FilterGroup)."""
        cats = [_cat(name="M", gender="male"), _cat(name="F", gender="female")]
        block = _block(FilterType.GENDER, Operator.EQ, "female")
        result = filter_cats_query(cats, block)
        assert _names(result) == ["F"]


# ===========================================================================
# 8. Serialisation round-trip
# ===========================================================================

class TestSerialisation:
    """group_to_dict → json.dumps → json.loads → group_from_dict is lossless."""

    def test_simple_block_roundtrip(self):
        original = FilterGroup(
            logical_op=LogicalOp.AND.value,
            children=[
                FilterBlock(FilterType.GENDER.value, Operator.EQ.value, "male"),
            ],
        )
        restored = group_from_dict(group_to_dict(original))

        assert restored.logical_op == original.logical_op
        assert len(restored.children) == 1
        block = restored.children[0]
        assert isinstance(block, FilterBlock)
        assert block.filter_type == FilterType.GENDER.value
        assert block.operator    == Operator.EQ.value
        assert block.value       == "male"

    def test_nested_group_roundtrip_through_json(self):
        original = _group(
            _group(
                _block(FilterType.GENDER, Operator.EQ, "male"),
                _block(FilterType.SEXUALITY, Operator.EQ, "straight"),
            ),
            _block(FilterType.MUTATION_COUNT, Operator.GTE, 8),
        )
        json_str  = json.dumps(group_to_dict(original))
        restored  = group_from_dict(json.loads(json_str))

        assert restored.logical_op == LogicalOp.AND.value
        assert len(restored.children) == 2

        inner = restored.children[0]
        assert isinstance(inner, FilterGroup)
        assert len(inner.children) == 2

        blk = restored.children[1]
        assert isinstance(blk, FilterBlock)
        assert blk.filter_type == FilterType.MUTATION_COUNT.value
        assert blk.operator    == Operator.GTE.value
        assert blk.value       == 8

    def test_roundtrip_preserves_or_logic(self):
        original = _group(
            _block(FilterType.GENDER, Operator.EQ, "female"),
            _block(FilterType.SEXUALITY, Operator.EQ, "bi"),
            op=LogicalOp.OR,
        )
        restored = group_from_dict(group_to_dict(original))
        assert restored.logical_op == LogicalOp.OR.value

    def test_roundtrip_preserves_none_value(self):
        original = _group(_block(FilterType.ABILITIES, Operator.IS_EMPTY))
        restored = group_from_dict(group_to_dict(original))
        assert restored.children[0].value is None

    def test_roundtrip_preserves_list_value(self):
        original = _group(_block(FilterType.ABILITIES, Operator.ANY_OF, ["Slash", "Kick"]))
        restored = group_from_dict(group_to_dict(original))
        assert restored.children[0].value == ["Slash", "Kick"]

    def test_from_dict_raises_on_unknown_kind(self):
        bad_data = {
            "kind":       "group",
            "logical_op": "AND",
            "children":   [{"kind": "mystery"}],
        }
        with pytest.raises(ValueError, match="Unknown node kind"):
            group_from_dict(bad_data)

    def test_group_from_dict_raises_on_wrong_top_kind(self):
        bad_data = {"kind": "block", "filter_type": "gender", "operator": "eq", "value": "x"}
        with pytest.raises(ValueError):
            group_from_dict(bad_data)

    def test_serialised_tree_produces_identical_results(self):
        """Restored tree must filter identically to the original."""
        cats = [
            _with_mutations(_cat(name="A", gender="female"), ["x"] * 9),
            _with_mutations(_cat(name="B", gender="male"),   ["x"] * 9),
            _with_mutations(_cat(name="C", gender="female"), ["x"] * 7),
        ]
        tree = _group(
            _block(FilterType.GENDER,         Operator.EQ,  "female"),
            _block(FilterType.MUTATION_COUNT, Operator.GTE, 8),
        )
        expected = filter_cats_query(cats, tree)
        restored = group_from_dict(json.loads(json.dumps(group_to_dict(tree))))
        assert _names(filter_cats_query(cats, restored)) == _names(expected)


# ===========================================================================
# 9. Preset system
# ===========================================================================

class TestPresets:
    """save_preset → load_preset → filter produces identical results."""

    @pytest.fixture
    def tmp_preset_path(self, tmp_path):
        return str(tmp_path / "presets.json")

    def test_save_and_load_roundtrip(self, tmp_preset_path):
        tree = _group(
            _block(FilterType.GENDER,         Operator.EQ,  "female"),
            _block(FilterType.MUTATION_COUNT, Operator.GTE, 8),
        )
        save_preset("GoodBreeders", tree, tmp_preset_path)
        loaded = load_preset("GoodBreeders", tmp_preset_path)

        assert loaded.logical_op == LogicalOp.AND.value
        assert len(loaded.children) == 2
        b0 = loaded.children[0]
        assert isinstance(b0, FilterBlock)
        assert b0.value == "female"

    def test_loaded_preset_produces_identical_results(self, tmp_preset_path):
        cats = [
            _with_mutations(_cat(name="A", gender="female"), ["x"] * 9),
            _with_mutations(_cat(name="B", gender="male"),   ["x"] * 9),
            _with_mutations(_cat(name="C", gender="female"), ["x"] * 7),
        ]
        tree = _group(
            _block(FilterType.GENDER,         Operator.EQ,  "female"),
            _block(FilterType.MUTATION_COUNT, Operator.GTE, 8),
        )
        expected = filter_cats_query(cats, tree)
        save_preset("Test", tree, tmp_preset_path)
        result = filter_cats_query(cats, load_preset("Test", tmp_preset_path))

        assert _names(result) == _names(expected)
        assert _names(result) == ["A"]

    def test_load_nonexistent_preset_raises_key_error(self, tmp_preset_path):
        with pytest.raises(KeyError):
            load_preset("DoesNotExist", tmp_preset_path)

    def test_list_presets_empty_when_no_file(self, tmp_preset_path):
        assert list_presets(tmp_preset_path) == []

    def test_list_presets_sorted_alphabetically(self, tmp_preset_path):
        save_preset("Zebra",   FilterGroup(), tmp_preset_path)
        save_preset("Alpha",   FilterGroup(), tmp_preset_path)
        save_preset("Midterm", FilterGroup(), tmp_preset_path)
        assert list_presets(tmp_preset_path) == ["Alpha", "Midterm", "Zebra"]

    def test_delete_existing_preset(self, tmp_preset_path):
        save_preset("ToDelete", FilterGroup(), tmp_preset_path)
        assert delete_preset("ToDelete", tmp_preset_path) is True
        assert list_presets(tmp_preset_path) == []

    def test_delete_nonexistent_preset_returns_false(self, tmp_preset_path):
        assert delete_preset("Ghost", tmp_preset_path) is False

    def test_preset_overwrite_updates_value(self, tmp_preset_path):
        tree1 = _group(_block(FilterType.GENDER, Operator.EQ, "male"))
        tree2 = _group(_block(FilterType.GENDER, Operator.EQ, "female"))
        save_preset("P", tree1, tmp_preset_path)
        save_preset("P", tree2, tmp_preset_path)
        loaded = load_preset("P", tmp_preset_path)
        assert loaded.children[0].value == "female"

    def test_multiple_presets_coexist(self, tmp_preset_path):
        save_preset("A", _group(_block(FilterType.GENDER, Operator.EQ, "male")),   tmp_preset_path)
        save_preset("B", _group(_block(FilterType.GENDER, Operator.EQ, "female")), tmp_preset_path)
        assert set(list_presets(tmp_preset_path)) == {"A", "B"}

    def test_preset_missing_file_raises_key_error_not_file_error(self, tmp_preset_path):
        """A non-existent file should raise KeyError (preset not found), not FileNotFoundError."""
        with pytest.raises(KeyError):
            load_preset("X", "/nonexistent/definitely/presets.json")

    def test_save_and_load_nested_preset(self, tmp_preset_path):
        tree = _group(
            _group(
                _block(FilterType.GENDER,    Operator.EQ, "female"),
                _block(FilterType.SEXUALITY, Operator.EQ, "bi"),
                op=LogicalOp.OR,
            ),
            _block(FilterType.MUTATION_COUNT, Operator.GTE, 8),
            _block(FilterType.DISORDER,       Operator.IS_EMPTY),
        )
        save_preset("Nested", tree, tmp_preset_path)
        loaded = load_preset("Nested", tmp_preset_path)
        # Top-level AND with 3 children
        assert loaded.logical_op == LogicalOp.AND.value
        assert len(loaded.children) == 3
        # First child is OR group
        inner = loaded.children[0]
        assert isinstance(inner, FilterGroup)
        assert inner.logical_op == LogicalOp.OR.value


# ===========================================================================
# 10. Complex end-to-end example — realistic breeder filter
# ===========================================================================

class TestComplexBreederFilter:
    """
    Realistic scenario: find the best newborns for breeding.

    Filter logic
    ~~~~~~~~~~~~
    (
        (gender == "female"  OR  sexuality == "bi")
        AND  mutation_count >= 8
        AND  disorder IS_EMPTY
        AND  (abilities CONTAINS "Slash"  OR  abilities CONTAINS "Piercing Strike")
    )

    Dataset
    ~~~~~~~
    A  female, 9 mutations, no disorders, has Slash            → MATCH
    B  male straight, 9 mutations, no disorders, has Slash     → NO  (not female, not bi)
    C  bi male, 8 mutations, no disorders, has Piercing Strike → MATCH  (bi qualifies)
    D  female, 8 mutations, has Rage disorder, has Slash       → NO  (has disorder)
    E  female, 7 mutations, no disorders, has Slash            → NO  (< 8 mutations)
    F  female, 9 mutations, no disorders, no relevant ability  → NO  (wrong ability)
    """

    def _dataset(self) -> list[_FakeCat]:
        a = _with_mutations(_with_abilities(_cat(name="A", gender="female"), ["Slash"]), ["x"] * 9)
        b = _with_mutations(_with_abilities(_cat(name="B", gender="male",   sexuality="straight"), ["Slash"]),            ["x"] * 9)
        c = _with_mutations(_with_abilities(_cat(name="C", gender="male",   sexuality="bi"),       ["Piercing Strike"]), ["x"] * 8)
        d = _with_disorders(_with_mutations(_with_abilities(_cat(name="D", gender="female"), ["Slash"]), ["x"] * 8), ["Rage"])
        e = _with_mutations(_with_abilities(_cat(name="E", gender="female"), ["Slash"]), ["x"] * 7)
        f = _with_mutations(_with_abilities(_cat(name="F", gender="female"), ["Kick"]),  ["x"] * 9)
        return [a, b, c, d, e, f]

    def _tree(self) -> FilterGroup:
        return _group(
            _group(
                _block(FilterType.GENDER,    Operator.EQ, "female"),
                _block(FilterType.SEXUALITY, Operator.EQ, "bi"),
                op=LogicalOp.OR,
            ),
            _block(FilterType.MUTATION_COUNT, Operator.GTE, 8),
            _block(FilterType.DISORDER,       Operator.IS_EMPTY),
            _group(
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Slash"),
                _block(FilterType.ABILITIES, Operator.CONTAINS, "Piercing Strike"),
                op=LogicalOp.OR,
            ),
        )

    def test_correct_cats_selected(self):
        result = filter_cats_query(self._dataset(), self._tree())
        assert set(_names(result)) == {"A", "C"}

    def test_no_false_positives(self):
        result = filter_cats_query(self._dataset(), self._tree())
        assert "B" not in _names(result)
        assert "D" not in _names(result)
        assert "E" not in _names(result)
        assert "F" not in _names(result)

    def test_complex_filter_survives_serialisation(self):
        """Serialise → JSON → deserialise → filter: same result as original."""
        cats   = self._dataset()
        tree   = self._tree()
        expected = _names(filter_cats_query(cats, tree))

        restored = group_from_dict(json.loads(json.dumps(group_to_dict(tree))))
        assert _names(filter_cats_query(cats, restored)) == expected

    def test_complex_filter_survives_preset_save_load(self, tmp_path):
        preset_path = str(tmp_path / "presets.json")
        cats = self._dataset()
        tree = self._tree()

        save_preset("BestBreeders", tree, preset_path)
        loaded = load_preset("BestBreeders", preset_path)
        result = filter_cats_query(cats, loaded)

        assert set(_names(result)) == {"A", "C"}

    def test_empty_dataset_returns_empty(self):
        assert filter_cats_query([], self._tree()) == []

    def test_no_matching_cats_returns_empty(self):
        cats = [
            _with_mutations(_cat(name="X", gender="male"), ["x"] * 9),  # not female/bi
        ]
        result = filter_cats_query(cats, self._tree())
        assert result == []

