"""
tests/test_cat_serializer.py
============================
Verifies that Cat.to_blob() / Cat.verify_roundtrip() produce a byte-perfect
round-trip for every cat in the live save file.

Run:
    python -m pytest tests/test_cat_serializer.py -v
  or directly:
    python tests/test_cat_serializer.py
"""

import sys
import os
import struct
import sqlite3

# Make sure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import lz4.block
import pytest

from parse.cat import Cat
from utils.loaders import (
    load_cats,
    load_house_infos,
    load_adventure_keys,
    load_current_day,
)
from utils.save_manager import TARGET_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_save_path() -> str:
    """Return the save path, skipping tests gracefully if none is found."""
    if not TARGET_PATH or not os.path.exists(TARGET_PATH):
        pytest.skip(f"Save file not found: {TARGET_PATH}")
    return TARGET_PATH


# ---------------------------------------------------------------------------
# Test 1 – Round-trip parity (byte-level) for every cat in the save
# ---------------------------------------------------------------------------

def test_roundtrip_all_cats():
    """
    For every cat blob in the save file:
      parse → Cat → to_blob() → re-parse → compare

    Passes when ALL cats round-trip losslessly (raw bytes identical, every
    parsed field equal).  Any mismatch is printed for diagnosis.
    """
    path = _load_save_path()

    house_info      = load_house_infos(path)
    adventure_keys  = load_adventure_keys(path)
    current_day     = load_current_day(path)
    raw_cats        = load_cats(path)

    assert raw_cats, "No cats found in save file — is TARGET_PATH correct?"

    failures: list[str] = []

    for cat_key, blob in raw_cats:
        ok, mismatches = Cat.verify_roundtrip(
            blob,
            cat_key,
            house_info=house_info,
            adventure_keys=adventure_keys,
            current_day=current_day,
        )
        if not ok:
            label = f"cat_key={cat_key}"
            # Try to get the name for a friendlier error message
            try:
                cat = Cat(blob, cat_key, house_info, adventure_keys, current_day)
                label += f" name={cat.name!r}"
            except Exception:
                pass
            failures.append(f"\n  [{label}]")
            for m in mismatches:
                failures.append(f"    - {m}")

    if failures:
        pytest.fail("Round-trip mismatches:\n" + "\n".join(failures))

    print(f"\n✓ {len(raw_cats)} cat(s) round-tripped losslessly.")


# ---------------------------------------------------------------------------
# Test 2 – Patch a stat, to_blob(), re-parse: the new value must be visible
# ---------------------------------------------------------------------------

def test_patch_stat_survives_roundtrip():
    """
    Modify stat_base[0] (STR) on one cat, call to_blob(), re-parse and verify
    the new value is preserved.  The other fields must remain untouched.
    """
    path = _load_save_path()

    house_info     = load_house_infos(path)
    adventure_keys = load_adventure_keys(path)
    current_day    = load_current_day(path)
    raw_cats       = load_cats(path)

    assert raw_cats, "No cats found in save file."

    cat_key, blob = raw_cats[0]
    cat = Cat(blob, cat_key, house_info, adventure_keys, current_day)

    original_str = cat.stat_base[0]
    new_str = (original_str + 5) % 100  # ensure a change, keep it plausible

    cat.stat_base[0] = new_str
    new_blob = cat.to_blob()

    # Re-parse the patched blob
    cat2 = Cat(new_blob, cat_key, house_info, adventure_keys, current_day)

    assert cat2.stat_base[0] == new_str, (
        f"Patched STR not preserved: expected {new_str}, got {cat2.stat_base[0]}"
    )
    # All other stats must be unchanged
    assert cat2.stat_base[1:] == cat.stat_base[1:], "Other stat_base values changed unexpectedly"
    assert cat2.stat_mod == cat.stat_mod, "stat_mod changed unexpectedly"
    assert cat2.stat_sec == cat.stat_sec, "stat_sec changed unexpectedly"

    print(
        f"\n✓ STR patch: {original_str} → {new_str} "
        f"(cat_key={cat_key}, name={cat.name!r})"
    )


# ---------------------------------------------------------------------------
# Test 3 – to_blob() output is a valid LZ4 blob the game format expects
# ---------------------------------------------------------------------------

def test_blob_header_format():
    """
    Verify that to_blob() produces a blob whose first 4 bytes are the correct
    little-endian uncompressed size and that it decompresses without error.
    """
    path = _load_save_path()

    house_info     = load_house_infos(path)
    adventure_keys = load_adventure_keys(path)
    current_day    = load_current_day(path)
    raw_cats       = load_cats(path)

    assert raw_cats, "No cats found in save file."

    cat_key, blob = raw_cats[0]
    cat = Cat(blob, cat_key, house_info, adventure_keys, current_day)
    new_blob = cat.to_blob()

    # The header must be a valid u32 LE uncompressed size
    assert len(new_blob) >= 4, "Blob too short to contain header"
    uncomp_size = struct.unpack('<I', new_blob[:4])[0]
    assert uncomp_size > 0, f"Uncompressed size is 0"

    # The payload must decompress cleanly to exactly uncomp_size bytes
    raw = lz4.block.decompress(new_blob[4:], uncompressed_size=uncomp_size)
    assert len(raw) == uncomp_size, (
        f"Decompressed size mismatch: header says {uncomp_size}, got {len(raw)}"
    )
    assert raw == cat._raw, "Decompressed blob differs from original _raw"

    print(
        f"\n✓ Blob header OK: uncompressed={uncomp_size} bytes, "
        f"compressed={len(new_blob) - 4} bytes"
    )


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Cat serializer round-trip tests")
    print("=" * 60)

    passed = 0
    failed = 0

    tests = [
        ("Round-trip all cats",        test_roundtrip_all_cats),
        ("Patch stat survives",         test_patch_stat_survives_roundtrip),
        ("Blob header format",          test_blob_header_format),
    ]

    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            print(f"  PASSED")
            passed += 1
        except Exception as exc:
            print(f"  FAILED: {exc}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(1 if failed else 0)

