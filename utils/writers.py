import struct

class BinaryWriter:
    def __init__(self):
        self.data = bytearray()
        self.pos = 0

    def u8(self, val):
        self.data += struct.pack("<B", val)
        self.pos += 1

    def u32(self, val):
        self.data += struct.pack("<I", val)
        self.pos += 4

    def i32(self, val):
        self.data += struct.pack("<i", val)
        self.pos += 4

    def u64(self, val):
        self.data += struct.pack("<Q", val)
        self.pos += 8

    def i64(self, val):
        self.data += struct.pack("<q", val)
        self.pos += 8

    def f64(self, val):
        self.data += struct.pack("<d", val)
        self.pos += 8

    def str(self, s):
        if s is None:
            s = ""
        encoded = s.encode("utf-8")
        self.u64(len(encoded))
        self.data += encoded
        self.pos += len(encoded)

    def utf16str(self, s):
        encoded = s.encode("utf-16le")
        char_count = len(encoded) // 2
        self.u64(char_count)
        self.data += encoded
        self.pos += len(encoded)

    def bytes(self, b):
        self.data += b
        self.pos += len(b)

    def skip(self, n):
        self.data += b"\x00" * n
        self.pos += n

    def get(self):
        return bytes(self.data)