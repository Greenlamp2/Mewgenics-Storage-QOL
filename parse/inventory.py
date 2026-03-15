from utils.readers import BinaryReader

class Inventory:
    def __init__(self, blob):
        self.items = []
        reader = BinaryReader(blob)
        self.count = reader.u32()
        if self.count == 0:
            return
        self.version = reader.u32()
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