"""
utils/cat_query_filters.py
==========================
Advanced, modular query-builder filter system for cat lists.

This module provides a tree-structured filter model (filter blocks + groups
with AND/OR logic), an evaluation engine, and a JSON-based preset system.

Architecture
------------
``FilterBlock``   — a single leaf condition (type + operator + value).
``FilterGroup``   — an internal node that combines blocks/sub-groups with
                    AND or OR logic.  Groups can be arbitrarily nested.

Public API
----------
FilterType          — enum of filterable cat attributes
Operator            — enum of comparison operators
LogicalOp           — enum: AND | OR
FilterBlock         — single filter condition
FilterGroup         — logical group (AND/OR) of blocks / sub-groups
FilterNode          — type alias: FilterBlock | FilterGroup
ALLOWED_OPERATORS   — dict mapping FilterType → allowed Operators (for UI hints)
evaluate_filter(cat, node)          → bool
filter_cats_query(cats, tree)       → list
group_to_dict(group)                → dict   (JSON-serialisable)
group_from_dict(data)               → FilterGroup
save_preset(name, group, path)      → None
load_preset(name, path)             → FilterGroup
list_presets(path)                  → list[str]
delete_preset(name, path)           → bool

Extending the system
--------------------
Adding a new filter type requires three steps:
  1. Add the enum member to ``FilterType``.
  2. Add the allowed operators to ``ALLOWED_OPERATORS``.
  3. Add a branch (or helper) inside ``_evaluate_block``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class LogicalOp(str, Enum):
    """Logical operator used to combine children results inside a group."""
    AND = "AND"
    OR  = "OR"


class FilterType(str, Enum):
    """Filterable cat attribute identifiers.

    Each value maps to a specific Cat field (see docstring of
    ``_evaluate_block`` for the exact mapping).
    """
    ABILITIES      = "abilities"       # list[str]  — cat.abilities
    PASSIVES       = "passives"        # list[str]  — cat.passive_abilities
    MUTATION       = "mutation"        # list[str]  — cat.mutations (display names)
    MUTATION_COUNT = "mutation_count"  # int        — len(cat.mutation_chip_items)
    GENDER         = "gender"          # str        — cat.gender
    SEXUALITY      = "sexuality"       # str        — cat.sexuality
    DEFECTS        = "defects"         # list[str]  — cat.defects (visual birth defects)
    DEFECTS_COUNT  = "defects_count"   # int        — len(cat.defect_chip_items)
    DISORDER       = "disorder"        # list[str]  — cat.disorders
    ROOM           = "room"            # str        — cat.room


class Operator(str, Enum):
    """Comparison operators available for filter blocks.

    List operators (for list-type fields)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    CONTAINS      — single value (str) is an element of the field list
    NOT_CONTAINS  — single value is NOT an element of the field list
    ANY_OF        — at least one element of value (list[str]) is in the field list
    NONE_OF       — none of the elements of value appear in the field list
    IS_EMPTY      — the field list is empty         (value is ignored)
    IS_NOT_EMPTY  — the field list is non-empty     (value is ignored)

    Numeric operators (for count fields)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    EQ   — equal to
    NE   — not equal to
    LT   — strictly less than
    LTE  — less than or equal to
    GT   — strictly greater than
    GTE  — greater than or equal to

    String operators (for gender, sexuality, room)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    EQ / NE / CONTAINS / NOT_CONTAINS
    (CONTAINS / NOT_CONTAINS are case-insensitive substring matches)
    """
    # List membership
    CONTAINS     = "contains"
    NOT_CONTAINS = "not_contains"
    ANY_OF       = "any_of"
    NONE_OF      = "none_of"
    IS_EMPTY     = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    # Numeric comparison
    EQ  = "eq"
    NE  = "ne"
    LT  = "lt"
    LTE = "lte"
    GT  = "gt"
    GTE = "gte"


# Operators valid for each filter type.
# Used for input validation and UI hints (e.g. populating operator dropdowns).
ALLOWED_OPERATORS: dict[FilterType, tuple[Operator, ...]] = {
    FilterType.ABILITIES: (
        Operator.CONTAINS, Operator.NOT_CONTAINS,
        Operator.ANY_OF, Operator.NONE_OF,
        Operator.IS_EMPTY, Operator.IS_NOT_EMPTY,
    ),
    FilterType.PASSIVES: (
        Operator.CONTAINS, Operator.NOT_CONTAINS,
        Operator.ANY_OF, Operator.NONE_OF,
        Operator.IS_EMPTY, Operator.IS_NOT_EMPTY,
    ),
    FilterType.MUTATION: (
        Operator.CONTAINS, Operator.NOT_CONTAINS,
        Operator.ANY_OF, Operator.NONE_OF,
        Operator.IS_EMPTY, Operator.IS_NOT_EMPTY,
    ),
    FilterType.MUTATION_COUNT: (
        Operator.EQ, Operator.NE,
        Operator.LT, Operator.LTE,
        Operator.GT, Operator.GTE,
    ),
    FilterType.GENDER:    (Operator.EQ, Operator.NE),
    FilterType.SEXUALITY: (Operator.EQ, Operator.NE),
    FilterType.DEFECTS: (
        Operator.CONTAINS, Operator.NOT_CONTAINS,
        Operator.ANY_OF, Operator.NONE_OF,
        Operator.IS_EMPTY, Operator.IS_NOT_EMPTY,
    ),
    FilterType.DEFECTS_COUNT: (
        Operator.EQ, Operator.NE,
        Operator.LT, Operator.LTE,
        Operator.GT, Operator.GTE,
    ),
    FilterType.DISORDER: (
        Operator.CONTAINS, Operator.NOT_CONTAINS,
        Operator.ANY_OF, Operator.NONE_OF,
        Operator.IS_EMPTY, Operator.IS_NOT_EMPTY,
    ),
    FilterType.ROOM: (
        Operator.EQ, Operator.NE,
        Operator.CONTAINS, Operator.NOT_CONTAINS,
    ),
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FilterBlock:
    """A single leaf condition in the filter tree.

    Attributes
    ----------
    filter_type:
        Which cat attribute to test.  Should be a ``FilterType`` value (str),
        but plain strings are accepted for forward-compatible custom types.
    operator:
        How to compare the attribute value.  Should be an ``Operator`` value
        (str), but plain strings are accepted for extensibility.
    value:
        The comparison target.  Expected type depends on the operator:
          - CONTAINS / NOT_CONTAINS (list fields) : str
          - ANY_OF / NONE_OF                      : list[str]
          - IS_EMPTY / IS_NOT_EMPTY               : None (value is ignored)
          - Numeric operators (EQ/NE/LT/…)        : int | float | str (auto-coerced)
          - EQ / NE / CONTAINS / NOT_CONTAINS (string fields) : str
    """

    filter_type: str   # FilterType value (or custom string)
    operator:    str   # Operator value (or custom string)
    value:       Any = None

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict representation."""
        return {
            "kind":        "block",
            "filter_type": self.filter_type,
            "operator":    self.operator,
            "value":       self.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterBlock":
        """Deserialise a ``FilterBlock`` from a plain dict."""
        return cls(
            filter_type=data["filter_type"],
            operator=data["operator"],
            value=data.get("value"),
        )


@dataclass
class FilterGroup:
    """An internal (non-leaf) node — a logical group of blocks and/or sub-groups.

    Attributes
    ----------
    logical_op:
        ``"AND"`` — all children must match (default).
        ``"OR"``  — at least one child must match.
    children:
        Ordered list of ``FilterBlock`` or nested ``FilterGroup`` objects.
        An **empty** group always evaluates to ``True`` (pass-through).

    Example — (female OR bi) AND mutation_count >= 8::

        FilterGroup(
            logical_op="AND",
            children=[
                FilterGroup(
                    logical_op="OR",
                    children=[
                        FilterBlock("gender",    "eq", "female"),
                        FilterBlock("sexuality", "eq", "bi"),
                    ],
                ),
                FilterBlock("mutation_count", "gte", 8),
            ],
        )
    """

    logical_op: str = LogicalOp.AND.value
    children:   list[Union[FilterBlock, "FilterGroup"]] = field(default_factory=list)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict representation (recursive)."""
        return {
            "kind":       "group",
            "logical_op": self.logical_op,
            "children":   [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterGroup":
        """Deserialise a ``FilterGroup`` from a plain dict (recursive)."""
        children: list[Union[FilterBlock, FilterGroup]] = []
        for child_data in data.get("children", []):
            kind = child_data.get("kind")
            if kind == "block":
                children.append(FilterBlock.from_dict(child_data))
            elif kind == "group":
                children.append(FilterGroup.from_dict(child_data))
            else:
                raise ValueError(f"Unknown node kind: {kind!r}")
        return cls(
            logical_op=data.get("logical_op", LogicalOp.AND.value),
            children=children,
        )


# Type alias: any node in the filter tree.
FilterNode = Union[FilterBlock, FilterGroup]


# ---------------------------------------------------------------------------
# Evaluation error
# ---------------------------------------------------------------------------

class FilterEvaluationError(Exception):
    """Raised when a filter block contains an unsupported operator/type pair
    or references an unknown filter type."""


# ---------------------------------------------------------------------------
# Internal: attribute accessors
# ---------------------------------------------------------------------------

# Sets of filter type strings partitioned by their data kind.
_LIST_TYPES = {
    FilterType.ABILITIES.value,
    FilterType.PASSIVES.value,
    FilterType.MUTATION.value,
    FilterType.DEFECTS.value,
    FilterType.DISORDER.value,
}
_COUNT_TYPES = {
    FilterType.MUTATION_COUNT.value,
    FilterType.DEFECTS_COUNT.value,
}
_STRING_TYPES = {
    FilterType.GENDER.value,
    FilterType.SEXUALITY.value,
    FilterType.ROOM.value,
}

# Maps filter_type → (cat_attribute_name, default_value)
_LIST_ATTR_MAP: dict[str, str] = {
    FilterType.ABILITIES.value: "abilities",
    FilterType.PASSIVES.value:  "passive_abilities",
    FilterType.MUTATION.value:  "mutations",
    FilterType.DEFECTS.value:   "defects",
    FilterType.DISORDER.value:  "disorders",
}
_STRING_ATTR_MAP: dict[str, tuple[str, str]] = {
    FilterType.GENDER.value:    ("gender",    ""),
    FilterType.SEXUALITY.value: ("sexuality", "straight"),
    FilterType.ROOM.value:      ("room",      ""),
}

# Room key → human-readable display name.
# Must stay in sync with ui/cat_manager.py::ROOM_DISPLAY_NAMES.
_ROOM_DISPLAY_NAMES: dict[str, str] = {
    "Floor1_Large": "RDC Gauche",
    "Floor1_Small": "RDC Droite",
    "Floor2_Small": "Etage Gauche",
    "Floor2_Large": "Etage Droite",
    "Attic":        "Grenier",
}


def _room_to_display(room: str) -> str:
    """Translate an internal room key to its display name (falls back to the key)."""
    return _ROOM_DISPLAY_NAMES.get(room, room)


def _get_list_field(cat: Any, filter_type: str) -> list:
    """Return the list field of *cat* for *filter_type*.

    Missing attributes are treated as empty lists (graceful degradation).
    """
    attr = _LIST_ATTR_MAP.get(filter_type)
    if attr is None:
        return []
    return list(getattr(cat, attr, []) or [])


def _get_count_field(cat: Any, filter_type: str) -> int:
    """Return the integer count for *filter_type* derived from *cat*."""
    if filter_type == FilterType.MUTATION_COUNT.value:
        return len(getattr(cat, "mutation_chip_items", []) or [])
    if filter_type == FilterType.DEFECTS_COUNT.value:
        return len(getattr(cat, "defect_chip_items", []) or [])
    return 0


def _get_str_field(cat: Any, filter_type: str) -> str:
    """Return the string field of *cat* for *filter_type*.

    For the ``room`` field the internal room key is translated to its
    human-readable display name (e.g. ``"Attic"`` → ``"Grenier"``).
    Missing attributes fall back to their documented default value.
    """
    attr, default = _STRING_ATTR_MAP.get(filter_type, (None, ""))
    if attr is None:
        return ""
    value = str(getattr(cat, attr, default) or default)
    if filter_type == FilterType.ROOM.value:
        value = _room_to_display(value)
    return value


# ---------------------------------------------------------------------------
# Internal: operator applicators
# ---------------------------------------------------------------------------

def _apply_list_operator(field_list: list, operator: str, value: Any) -> bool:
    """Apply a list-oriented *operator* to *field_list*."""
    if operator == Operator.CONTAINS.value:
        return str(value) in field_list

    if operator == Operator.NOT_CONTAINS.value:
        return str(value) not in field_list

    if operator == Operator.ANY_OF.value:
        values = value if isinstance(value, list) else [value]
        return any(str(v) in field_list for v in values)

    if operator == Operator.NONE_OF.value:
        values = value if isinstance(value, list) else [value]
        return all(str(v) not in field_list for v in values)

    if operator == Operator.IS_EMPTY.value:
        return len(field_list) == 0

    if operator == Operator.IS_NOT_EMPTY.value:
        return len(field_list) > 0

    raise FilterEvaluationError(
        f"Operator {operator!r} is not supported for list fields."
    )


def _apply_numeric_operator(count: int | float, operator: str, value: Any) -> bool:
    """Apply a numeric comparison *operator* to *count*."""
    try:
        num = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return False

    if operator == Operator.EQ.value:  return count == num
    if operator == Operator.NE.value:  return count != num
    if operator == Operator.LT.value:  return count <  num
    if operator == Operator.LTE.value: return count <= num
    if operator == Operator.GT.value:  return count >  num
    if operator == Operator.GTE.value: return count >= num

    raise FilterEvaluationError(
        f"Operator {operator!r} is not supported for numeric fields."
    )


def _apply_string_operator(field_str: str, operator: str, value: Any) -> bool:
    """Apply a string comparison *operator* to *field_str*."""
    val_str = str(value) if value is not None else ""

    if operator == Operator.EQ.value:           return field_str == val_str
    if operator == Operator.NE.value:           return field_str != val_str
    if operator == Operator.CONTAINS.value:     return val_str.lower() in field_str.lower()
    if operator == Operator.NOT_CONTAINS.value: return val_str.lower() not in field_str.lower()

    raise FilterEvaluationError(
        f"Operator {operator!r} is not supported for string fields."
    )


# ---------------------------------------------------------------------------
# Evaluation engine
# ---------------------------------------------------------------------------

def _evaluate_block(cat: Any, block: FilterBlock) -> bool:
    """Evaluate a single ``FilterBlock`` leaf condition against *cat*.

    Missing cat attributes are handled gracefully:
      - Missing list fields  → treated as empty lists.
      - Missing count fields → treated as 0.
      - Missing string fields → treated as "" (or "straight" for sexuality).

    Raises
    ------
    FilterEvaluationError
        When ``block.filter_type`` is unknown or ``block.operator`` is not
        applicable to that field's data type.
    """
    ft = block.filter_type

    if ft in _LIST_TYPES:
        return _apply_list_operator(
            _get_list_field(cat, ft),
            block.operator,
            block.value,
        )

    if ft in _COUNT_TYPES:
        return _apply_numeric_operator(
            _get_count_field(cat, ft),
            block.operator,
            block.value,
        )

    if ft in _STRING_TYPES:
        return _apply_string_operator(
            _get_str_field(cat, ft),
            block.operator,
            block.value,
        )

    raise FilterEvaluationError(f"Unknown filter type: {ft!r}")


def evaluate_filter(cat: Any, node: FilterNode) -> bool:
    """Recursively evaluate *node* (block or group) against *cat*.

    Parameters
    ----------
    cat:
        Any duck-typed object exposing the cat attributes referenced by
        the filter blocks in *node*.  Missing attributes are handled
        gracefully (see ``_evaluate_block``).
    node:
        A ``FilterBlock`` (leaf condition) or ``FilterGroup``
        (logical combinator with children).

    Returns
    -------
    bool
        ``True`` if *cat* satisfies the condition described by *node*.

    Notes
    -----
    An empty ``FilterGroup`` (no children) always returns ``True``,
    regardless of its ``logical_op``.  This makes it behave as a
    pass-through placeholder, which is the expected UX when no filters
    have been added yet.
    """
    if isinstance(node, FilterGroup):
        if not node.children:
            return True  # empty group → pass-through

        # Use a generator for short-circuit evaluation.
        child_results = (evaluate_filter(cat, child) for child in node.children)

        if node.logical_op == LogicalOp.OR.value:
            return any(child_results)
        # Default: AND
        return all(child_results)

    if isinstance(node, FilterBlock):
        return _evaluate_block(cat, node)

    raise FilterEvaluationError(f"Unknown node type: {type(node)!r}")


def filter_cats_query(
    cats: list,
    tree: FilterGroup | FilterBlock | None,
) -> list:
    """Filter *cats* using the given query *tree*.

    Parameters
    ----------
    cats:
        List of ``Cat`` objects (or duck-typed equivalents).
    tree:
        The root ``FilterGroup`` (or ``FilterBlock``).
        Pass ``None`` to return all cats unchanged.

    Returns
    -------
    list
        A **new** list containing only the cats that match *tree*.
        The original *cats* list is never mutated.
    """
    if tree is None:
        return list(cats)
    return [c for c in cats if evaluate_filter(c, tree)]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def group_to_dict(group: FilterGroup) -> dict:
    """Serialise *group* to a plain dict suitable for ``json.dumps``."""
    return group.to_dict()


def group_from_dict(data: dict) -> FilterGroup:
    """Deserialise a ``FilterGroup`` from a plain dict.

    Raises
    ------
    ValueError
        If ``data["kind"]`` is not ``"group"``.
    """
    if data.get("kind") != "group":
        raise ValueError(
            f"Expected a group dict (kind='group'), got kind={data.get('kind')!r}"
        )
    return FilterGroup.from_dict(data)


# ---------------------------------------------------------------------------
# Preset system — file-based JSON persistence
# ---------------------------------------------------------------------------

def save_preset(name: str, group: FilterGroup, presets_path: str) -> None:
    """Save *group* as a named preset in the JSON file at *presets_path*.

    The file is created if it does not exist.
    An existing preset with the same *name* is silently overwritten.

    Parameters
    ----------
    name:
        Unique preset name (e.g. ``"Best breeders"``).
    group:
        The root ``FilterGroup`` to save.
    presets_path:
        Absolute path to the JSON file that stores all presets.
    """
    presets = _load_presets_file(presets_path)
    presets[name] = group_to_dict(group)
    _save_presets_file(presets_path, presets)


def load_preset(name: str, presets_path: str) -> FilterGroup:
    """Load the preset named *name* from *presets_path*.

    Raises
    ------
    KeyError
        If no preset with that name exists in the file.
    """
    presets = _load_presets_file(presets_path)
    if name not in presets:
        raise KeyError(f"No preset named {name!r} found in {presets_path!r}")
    return group_from_dict(presets[name])


def list_presets(presets_path: str) -> list[str]:
    """Return a sorted list of preset names stored at *presets_path*."""
    return sorted(_load_presets_file(presets_path).keys())


def delete_preset(name: str, presets_path: str) -> bool:
    """Delete the preset named *name* from *presets_path*.

    Returns
    -------
    bool
        ``True`` if the preset was found and deleted, ``False`` if it
        did not exist.
    """
    presets = _load_presets_file(presets_path)
    if name not in presets:
        return False
    del presets[name]
    _save_presets_file(presets_path, presets)
    return True


# ── Private I/O helpers ────────────────────────────────────────────────────

def _load_presets_file(presets_path: str) -> dict:
    """Return the presets dict from the JSON file, or {} if it doesn't exist."""
    if not os.path.isfile(presets_path):
        return {}
    try:
        with open(presets_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_presets_file(presets_path: str, presets: dict) -> None:
    """Write *presets* to the JSON file at *presets_path*."""
    os.makedirs(os.path.dirname(os.path.abspath(presets_path)), exist_ok=True)
    with open(presets_path, "w", encoding="utf-8") as fh:
        json.dump(presets, fh, indent=2, ensure_ascii=False)

