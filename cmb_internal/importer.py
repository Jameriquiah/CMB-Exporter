from dataclasses import dataclass
from pathlib import Path
import struct

import bpy
from bpy_extras.io_utils import ImportHelper
from math import radians
from mathutils import Euler, Matrix, Vector

from .cmb_constants import (
    CMB_MAGIC,
    CMB_VERSION_OOT3D,
    MATS_MAGIC,
    MSHS_MAGIC,
    PicaDataType,
    PicaTextureFormat,
    SEPD_MAGIC,
    SHP_MAGIC,
    SKL_MAGIC,
    SKLM_MAGIC,
    TEX_MAGIC,
    VATR_MAGIC,
    BlendEquation,
    BlendFactor,
    TestFunction,
    TextureMagFilter,
    TextureMinFilter,
    TextureWrapMode,
)
from .material_presets import apply_stages_to_settings
from .texture_slots import texture_slot_attr
from .viewport import sync_cmb_material_preview


MATERIAL_RECORD_SIZE = 0x15C
SEPD_FLAGS_HAS_COLORS = 0x04
SEPD_FLAGS_HAS_UV0 = 0x08
SEPD_FLAGS_HAS_UV1 = 0x10
SEPD_FLAGS_HAS_UV2 = 0x20
SEPD_FLAGS_HAS_INDICES = 0x40
SEPD_FLAGS_HAS_WEIGHTS = 0x80
IMPORT_ROTATION_EULER = (radians(90.0), 0.0, 0.0)
IMPORT_MESH_DATA_CORRECTION = Matrix.Rotation(radians(-90.0), 4, "X")
ETC_MODIFIER_TABLES = (
    (2, 8, -2, -8),
    (5, 17, -5, -17),
    (9, 29, -9, -29),
    (13, 42, -13, -42),
    (18, 60, -18, -60),
    (24, 80, -24, -80),
    (33, 106, -33, -106),
    (47, 183, -47, -183),
)


class CmbImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedBone:
    index: int
    parent_index: int
    scale: tuple[float, float, float]
    rotation: tuple[float, float, float]
    translation: tuple[float, float, float]


@dataclass(frozen=True)
class ParsedTexture:
    name: str
    width: int
    height: int
    texture_format: str
    data_offset: int
    data_size: int


@dataclass(frozen=True)
class VertexList:
    offset: int
    scale: float
    data_type: int
    mode: int
    constant: tuple[float, float, float, float]


@dataclass(frozen=True)
class VatrStream:
    size: int
    offset: int


@dataclass(frozen=True)
class Prms:
    palette: tuple[int, ...]
    skinning_mode: int
    indices: tuple[int, ...]


@dataclass(frozen=True)
class Shape:
    flags: int
    vertex_lists: tuple[VertexList, ...]
    bone_dimension: int
    prms: tuple[Prms, ...]


@dataclass(frozen=True)
class MeshEntry:
    shape_index: int
    material_index: int
    visibility_id: int


class Reader:
    def __init__(self, data):
        self.data = data

    def _unpack(self, fmt, offset):
        size = struct.calcsize(fmt)
        if offset + size > len(self.data):
            raise CmbImportError("Unexpected end of CMB data")
        values = struct.unpack_from(fmt, self.data, offset)
        return values[0] if len(values) == 1 else values

    def bytes(self, offset, size):
        if offset + size > len(self.data):
            raise CmbImportError("Unexpected end of CMB data")
        return self.data[offset : offset + size]

    def magic(self, offset):
        return self.bytes(offset, 4)

    def u8(self, offset):
        return self._unpack("<B", offset)

    def s8(self, offset):
        return self._unpack("<b", offset)

    def u16(self, offset):
        return self._unpack("<H", offset)

    def s16(self, offset):
        return self._unpack("<h", offset)

    def u32(self, offset):
        return self._unpack("<I", offset)

    def f32(self, offset):
        return self._unpack("<f", offset)

    def vec2(self, offset):
        return self.f32(offset), self.f32(offset + 4)

    def vec3(self, offset):
        return self.f32(offset), self.f32(offset + 4), self.f32(offset + 8)

    def vec4(self, offset):
        return self.f32(offset), self.f32(offset + 4), self.f32(offset + 8), self.f32(offset + 12)

    def rgba8(self, offset):
        return self.u8(offset), self.u8(offset + 1), self.u8(offset + 2), self.u8(offset + 3)

    def fixed_ascii(self, offset, size):
        raw = self.bytes(offset, size).split(b"\0", 1)[0]
        return raw.decode("ascii", errors="replace")


def _enum_name(enum_type, value, default):
    try:
        return enum_type(value).name
    except ValueError:
        return default


def _rgba8_to_float(color):
    return tuple(channel / 255.0 for channel in color)


