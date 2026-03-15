import itertools
import struct
import sqlite3

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

class Inventory:
    def __init__(self, blob):
        reader = BinaryReader(blob)
        self.count = reader.u32()
        if self.count == 0:
            return
        self.version = reader.u32()
        self.items = []
        for i in range(self.count):
            # flag byte
            reader.skip(1)
            name = reader.str()
            subname = reader.str()
            charges = reader.i32()
            field1 = reader.u32()
            field2 = reader.u32()
            seqId = reader.u32()
            tailByte = reader.u8()
            sep_flag = None
            if i < self.count - 1:
                sep_flag = reader.u8()
                sep_val = reader.u32()
            else:
                sep_flag = reader.u8()
            self.items.append({
                'name': name,
                'subname': subname,
                'charges': charges,
                'field1': field1,
                'field2': field2,
                'seqId': seqId,
                'tailByte': tailByte,
                'sep_flag': sep_flag
            })

    def addItem(self, item):
        self.items.append(item)
        self.count += 1



def build_inventory_blob(items):
    writer = BinaryWriter()

    writer.u32(len(items))
    writer.u32(5)  # version

    for i, item in enumerate(items):

        writer.u8(1)  # flag
        writer.str(item.get('name'))
        writer.str(item.get('subName', ''))

        writer.i32(item.get('charges'))
        writer.u32(item.get('field1'))
        writer.u32(item.get('field2'))
        writer.u32(item.get('seqId'))

        writer.u8(item.get('tailByte'))

        if i < len(items) - 1:
            writer.u8(item.get('sep_flag'))
            writer.u32(5)
        else:
            writer.u8(item.get('sep_flag'))

    return writer.get()

def compare_blob(original, duplicate):
    diff = None
    for i, (a, b) in enumerate(zip(duplicate, original)):
        if a != b:
            diff = i
            break

    if diff is not None:
        start = max(0, diff - 16)
        end = diff + 16

        print("orig:", original[start:end].hex(" "))
        print("test:", duplicate[start:end].hex(" "))

    for i, (a, b) in enumerate(itertools.zip_longest(duplicate, original)):
        if a != b:
            print("diff at", i)
            return False
            break

    return True

def sql_hex_literal(data: bytes) -> str:
    return f"X'{data.hex()}'"

def is_app_up_most_to_date(path):
    conn = sqlite3.connect(path)
    storageBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_storage\'").fetchone()[1]
    storage = Inventory(storageBlob)
    blob = build_inventory_blob(storage.items)
    return compare_blob(storageBlob, blob)


def parse_all(path):
    conn = sqlite3.connect(path)
    backpackBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_backpack\'").fetchone()[1]
    storageBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_storage\'").fetchone()[1]
    trashBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_trash\'").fetchone()[1]
    storage = Inventory(storageBlob)
    backpack = Inventory(backpackBlob)
    trash = Inventory(trashBlob)
    blob = build_inventory_blob(storage.items)
    conn.execute(
        "UPDATE files SET data=? WHERE key='inventory_storage'",
        (blob,)
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if is_app_up_most_to_date('steamcampaign01.sav'):
        print("AppUpMost is up to date!")
        parse_all('steamcampaign01.sav')
    else:
        print("AppUpMost is NOT up to date!")
