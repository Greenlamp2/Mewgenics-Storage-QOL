import struct

class BinaryReader:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def u8(self):
        val = self.data[self.pos]
        self.pos += 1
        return val

    def u32(self):
        val = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return val

    def i32(self):
        val = struct.unpack_from('<i', self.data, self.pos)[0]
        self.pos += 4
        return val

    def u64(self):
        low, high = struct.unpack_from('<II', self.data, self.pos)
        self.pos += 8
        return low + (high * 4294967296)

    def i64(self):
        low, high = struct.unpack_from('<Ii', self.data, self.pos)
        self.pos += 8
        return low + (high * 4294967296)

    def f64(self):
        val = struct.unpack_from('<d', self.data, self.pos)[0]
        self.pos += 8
        return val

    def str(self):
        start = self.pos
        try:
            length = self.u64()
            if length > 10000 or length < 0: return None
            res = self.data[self.pos: self.pos + int(length)].decode('utf-8', errors='ignore')
            self.pos += int(length)
            return res
        except:
            self.pos = start
            return None

    def utf16str(self):
        char_count = self.u64()
        byte_len = int(char_count * 2)
        res = self.data[self.pos: self.pos + byte_len].decode('utf-16le', errors='ignore')
        self.pos += byte_len
        return res

    def skip(self, n):
        self.pos += n

    def seek(self, n):
        self.pos = n

    def remaining(self):
        return len(self.data) - self.pos