def _texture_format_name(pica_format, data_type, is_etc1):
    if pica_format == PicaTextureFormat.ETC1_RGB8_NATIVE_DMP:
        return "ETC1"
    if pica_format == PicaTextureFormat.ETC1_ALPHA_RGB8_A4_NATIVE_DMP:
        return "ETC1A4"
    if pica_format == PicaTextureFormat.RGB_NATIVE_DMP and data_type == PicaDataType.UNSIGNED_SHORT_565:
        return "RGB565"
    if pica_format == PicaTextureFormat.RGBA_NATIVE_DMP and data_type == PicaDataType.UNSIGNED_SHORT_5551:
        return "RGBA5551"
    if pica_format == PicaTextureFormat.LUMINANCE_ALPHA_NATIVE_DMP and data_type == PicaDataType.UNSIGNED_BYTE_44_DMP:
        return "LA4"
    if pica_format == PicaTextureFormat.LUMINANCE_ALPHA_NATIVE_DMP and data_type == PicaDataType.U8:
        return "LA8"
    if pica_format == PicaTextureFormat.LUMINANCE_NATIVE_DMP and data_type == PicaDataType.UNSIGNED_4_BITS_DMP:
        return "L4"
    if pica_format == PicaTextureFormat.LUMINANCE_NATIVE_DMP and data_type == PicaDataType.U8:
        return "L8"
    if pica_format == PicaTextureFormat.ALPHA_NATIVE_DMP and data_type == PicaDataType.U8:
        return "A8"
    return "ETC1A4" if is_etc1 else "RGB565"


def _morton_index_8x8(x, y):
    return (
        ((x & 1) << 0)
        | ((y & 1) << 1)
        | ((x & 2) << 1)
        | ((y & 2) << 2)
        | ((x & 4) << 2)
        | ((y & 4) << 3)
    )


