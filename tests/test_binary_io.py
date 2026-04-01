"""
tests/test_binary_io.py
=======================
Unit tests for BinaryReader and BinaryWriter — no external dependencies.
"""
import math
import struct


from utils.readers import BinaryReader
from utils.writers import BinaryWriter


# ─── BinaryWriter ─────────────────────────────────────────────────────────────

class TestBinaryWriter:
    def test_u8_single(self):
        w = BinaryWriter()
        w.u8(0xAB)
        assert w.get() == bytes([0xAB])
        assert w.pos == 1

    def test_u8_range_boundaries(self):
        w = BinaryWriter()
        w.u8(0)
        w.u8(255)
        assert w.get() == bytes([0, 255])

    def test_u32_little_endian(self):
        w = BinaryWriter()
        w.u32(0x01020304)
        assert w.get() == bytes([0x04, 0x03, 0x02, 0x01])
        assert w.pos == 4

    def test_u32_zero(self):
        w = BinaryWriter()
        w.u32(0)
        assert w.get() == b"\x00\x00\x00\x00"

    def test_i32_negative(self):
        w = BinaryWriter()
        w.i32(-1)
        assert struct.unpack("<i", w.get())[0] == -1

    def test_i32_min_max(self):
        w = BinaryWriter()
        w.i32(-2**31)
        w.i32(2**31 - 1)
        data = w.get()
        assert struct.unpack_from("<i", data, 0)[0] == -2**31
        assert struct.unpack_from("<i", data, 4)[0] == 2**31 - 1

    def test_u64(self):
        w = BinaryWriter()
        v = 0xDEADBEEF_CAFEBABE
        w.u64(v)
        assert struct.unpack("<Q", w.get())[0] == v
        assert w.pos == 8

    def test_f64_round_trip(self):
        w = BinaryWriter()
        w.f64(3.14159265)
        val = struct.unpack("<d", w.get())[0]
        assert abs(val - 3.14159265) < 1e-8

    def test_f64_special_values(self):
        w = BinaryWriter()
        w.f64(0.0)
        w.f64(1.0)
        data = w.get()
        assert struct.unpack_from("<d", data, 0)[0] == 0.0
        assert struct.unpack_from("<d", data, 8)[0] == 1.0

    def test_str_empty(self):
        w = BinaryWriter()
        w.str("")
        # u64 length=0 (8 bytes) + 0 content bytes
        assert w.get() == struct.pack("<Q", 0)

    def test_str_ascii(self):
        w = BinaryWriter()
        w.str("hello")
        data = w.get()
        length = struct.unpack_from("<Q", data, 0)[0]
        assert length == 5
        assert data[8:13] == b"hello"
        assert w.pos == 13

    def test_str_none_treated_as_empty(self):
        w = BinaryWriter()
        w.str(None)
        assert w.get() == struct.pack("<Q", 0)

    def test_utf16str(self):
        w = BinaryWriter()
        w.utf16str("AB")
        data = w.get()
        char_count = struct.unpack_from("<Q", data, 0)[0]
        assert char_count == 2
        assert data[8:12] == "AB".encode("utf-16-le")

    def test_bytes_passthrough(self):
        w = BinaryWriter()
        raw = b"\x01\x02\x03"
        w.bytes(raw)
        assert w.get() == raw

    def test_skip_pads_zeros(self):
        w = BinaryWriter()
        w.skip(4)
        assert w.get() == b"\x00\x00\x00\x00"

    def test_chained_writes_position(self):
        w = BinaryWriter()
        w.u8(1)
        w.u32(2)
        w.u64(3)
        assert w.pos == 1 + 4 + 8

    def test_get_returns_bytes_not_bytearray(self):
        w = BinaryWriter()
        w.u32(0)
        assert isinstance(w.get(), bytes)


# ─── BinaryReader ─────────────────────────────────────────────────────────────

class TestBinaryReader:
    def _pack(self, fmt, *values) -> bytes:
        return struct.pack(fmt, *values)

    def test_u8(self):
        r = BinaryReader(bytes([42]))
        assert r.u8() == 42
        assert r.pos == 1

    def test_u32(self):
        data = struct.pack("<I", 0xDEADBEEF)
        r = BinaryReader(data)
        assert r.u32() == 0xDEADBEEF

    def test_i32_negative(self):
        data = struct.pack("<i", -999)
        r = BinaryReader(data)
        assert r.i32() == -999

    def test_u64(self):
        v = 0x0102030405060708
        data = struct.pack("<Q", v)
        r = BinaryReader(data)
        assert r.u64() == v

    def test_f64(self):
        data = struct.pack("<d", math.pi)
        r = BinaryReader(data)
        assert abs(r.f64() - math.pi) < 1e-12

    def test_str_round_trip(self):
        w = BinaryWriter()
        w.str("GlassShard")
        r = BinaryReader(w.get())
        assert r.str() == "GlassShard"

    def test_str_empty(self):
        w = BinaryWriter()
        w.str("")
        r = BinaryReader(w.get())
        assert r.str() == ""

    def test_utf16str_round_trip(self):
        w = BinaryWriter()
        w.utf16str("Whiskers")
        r = BinaryReader(w.get())
        assert r.utf16str() == "Whiskers"

    def test_skip(self):
        r = BinaryReader(b"\x00\x00\x00\xFF")
        r.skip(3)
        assert r.u8() == 0xFF

    def test_seek(self):
        data = struct.pack("<II", 10, 20)
        r = BinaryReader(data)
        r.seek(4)
        assert r.u32() == 20

    def test_remaining(self):
        r = BinaryReader(b"\x01\x02\x03\x04")
        assert r.remaining() == 4
        r.u8()
        assert r.remaining() == 3

    def test_str_oversized_length_returns_none(self):
        # length > 10000 should return None
        data = struct.pack("<Q", 99999)
        r = BinaryReader(data)
        assert r.str() is None
        # pos should be restored to before the call
        assert r.pos == 0


# ─── Round-trip BinaryWriter → BinaryReader ───────────────────────────────────

class TestRoundTrip:

    def test_full_item_fields_round_trip(self):
        """Simulate writing and reading back a single inventory item entry."""
        name    = "MagicSword"
        subname = ""
        charges = -1
        field1  = 42
        field2  = 0
        seq_id  = 7
        tail    = 0
        sep     = 1

        w = BinaryWriter()
        w.u8(1)           # flag
        w.str(name)
        w.str(subname)
        w.i32(charges)
        w.u32(field1)
        w.u32(field2)
        w.u32(seq_id)
        w.u8(tail)
        w.u8(sep)

        r = BinaryReader(w.get())
        assert r.u8()    == 1
        assert r.str()   == name
        assert r.str()   == subname
        assert r.i32()   == charges
        assert r.u32()   == field1
        assert r.u32()   == field2
        assert r.u32()   == seq_id
        assert r.u8()    == tail
        assert r.u8()    == sep

    def test_multiple_values_sequential(self):
        w = BinaryWriter()
        values = [0, 1, 127, 255, 1000, 2**31 - 1]
        for v in values:
            w.u32(v)

        r = BinaryReader(w.get())
        for v in values:
            assert r.u32() == v

