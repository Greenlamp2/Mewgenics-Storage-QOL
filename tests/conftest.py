"""
tests/conftest.py
=================
Pytest fixtures shared across the test suite.
Pure helpers (make_raw, build_blob, …) live in tests/helpers.py.
"""
import sys
import os

import pytest

# Ensure the project root is on sys.path so project modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.helpers import (  # noqa: E402
    MOCK_ITEM_DETAILS,
    MOCK_RARE_DETAILS,
    MOCK_UNCOMMON_DETAILS,
    MOCK_VERY_RARE_DETAILS,
    make_raw,
    build_blob,
    setup_save_db,
    add_item_to_inv,
)


# ─── Catalog mock ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_item_catalog(monkeypatch):
    """Replace item_catalog with a lightweight stub (no data files needed)."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.is_quest_item.return_value = False
    mock.get_category.return_value = "weapons"
    mock.get_item_full.return_value = dict(MOCK_ITEM_DETAILS)
    mock.get_item_ability.return_value = None
    mock.solve_icon_name.side_effect = lambda n: f"ITEM_{n}.svg"
    mock.get_price.return_value = "14"
    mock.get_armor_set_data.return_value = None
    mock.get_set_bonus.return_value = None
    mock.get_all_non_quest_items.return_value = {
        "TestItem":     dict(MOCK_ITEM_DETAILS),
        "RareItem":     dict(MOCK_RARE_DETAILS),
        "UncommonItem": dict(MOCK_UNCOMMON_DETAILS),
        "VeryRareItem": dict(MOCK_VERY_RARE_DETAILS),
    }

    monkeypatch.setattr("parse.item.item_catalog",    mock)
    monkeypatch.setattr("app_controller.item_catalog", mock)
    return mock


# ─── Temp save-file fixture ───────────────────────────────────────────────────

@pytest.fixture
def tmp_save(tmp_path):
    """Path to a minimal valid save SQLite database (empty inventories)."""
    db = str(tmp_path / "test.sav")
    setup_save_db(db)
    return db


# ─── Temp items-pool path ─────────────────────────────────────────────────────

@pytest.fixture
def tmp_items_pool(tmp_path, monkeypatch):
    """Redirect items_pool.json reads/writes to a temp file."""
    pool_path = str(tmp_path / "items_pool.json")
    monkeypatch.setattr("utils.loaders.ITEMS_POOL_PATH", pool_path)
    monkeypatch.setattr("utils.savers.ITEMS_POOL_PATH",  pool_path)
    return pool_path


# ─── Ready-made AppController ─────────────────────────────────────────────────

@pytest.fixture
def controller(tmp_save, tmp_items_pool, mock_item_catalog):
    """AppController backed by an empty temp save, catalog mocked."""
    from app_controller import AppController
    ctrl = AppController(tmp_save)
    ctrl.load_data()
    return ctrl

