import struct


class BinaryWriter:
    def __init__(self):
        self._data = bytearray()

    @property
    def offset(self):
        return len(self._data)

    def bytes(self):
        return bytes(self._data)

    def write(self, data):
        self._data.extend(data)

    def write_magic(self, magic):
        if len(magic) != 4:
            raise ValueError("CMB chunk magic values must be exactly 4 bytes")
        self.write(magic)

    def write_u8(self, value):
        self.write(struct.pack("<B", value))

    def write_s8(self, value):
        self.write(struct.pack("<b", value))

    def write_u16(self, value):
        self.write(struct.pack("<H", value))

    def write_s16(self, value):
        self.write(struct.pack("<h", value))

    def write_u32(self, value):
        self.write(struct.pack("<I", value))

    def write_s32(self, value):
        self.write(struct.pack("<i", value))

    def write_f32(self, value):
        self.write(struct.pack("<f", value))

    def write_vector2(self, value):
        self.write_f32(value[0])
        self.write_f32(value[1])

    def write_vector3(self, value):
        self.write_f32(value[0])
        self.write_f32(value[1])
        self.write_f32(value[2])

    def write_vector4(self, value):
        self.write_f32(value[0])
        self.write_f32(value[1])
        self.write_f32(value[2])
        self.write_f32(value[3])

    def write_rgba8(self, value):
        self.write_u8(value[0])
        self.write_u8(value[1])
        self.write_u8(value[2])
        self.write_u8(value[3])

    def write_fixed_ascii(self, value, size):
        encoded = value.encode("ascii", errors="replace")[:size]
        self.write(encoded)
        self.write(bytes(size - len(encoded)))

    def write_padding(self, size, fill=0):
        self.write(bytes([fill]) * size)

    def align(self, alignment, fill=0):
        remainder = self.offset % alignment
        if remainder:
            self.write(bytes([fill]) * (alignment - remainder))

    def reserve_u32(self):
        offset = self.offset
        self.write_u32(0)
        return offset

    def patch_u32(self, offset, value):
        self._data[offset : offset + 4] = struct.pack("<I", value)
