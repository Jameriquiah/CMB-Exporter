from dataclasses import dataclass
from pathlib import Path

from .binary import BinaryWriter
from .texture_encoder import CmbTextureEncodeError, EncodedTexture, encode_texture_pixels
from .textures import _image_pixels, _safe_texture_name


class CmabWriteError(ValueError):
    pass


@dataclass(frozen=True)
class CmabTexture:
    name: str
    encoded: EncodedTexture


def _patch_u32(writer, offset, value):
    writer.patch_u32(offset, value)


def _encode_cmab_texture(image, texture_format):
    pixels, width, height = _image_pixels(image)
    try:
        encoded = encode_texture_pixels(
            pixels,
            width,
            height,
            texture_format,
        )
    except CmbTextureEncodeError as exc:
        raise CmabWriteError(f"Image '{image.name}' texture export failed: {exc}") from exc
    return CmabTexture(name=_safe_texture_name(image.name), encoded=encoded)


def _write_string_table(writer, names):
    start = writer.offset
    writer.write_magic(b"STRT")
    writer.write_u32(len(names))
    offsets_start = writer.offset
    for _name in names:
        writer.write_u32(0)

    string_start = writer.offset
    for index, name in enumerate(names):
        _patch_u32(writer, offsets_start + index * 4, writer.offset - string_start)
        writer.write(name.encode("ascii", errors="replace") + b"\0")
    writer.align(16)
    return start


def _write_txpt(writer, textures):
    start = writer.offset
    writer.write_magic(b"TXPT")
    writer.write_u16(len(textures))
    writer.write_u16(0)

    data_offsets = []
    for index, texture in enumerate(textures):
        encoded = texture.encoded
        writer.write_u32(len(encoded.data))
        writer.write_u16(encoded.mipmap_count)
        writer.write_u8(encoded.is_etc1)
        writer.write_u8(0)
        writer.write_u16(encoded.width)
        writer.write_u16(encoded.height)
        writer.write_u16(encoded.texture_format)
        writer.write_u16(encoded.data_type)
        data_offsets.append(writer.reserve_u32())
        writer.write_u32(index)

    return start, tuple(data_offsets)


def _write_palette_track(writer, texture_count):
    writer.write_u32(3)
    writer.write_u32(texture_count)
    writer.write_u32(0)
    writer.write_u32(max(0, texture_count - 1))
    for index in range(texture_count):
        writer.write_s32(index)
        writer.write_f32(float(index))


def _write_mads(writer, material_index, channel_index, texture_count):
    start = writer.offset
    writer.write_magic(b"mads")
    writer.write_u32(1)
    writer.write_u32(12)

    writer.write_magic(b"mmad")
    writer.write_u32(2)
    writer.write_u32(material_index)
    writer.write_u32(channel_index)
    writer.write_u16(20)
    writer.write_u16(0)
    _write_palette_track(writer, texture_count)
    return start


def write_cmab_file(
    material,
    filepath,
    material_index,
    channel_index=0,
):
    settings = material.cmb_settings
    if not settings.cmab_texture_swap_enabled:
        raise CmabWriteError("Active material has no CMAB texture swap images")

    images = []
    for index, frame in enumerate(settings.cmab_texture_swap_images):
        if frame.image is None:
            raise CmabWriteError(f"CMAB texture swap image {index} is empty")
        images.append(frame.image)

    if not images:
        raise CmabWriteError("Active material has no CMAB texture swap images")

    textures = tuple(
        _encode_cmab_texture(image, settings.texture_format)
        for image in images
    )

    writer = BinaryWriter()
    writer.write_magic(b"cmab")
    writer.write_u32(1)
    size_offset = writer.reserve_u32()
    writer.write_u32(0)
    writer.write_u32(1)
    anmd_offset = writer.reserve_u32()
    strt_offset = writer.reserve_u32()
    texture_data_offset = writer.reserve_u32()

    _patch_u32(writer, anmd_offset, writer.offset)
    anmd_start = writer.offset
    writer.write_u32(0xFFFFFFFF)
    writer.write_u32(len(textures))
    writer.write_u32(1)
    mads_pointer_offset = writer.reserve_u32()
    txpt_pointer_offset = writer.reserve_u32()

    mads_start = _write_mads(writer, material_index, channel_index, len(textures))
    _patch_u32(writer, mads_pointer_offset, mads_start - anmd_start)
    _patch_u32(writer, txpt_pointer_offset, writer.offset - anmd_start)
    _txpt_start, data_offset_fields = _write_txpt(writer, textures)

    writer.align(16)
    _patch_u32(writer, strt_offset, writer.offset)
    _write_string_table(writer, tuple(texture.name for texture in textures))

    writer.align(16)
    data_start = writer.offset
    _patch_u32(writer, texture_data_offset, data_start)
    for texture, offset_field in zip(textures, data_offset_fields):
        _patch_u32(writer, offset_field, writer.offset - data_start)
        writer.write(texture.encoded.data)
        writer.align(16)

    _patch_u32(writer, size_offset, writer.offset)
    path = Path(filepath)
    if path.suffix.lower() != ".cmab":
        path = path.with_suffix(".cmab")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(writer.bytes())
    return path