def _tile_order(width, height):
    tile_size = 8
    padded_width = ((width + tile_size - 1) // tile_size) * tile_size
    padded_height = ((height + tile_size - 1) // tile_size) * tile_size
    for tile_y in range(0, padded_height, tile_size):
        for tile_x in range(0, padded_width, tile_size):
            coords = []
            for y in range(tile_size):
                for x in range(tile_size):
                    coords.append((_morton_index_8x8(x, y), tile_x + x, tile_y + y))
            for _order, x, y in sorted(coords):
                yield x, y


def _etc_block_order(width, height):
    block_size = 4
    tile_size = 8
    padded_width = ((width + tile_size - 1) // tile_size) * tile_size
    padded_height = ((height + tile_size - 1) // tile_size) * tile_size
    block_offsets = (
        (0, 0),
        (block_size, 0),
        (0, block_size),
        (block_size, block_size),
    )
    for tile_y in range(0, padded_height, tile_size):
        for tile_x in range(0, padded_width, tile_size):
            for offset_x, offset_y in block_offsets:
                yield tile_x + offset_x, tile_y + offset_y


def _u8_to_float(value):
    return value / 255.0


def _expand_bits(value, bits):
    max_value = (1 << bits) - 1
    return round((value / max_value) * 255)


def _decode_texture_pixel(data, offset, texture_format):
    if texture_format == "RGB565":
        value = data[offset] | (data[offset + 1] << 8)
        return (
            _u8_to_float(_expand_bits((value >> 11) & 0x1F, 5)),
            _u8_to_float(_expand_bits((value >> 5) & 0x3F, 6)),
            _u8_to_float(_expand_bits(value & 0x1F, 5)),
            1.0,
            offset + 2,
        )
    if texture_format == "RGBA5551":
        value = data[offset] | (data[offset + 1] << 8)
        return (
            _u8_to_float(_expand_bits((value >> 11) & 0x1F, 5)),
            _u8_to_float(_expand_bits((value >> 6) & 0x1F, 5)),
            _u8_to_float(_expand_bits((value >> 1) & 0x1F, 5)),
            1.0 if value & 1 else 0.0,
            offset + 2,
        )
    if texture_format == "LA4":
        value = data[offset]
        luminance = _u8_to_float(_expand_bits(value & 0xF, 4))
        alpha = _u8_to_float(_expand_bits((value >> 4) & 0xF, 4))
        return luminance, luminance, luminance, alpha, offset + 1
    if texture_format == "LA8":
        alpha = data[offset]
        luminance = data[offset + 1]
        return _u8_to_float(luminance), _u8_to_float(luminance), _u8_to_float(luminance), _u8_to_float(alpha), offset + 2
    if texture_format == "L8":
        luminance = _u8_to_float(data[offset])
        return luminance, luminance, luminance, 1.0, offset + 1
    if texture_format == "A8":
        alpha = _u8_to_float(data[offset])
        return 1.0, 1.0, 1.0, alpha, offset + 1
    raise CmbImportError(f"Texture format {texture_format} cannot be decoded yet")


def _decode_l4_texture(data, width, height):
    pixels = [(0.0, 0.0, 0.0, 0.0)] * (width * height)
    offset = 0
    high_nibble = False
    current_byte = 0
    for x, y in _tile_order(width, height):
        if not high_nibble:
            if offset >= len(data):
                break
            current_byte = data[offset]
            offset += 1
            value = current_byte & 0xF
            high_nibble = True
        else:
            value = (current_byte >> 4) & 0xF
            high_nibble = False
        if x < width and y < height:
            luminance = _u8_to_float(_expand_bits(value, 4))
            pixels[y * width + x] = (luminance, luminance, luminance, 1.0)
    return pixels


def _clamp_u8(value):
    return max(0, min(255, int(value)))


def _expand4(value):
    return (value << 4) | value


def _expand5(value):
    return (value << 3) | (value >> 2)


def _signed_etc_delta(value):
    return value - 8 if value & 0x4 else value


def _etc_pixel_index(x, y):
    return x * 4 + y


def _decode_etc_color_block(block):
    value = int.from_bytes(block, "little")
    high = (value >> 32) & 0xFFFFFFFF
    low = value & 0xFFFFFFFF
    flip = bool(high & 1)
    differential = bool((high >> 1) & 1)
    table1 = (high >> 5) & 0x7
    table2 = (high >> 2) & 0x7

    if differential:
        red1 = (high >> 27) & 0x1F
        green1 = (high >> 19) & 0x1F
        blue1 = (high >> 11) & 0x1F
        red_delta = _signed_etc_delta((high >> 24) & 0x7)
        green_delta = _signed_etc_delta((high >> 16) & 0x7)
        blue_delta = _signed_etc_delta((high >> 8) & 0x7)
        colors = (
            (_expand5(red1), _expand5(green1), _expand5(blue1)),
            (_expand5(red1 + red_delta), _expand5(green1 + green_delta), _expand5(blue1 + blue_delta)),
        )
    else:
        colors = (
            (_expand4((high >> 28) & 0xF), _expand4((high >> 20) & 0xF), _expand4((high >> 12) & 0xF)),
            (_expand4((high >> 24) & 0xF), _expand4((high >> 16) & 0xF), _expand4((high >> 8) & 0xF)),
        )

    decoded = []
    for y in range(4):
        row = []
        for x in range(4):
            index = _etc_pixel_index(x, y)
            selector = ((low >> index) & 1) | (((low >> (index + 16)) & 1) << 1)
            subblock = y >= 2 if flip else x >= 2
            red, green, blue = colors[1 if subblock else 0]
            modifier = ETC_MODIFIER_TABLES[table2 if subblock else table1][selector]
            row.append((
                _clamp_u8(red + modifier),
                _clamp_u8(green + modifier),
                _clamp_u8(blue + modifier),
            ))
        decoded.append(tuple(row))
    return tuple(decoded)


def _decode_etc_alpha_block(block):
    value = int.from_bytes(block, "little")
    decoded = []
    for y in range(4):
        row = []
        for x in range(4):
            alpha4 = (value >> (_etc_pixel_index(x, y) * 4)) & 0xF
            row.append(_expand4(alpha4))
        decoded.append(tuple(row))
    return tuple(decoded)


def _decode_etc_texture(data, texture):
    pixels = [(0.0, 0.0, 0.0, 0.0)] * (texture.width * texture.height)
    offset = 0
    has_alpha = texture.texture_format == "ETC1A4"
    for block_x, block_y in _etc_block_order(texture.width, texture.height):
        alpha_block = None
        if has_alpha:
            if offset + 8 > len(data):
                break
            alpha_block = _decode_etc_alpha_block(data[offset : offset + 8])
            offset += 8
        if offset + 8 > len(data):
            break
        color_block = _decode_etc_color_block(data[offset : offset + 8])
        offset += 8
        for y in range(4):
            for x in range(4):
                pixel_x = block_x + x
                pixel_y = block_y + y
                if pixel_x >= texture.width or pixel_y >= texture.height:
                    continue
                red, green, blue = color_block[y][x]
                alpha = alpha_block[y][x] if alpha_block is not None else 255
                pixels[pixel_y * texture.width + pixel_x] = (
                    _u8_to_float(red),
                    _u8_to_float(green),
                    _u8_to_float(blue),
                    _u8_to_float(alpha),
                )
    return pixels


def _decode_texture_pixels(data, texture):
    if texture.texture_format in {"ETC1", "ETC1A4"}:
        return _decode_etc_texture(data, texture)
    if texture.texture_format == "L4":
        return _decode_l4_texture(data, texture.width, texture.height)

    pixels = [(0.0, 0.0, 0.0, 0.0)] * (texture.width * texture.height)
    offset = 0
    for x, y in _tile_order(texture.width, texture.height):
        red, green, blue, alpha, offset = _decode_texture_pixel(data, offset, texture.texture_format)
        if x < texture.width and y < texture.height:
            pixels[y * texture.width + x] = (red, green, blue, alpha)
    return pixels


def _flip_pixels_for_blender(pixels, width, height):
    return [
        channel
        for y in range(height - 1, -1, -1)
        for pixel in pixels[y * width : (y + 1) * width]
        for channel in pixel
    ]


def _coord_mapping_name(value):
    return {0: "NONE", 1: "UV", 3: "REFLECTION"}.get(value, "NONE")


def _culling_name(value):
    return {0: "FRONT_AND_BACK", 1: "BACK", 2: "FRONT", 3: "NONE"}.get(value, "BACK")


def _blend_mode_name(value, color_src, color_dst):
    if value == 0:
        return "OPAQUE"
    if color_src == BlendFactor.SRC_ALPHA and color_dst == BlendFactor.ONE:
        return "ADD"
    return "ALPHA"


def _read_header(reader):
    if reader.magic(0) != CMB_MAGIC:
        raise CmbImportError("File is not a CMB")
    version = reader.u32(8)
    if version != CMB_VERSION_OOT3D:
        raise CmbImportError(f"Unsupported CMB version: {version:#x}")
    name = reader.fixed_ascii(0x10, 16) or "cmb_model"
    return name, {
        "skl": reader.u32(0x24),
        "mats": reader.u32(0x28),
        "tex": reader.u32(0x2C),
        "sklm": reader.u32(0x30),
        "luts": reader.u32(0x34),
        "vatr": reader.u32(0x38),
        "indices": reader.u32(0x3C),
        "textures": reader.u32(0x40),
    }


def _check_magic(reader, offset, magic):
    if offset <= 0 or reader.magic(offset) != magic:
        raise CmbImportError(f"Missing CMB section {magic!r}")


def _read_bones(reader, skl_offset):
    _check_magic(reader, skl_offset, SKL_MAGIC)
    count = reader.u32(skl_offset + 8)
    offset = skl_offset + 16
    bones = []
    for _ in range(count):
        bones.append(
            ParsedBone(
                index=reader.s16(offset),
                parent_index=reader.s16(offset + 2),
                scale=reader.vec3(offset + 4),
                rotation=reader.vec3(offset + 16),
                translation=reader.vec3(offset + 28),
            )
        )
        offset += 40
    return tuple(bones)


def _read_textures(reader, tex_offset):
    if tex_offset <= 0:
        return ()
    _check_magic(reader, tex_offset, TEX_MAGIC)
    count = reader.u32(tex_offset + 8)
    offset = tex_offset + 12
    textures = []
    for _ in range(count):
        is_etc1 = reader.u8(offset + 6)
        width = reader.u16(offset + 8)
        height = reader.u16(offset + 10)
        pica_format = reader.u16(offset + 12)
        data_type = reader.u16(offset + 14)
        textures.append(
            ParsedTexture(
                name=reader.fixed_ascii(offset + 20, 16) or "texture",
                width=width,
                height=height,
                texture_format=_texture_format_name(pica_format, data_type, is_etc1),
                data_offset=reader.u32(offset + 16),
                data_size=reader.u32(offset),
            )
        )
        offset += 36
    return tuple(textures)


def _read_mat_texture(reader, offset):
    return {
        "index": reader.s16(offset),
        "min_filter": _enum_name(TextureMinFilter, reader.u16(offset + 4), "LINEAR"),
        "mag_filter": _enum_name(TextureMagFilter, reader.u16(offset + 6), "LINEAR"),
        "wrap_u": _enum_name(TextureWrapMode, reader.u16(offset + 8), "REPEAT"),
        "wrap_v": _enum_name(TextureWrapMode, reader.u16(offset + 10), "REPEAT"),
    }


def _read_texture_coord(reader, offset):
    return {
        "coord_matrix_mode": reader.u8(offset),
        "coord_reference_camera": reader.u8(offset + 1),
        "coord_mapping": _coord_mapping_name(reader.u8(offset + 2)),
        "coord_source": reader.u8(offset + 3),
        "coord_scale": reader.vec2(offset + 4),
        "coord_rotation": reader.f32(offset + 12),
        "coord_translation": reader.vec2(offset + 16),
    }


def _read_env_stages(reader, mats_offset, material_count, env_end_offset):
    env_offset = mats_offset + 12 + material_count * MATERIAL_RECORD_SIZE
    env_count = (env_end_offset - env_offset) // 40
    stages = []
    for index in range(max(0, env_count)):
        offset = env_offset + index * 40
        stages.append(tuple(reader.u16(offset + word_index * 2) for word_index in range(20)))
    return tuple(stages)


def _read_materials(reader, mats_offset, tex_offset, textures, texture_data_offset):
    _check_magic(reader, mats_offset, MATS_MAGIC)
    count = reader.u32(mats_offset + 8)
    env_stages = _read_env_stages(reader, mats_offset, count, tex_offset)
    materials = []
    for material_index in range(count):
        start = mats_offset + 12 + material_index * MATERIAL_RECORD_SIZE
        offset = start
        data = {
            "fragment_lighting": bool(reader.u8(offset)),
            "vertex_lighting": bool(reader.u8(offset + 1)),
            "is_fog_enabled": bool(reader.u8(offset + 2)),
            "render_layer": reader.u8(offset + 3),
            "face_culling": _culling_name(reader.u8(offset + 4)),
            "polygon_offset_enabled": bool(reader.u8(offset + 5)),
            "polygon_offset": reader.u16(offset + 6),
        }
        offset += 16

        mat_textures = tuple(_read_mat_texture(reader, offset + slot * 24) for slot in range(3))
        offset += 72
        coords = tuple(_read_texture_coord(reader, offset + slot * 24) for slot in range(3))
        offset += 72

        data["emission_color"] = _rgba8_to_float(reader.rgba8(offset))
        data["ambient_color"] = _rgba8_to_float(reader.rgba8(offset + 4))
        data["diffuse_color"] = _rgba8_to_float(reader.rgba8(offset + 8))
        data["specular0_color"] = _rgba8_to_float(reader.rgba8(offset + 12))
        data["specular1_color"] = _rgba8_to_float(reader.rgba8(offset + 16))
        offset += 20

        for color_index in range(6):
            data[f"constant{color_index}_color"] = _rgba8_to_float(reader.rgba8(offset + color_index * 4))
        offset += 24
        data["buffer_color"] = reader.vec4(offset)
        offset += 16 + 14 + 6 + 48

        stage_count = reader.u32(offset)
        stage_indices = tuple(reader.s16(offset + 4 + index * 2) for index in range(6))
        offset += 16

        data["alpha_test_enabled"] = bool(reader.u8(offset))
        data["alpha_reference"] = reader.u8(offset + 1)
        data["alpha_function"] = _enum_name(TestFunction, reader.u16(offset + 2), "ALWAYS")
        data["depth_test_enabled"] = bool(reader.u8(offset + 4))
        data["depth_write_enabled"] = bool(reader.u8(offset + 5))
        data["depth_function"] = _enum_name(TestFunction, reader.u16(offset + 6), "LEQUAL")
        blend_value = reader.u32(offset + 8)
        alpha_src = reader.u16(offset + 12)
        alpha_dst = reader.u16(offset + 14)
        alpha_equation = reader.u32(offset + 16)
        color_src = reader.u16(offset + 20)
        color_dst = reader.u16(offset + 22)
        color_equation = reader.u32(offset + 24)
        data["blend_mode"] = _blend_mode_name(blend_value, color_src, color_dst)
        data["blend_alpha_src_function"] = _enum_name(BlendFactor, alpha_src, "SRC_ALPHA")
        data["blend_alpha_dst_function"] = _enum_name(BlendFactor, alpha_dst, "ONE_MINUS_SRC_ALPHA")
        data["blend_alpha_equation"] = _enum_name(BlendEquation, alpha_equation, "FUNC_ADD")
        data["blend_color_src_function"] = _enum_name(BlendFactor, color_src, "ONE")
        data["blend_color_dst_function"] = _enum_name(BlendFactor, color_dst, "ZERO")
        data["blend_color_equation"] = _enum_name(BlendEquation, color_equation, "FUNC_ADD")
        data["blend_color"] = reader.vec4(offset + 28)

        material = bpy.data.materials.new(f"{material_index:02d}_CMBMaterial")
        material.use_nodes = False
        settings = material.cmb_settings
        settings.material_type = "CMB"
        settings.enabled = True
        for key, value in data.items():
            setattr(settings, key, value)
        material.diffuse_color = data["diffuse_color"]

        for slot_index, (texture, coord) in enumerate(zip(mat_textures, coords)):
            prefix = texture_slot_attr(slot_index, "")
            texture_index = texture["index"]
            image = None
            texture_format = "RGB565"
            if 0 <= texture_index < len(textures):
                texture_info = textures[texture_index]
                image = _image_for_texture(reader, texture_data_offset, texture_info)
                texture_format = texture_info.texture_format
            setattr(settings, f"{prefix}image", image)
            setattr(settings, f"{prefix}format", texture_format)
            for key in ("min_filter", "mag_filter", "wrap_u", "wrap_v"):
                setattr(settings, f"{prefix}{key}", texture[key])
            for key, value in coord.items():
                setattr(settings, f"{prefix}{key}", value if image is not None else ("NONE" if key == "coord_mapping" else value))

        stages = tuple(env_stages[index] for index in stage_indices[:stage_count] if 0 <= index < len(env_stages))
        if stages:
            apply_stages_to_settings(settings, stages)
        sync_cmb_material_preview(material, force=True)
        materials.append(material)
    return tuple(materials)


def _image_for_texture(reader, texture_data_offset, texture):
    existing = bpy.data.images.get(texture.name)
    if existing is not None and tuple(existing.size) == (texture.width, texture.height):
        return existing
    image = bpy.data.images.new(texture.name, max(1, texture.width), max(1, texture.height), alpha=True)
    texture_data = reader.bytes(texture_data_offset + texture.data_offset, texture.data_size)
    pixels = _decode_texture_pixels(texture_data, texture)
    if pixels is not None:
        image.pixels.foreach_set(_flip_pixels_for_blender(pixels, texture.width, texture.height))
        image.pack()
    else:
        image.generated_color = (0.5, 0.5, 0.5, 1.0)
    image["cmb_imported_texture_format"] = texture.texture_format
    return image


def _read_vertex_list(reader, offset):
    return VertexList(
        offset=reader.u32(offset),
        scale=reader.f32(offset + 4),
        data_type=reader.u16(offset + 8),
        mode=reader.u16(offset + 10),
        constant=reader.vec4(offset + 12),
    )


def _read_vatr_streams(reader, vatr_offset):
    _check_magic(reader, vatr_offset, VATR_MAGIC)
    return tuple(
        VatrStream(
            size=reader.u32(vatr_offset + 12 + index * 8),
            offset=reader.u32(vatr_offset + 16 + index * 8),
        )
        for index in range(8)
    )


def _read_prms(reader, offset, index_buffer_offset):
    if reader.magic(offset) != b"prms":
        raise CmbImportError("Missing PRMS section")
    palette_info = reader.u32(offset + 12)
    skinning_mode = palette_info & 0xFFFF
    palette_count = palette_info >> 16
    prm_rel = reader.u32(offset + 20)
    palette = []
    for packed_index in range((palette_count + 1) // 2):
        packed = reader.u32(offset + 24 + packed_index * 4)
        palette.append(packed & 0xFFFF)
        if len(palette) < palette_count:
            palette.append((packed >> 16) & 0xFFFF)

    prm_offset = offset + prm_rel
    if reader.magic(prm_offset) != b"prm ":
        raise CmbImportError("Missing PRM section")
    index_count = reader.u16(prm_offset + 20)
    index_start = reader.u16(prm_offset + 22)
    indices = tuple(reader.u16(index_buffer_offset + (index_start + index) * 2) for index in range(index_count))
    return Prms(tuple(palette), skinning_mode, indices)


def _read_shapes(reader, shp_offset, index_buffer_offset):
    _check_magic(reader, shp_offset, SHP_MAGIC)
    count = reader.u32(shp_offset + 8)
    offsets = tuple(reader.u16(shp_offset + 16 + index * 2) for index in range(count))
    shapes = []
    for rel_offset in offsets:
        sepd_offset = shp_offset + rel_offset
        if reader.magic(sepd_offset) != SEPD_MAGIC:
            raise CmbImportError("Missing SEPD section")
        prms_count = reader.u16(sepd_offset + 8)
        flags = reader.u16(sepd_offset + 10)
        vertex_lists = tuple(_read_vertex_list(reader, sepd_offset + 36 + index * 28) for index in range(8))
        bone_dimension = reader.u16(sepd_offset + 260)
        prms_offsets_start = sepd_offset + 264
        prms_offsets = tuple(reader.u16(prms_offsets_start + index * 2) for index in range(prms_count))
        prms = tuple(_read_prms(reader, sepd_offset + rel, index_buffer_offset) for rel in prms_offsets)
        shapes.append(Shape(flags, vertex_lists, bone_dimension, prms))
    return tuple(shapes)


def _read_mesh_entries(reader, sklm_offset):
    _check_magic(reader, sklm_offset, SKLM_MAGIC)
    mshs_offset = sklm_offset + reader.u32(sklm_offset + 8)
    shp_offset = sklm_offset + reader.u32(sklm_offset + 12)
    _check_magic(reader, mshs_offset, MSHS_MAGIC)
    count = reader.u32(mshs_offset + 8)
    entries = []
    offset = mshs_offset + 16
    for _ in range(count):
        entries.append(MeshEntry(reader.u16(offset), reader.u8(offset + 2), reader.u8(offset + 3)))
        offset += 4
    return tuple(entries), shp_offset


def _local_matrix(bone):
    return Matrix.LocRotScale(Vector(bone.translation), Euler(bone.rotation, "XYZ"), Vector(bone.scale))


def _create_armature(name, bones):
    armature_data = bpy.data.armatures.new(f"{name}_Armature")
    armature_obj = bpy.data.objects.new(name, armature_data)
    bpy.context.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    matrices = []
    children_by_parent = {bone.index: [] for bone in bones}
    edit_bones = []
    for bone in bones:
        parent_matrix = matrices[bone.parent_index] if bone.parent_index >= 0 else Matrix.Identity(4)
        matrix = parent_matrix @ _local_matrix(bone)
        matrices.append(matrix)
        if bone.parent_index >= 0:
            children_by_parent.setdefault(bone.parent_index, []).append(bone.index)

    heads = tuple(matrix.translation.copy() for matrix in matrices)

    for bone in bones:
        edit_bone = armature_data.edit_bones.new(f"Bone_{bone.index:03d}")
        head = heads[bone.index]
        child_indices = children_by_parent.get(bone.index, ())
        length = 0.1
        if child_indices:
            length = (heads[child_indices[0]] - head).length
        if length < 0.001:
            length = 0.1
        orientation = matrices[bone.index].to_3x3()
        tail_direction = orientation @ Vector((0.0, 1.0, 0.0))
        if tail_direction.length < 0.001:
            tail_direction = Vector((0.0, 1.0, 0.0))
        tail_direction.normalize()
        roll_axis = orientation @ Vector((0.0, 0.0, 1.0))
        tail = head + tail_direction * length
        edit_bone.head = head
        edit_bone.tail = tail
        if roll_axis.length > 0.001:
            edit_bone.align_roll(roll_axis)
        if bone.parent_index >= 0:
            edit_bone.parent = edit_bones[bone.parent_index]
        edit_bones.append(edit_bone)

    bpy.ops.object.mode_set(mode="OBJECT")
    armature_obj.rotation_euler = IMPORT_ROTATION_EULER
    armature_obj.scale = (0.01, 0.01, 0.01)
    return armature_obj, tuple(bone.name for bone in armature_data.bones), tuple(matrices)


def _shape_vertex_count(shape):
    highest = -1
    for prms in shape.prms:
        if prms.indices:
            highest = max(highest, max(prms.indices))
    return highest + 1


def _read_position(reader, offset, index):
    base = offset + index * 12
    return reader.vec3(base)


def _read_normal(reader, offset, index, scale):
    base = offset + index * 3
    return reader.s8(base) * scale, reader.s8(base + 1) * scale, reader.s8(base + 2) * scale


def _read_uv(reader, offset, index, scale):
    base = offset + index * 4
    return reader.s16(base) * scale, reader.s16(base + 2) * scale


def _read_byte_tuple(reader, offset, index, size):
    base = offset + index * size
    return tuple(reader.u8(base + axis) for axis in range(size))


def _vertex_palette_for_shape(shape, vertex_count):
    palettes = [None] * vertex_count
    for prms in shape.prms:
        for index in prms.indices:
            if 0 <= index < vertex_count and palettes[index] is None:
                palettes[index] = prms.palette
    fallback = shape.prms[0].palette if shape.prms else (0,)
    return tuple(palette or fallback for palette in palettes)


def _stream_offset(vatr_offset, streams, lists, index):
    return vatr_offset + streams[index].offset + lists[index].offset


def _transform_normal(matrix, normal):
    transformed = matrix.to_3x3() @ Vector(normal)
    if transformed.length > 0.0:
        transformed.normalize()
    return float(transformed.x), float(transformed.y), float(transformed.z)


def _source_vertex_weights(reader, shape, prms, vertex_index, bone_indices_offset, bone_weights_offset, weighted):
    if prms.skinning_mode == 0:
        return ((prms.palette[0] if prms.palette else 0, 1.0),)

    if not weighted:
        return ((prms.palette[0] if prms.palette else 0, 1.0),)

    local_indices = _read_byte_tuple(reader, bone_indices_offset, vertex_index, shape.bone_dimension)
    raw_weights = _read_byte_tuple(reader, bone_weights_offset, vertex_index, shape.bone_dimension)
    return tuple(
        (prms.palette[index] if index < len(prms.palette) else 0, raw_weight / 100.0)
        for index, raw_weight in zip(local_indices, raw_weights)
        if raw_weight > 0
    )


def _shape_geometry(reader, shape, vatr_offset, vatr_streams, bone_matrices):
    vertex_count = _shape_vertex_count(shape)
    lists = shape.vertex_lists
    positions_offset = _stream_offset(vatr_offset, vatr_streams, lists, 0)
    normals_offset = _stream_offset(vatr_offset, vatr_streams, lists, 1)
    colors_offset = _stream_offset(vatr_offset, vatr_streams, lists, 2)
    uv_offsets = tuple(
        _stream_offset(vatr_offset, vatr_streams, lists, 3 + index)
        for index in range(3)
    )
    bone_indices_offset = _stream_offset(vatr_offset, vatr_streams, lists, 6)
    bone_weights_offset = _stream_offset(vatr_offset, vatr_streams, lists, 7)
    has_uv = (
        bool(shape.flags & SEPD_FLAGS_HAS_UV0),
        bool(shape.flags & SEPD_FLAGS_HAS_UV1),
        bool(shape.flags & SEPD_FLAGS_HAS_UV2),
    )
    positions = [_read_position(reader, positions_offset, index) for index in range(vertex_count)]
    normals = [_read_normal(reader, normals_offset, index, lists[1].scale) for index in range(vertex_count)]
    uvs = [
        [_read_uv(reader, uv_offsets[uv_index], index, lists[3 + uv_index].scale) for index in range(vertex_count)]
        if has_uv[uv_index]
        else None
        for uv_index in range(3)
    ]

    colors = None
    if shape.flags & SEPD_FLAGS_HAS_COLORS:
        colors = [reader.rgba8(colors_offset + index * 4) for index in range(vertex_count)]

    weighted = bool(shape.flags & SEPD_FLAGS_HAS_INDICES and shape.flags & SEPD_FLAGS_HAS_WEIGHTS)
    imported_positions = []
    imported_normals = []
    imported_uvs = [[] if uv_values is not None else None for uv_values in uvs]
    imported_colors = [] if colors is not None else None
    weights = []
    faces = []

    for prms in shape.prms:
        rigid_bone_index = prms.palette[0] if prms.skinning_mode == 0 and prms.palette else None
        rigid_matrix = (
            bone_matrices[rigid_bone_index]
            if rigid_bone_index is not None and 0 <= rigid_bone_index < len(bone_matrices)
            else None
        )
        vertex_lookup = {}
        for index in range(0, len(prms.indices), 3):
            triangle = prms.indices[index : index + 3]
            if len(triangle) != 3:
                continue

            face = []
            for source_index in triangle:
                imported_index = vertex_lookup.get(source_index)
                if imported_index is None:
                    position = Vector(positions[source_index])
                    normal = normals[source_index]
                    if rigid_matrix is not None:
                        position = rigid_matrix @ position
                        normal = _transform_normal(rigid_matrix, normal)

                    imported_index = len(imported_positions)
                    vertex_lookup[source_index] = imported_index
                    imported_positions.append((float(position.x), float(position.y), float(position.z)))
                    imported_normals.append(normal)
                    for uv_index, uv_values in enumerate(uvs):
                        if uv_values is not None:
                            imported_uvs[uv_index].append(uv_values[source_index])
                    if colors is not None:
                        imported_colors.append(colors[source_index])
                    weights.append(
                        _source_vertex_weights(
                            reader,
                            shape,
                            prms,
                            source_index,
                            bone_indices_offset,
                            bone_weights_offset,
                            weighted,
                        )
                    )
                face.append(imported_index)
            faces.append(tuple(face))

    return imported_positions, imported_normals, imported_uvs, imported_colors, weights, faces


def _create_mesh_object(name, shape, entry, reader, vatr_offset, vatr_streams, materials, armature, bone_names, bone_matrices):
    positions, normals, uvs, colors, weights, faces = _shape_geometry(reader, shape, vatr_offset, vatr_streams, bone_matrices)
    positions = [tuple(IMPORT_MESH_DATA_CORRECTION @ Vector(position)) for position in positions]
    normals = [_transform_normal(IMPORT_MESH_DATA_CORRECTION, normal) for normal in normals]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(positions, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if normals:
        loop_normals = [
            normals[mesh.loops[loop_index].vertex_index]
            for polygon in mesh.polygons
            for loop_index in polygon.loop_indices
        ]
        mesh.normals_split_custom_set(loop_normals)
        if hasattr(mesh, "use_auto_smooth"):
            mesh.use_auto_smooth = True
    if 0 <= entry.material_index < len(materials):
        mesh.materials.append(materials[entry.material_index])

    for uv_index, uv_values in enumerate(uvs):
        if uv_values is None:
            continue
        layer = mesh.uv_layers.new(name=f"UVMap{uv_index}")
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                layer.data[loop_index].uv = uv_values[mesh.loops[loop_index].vertex_index]

    if colors is not None:
        color_layer = mesh.vertex_colors.new(name="CMB Colors")
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                color = colors[mesh.loops[loop_index].vertex_index]
                color_layer.data[loop_index].color = _rgba8_to_float(color)

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = armature
    obj.rotation_euler = IMPORT_ROTATION_EULER
    obj.matrix_parent_inverse = armature.matrix_world.inverted()
    for bone_name in bone_names:
        obj.vertex_groups.new(name=bone_name)
    for vertex_index, influences in enumerate(weights):
        for bone_index, weight in influences:
            if 0 <= bone_index < len(bone_names):
                obj.vertex_groups[bone_names[bone_index]].add((vertex_index,), weight, "REPLACE")
    modifier = obj.modifiers.new("CMB Armature", "ARMATURE")
    modifier.object = armature
    return obj


def import_cmb(filepath):
    path = Path(filepath)
    reader = Reader(path.read_bytes())
    name, pointers = _read_header(reader)
    bones = _read_bones(reader, pointers["skl"])
    textures = _read_textures(reader, pointers["tex"])
    materials = _read_materials(reader, pointers["mats"], pointers["tex"], textures, pointers["textures"])
    entries, shp_offset = _read_mesh_entries(reader, pointers["sklm"])
    shapes = _read_shapes(reader, shp_offset, pointers["indices"])
    vatr_streams = _read_vatr_streams(reader, pointers["vatr"])
    armature, bone_names, bone_matrices = _create_armature(name, bones)

    imported = []
    for draw_index, entry in enumerate(entries):
        if not 0 <= entry.shape_index < len(shapes):
            continue
        imported.append(
            _create_mesh_object(
                f"vis{entry.visibility_id}_Shape{entry.shape_index:03d}",
                shapes[entry.shape_index],
                entry,
                reader,
                pointers["vatr"],
                vatr_streams,
                materials,
                armature,
                bone_names,
                bone_matrices,
            )
        )

    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    armature.select_set(True)
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return armature, tuple(imported), materials


class CMB_OT_import(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.cmb"
    bl_label = "Import CMB"
    bl_description = "Import a CMB model"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".cmb"
    filter_glob: bpy.props.StringProperty(default="*.cmb", options={"HIDDEN"})

    def execute(self, context):
        try:
            armature, meshes, materials = import_cmb(self.filepath)
        except CmbImportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Imported {len(meshes)} mesh(es), {len(armature.data.bones)} bone(s), {len(materials)} material(s)",
        )
        return {"FINISHED"}


def _menu_func_import(self, context):
    self.layout.operator(CMB_OT_import.bl_idname, text="Citrus Model Binary (.cmb)")


classes = (CMB_OT_import,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
