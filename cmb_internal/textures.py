from dataclasses import dataclass, replace
from pathlib import Path

from .texture_encoder import CmbTextureEncodeError, EncodedTexture, encode_texture_pixels
from .texture_slots import iter_texture_slot_values, texture_slot_attr


class CmbTextureExportError(ValueError):
    pass


@dataclass(frozen=True)
class CmbTexture:
    name: str
    encoded: EncodedTexture


def _png_color_info(data):
    if len(data) < 26 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return data[24], data[25]


def _image_png_color_info(image):
    packed_file = getattr(image, "packed_file", None)
    if packed_file is not None:
        return _png_color_info(packed_file.data[:26])

    filepath_from_user = getattr(image, "filepath_from_user", None)
    filepath = filepath_from_user() if filepath_from_user is not None else image.filepath
    if not filepath:
        return None
    try:
        return _png_color_info(Path(filepath).read_bytes()[:26])
    except OSError:
        return None


def _linear_to_srgb(value):
    value = max(0.0, min(1.0, value))
    if value <= 0.0031308:
        return value * 12.92
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def _image_needs_srgb_pixels(image):
    color_info = _image_png_color_info(image)
    if color_info is None:
        return False
    bit_depth, color_type = color_info
    colorspace = image.colorspace_settings.name.lower()
    return bit_depth > 8 and color_type in {2, 6} and "srgb" in colorspace


def _display_pixel(pixel):
    return (
        _linear_to_srgb(pixel[0]),
        _linear_to_srgb(pixel[1]),
        _linear_to_srgb(pixel[2]),
        pixel[3],
    )


def _image_pixels(image):
    if image.size[0] <= 0 or image.size[1] <= 0:
        raise CmbTextureExportError(f"Image '{image.name}' has invalid dimensions")

    if not image.has_data:
        image.pixels[0]

    width, height = image.size
    values = list(image.pixels)
    source_pixels = [
        tuple(values[offset : offset + 4])
        for offset in range(0, len(values), 4)
    ]
    if _image_needs_srgb_pixels(image):
        source_pixels = [_display_pixel(pixel) for pixel in source_pixels]
    pixels = [
        pixel
        for y in range(height - 1, -1, -1)
        for pixel in source_pixels[y * width : (y + 1) * width]
    ]

    return pixels, width, height


def _safe_texture_name(name):
    return name.rsplit(".", 1)[0][:16] or "texture"


def _texture_slot_uses(material):
    return tuple(
        (slot_index, image_name, texture_format)
        for slot_index, (image_name, texture_format) in iter_texture_slot_values(
            material, "image_name", "format"
        )
    )


def _validate_texture_format_consistency(model):
    uses_by_image = {}
    for material in model.materials:
        for slot_index, image_name, texture_format in _texture_slot_uses(material):
            if not image_name:
                continue
            uses_by_image.setdefault(image_name, []).append(
                (texture_format, material.name, slot_index)
            )

    conflicts = []
    for image_name, uses in uses_by_image.items():
        formats = {texture_format for texture_format, _material_name, _slot_index in uses}
        if len(formats) <= 1:
            continue
        details = ", ".join(
            f"{material_name} slot {slot_index}: {texture_format}"
            for texture_format, material_name, slot_index in uses
        )
        conflicts.append(f"{image_name} ({details})")

    if conflicts:
        raise CmbTextureExportError(
            "Texture format mismatch: the same image must use one format everywhere. "
            + "; ".join(conflicts)
        )


def _validate_texture_coord_mappings(model):
    conflicts = []
    for material in model.materials:
        for slot_index, (image_name, coord_mapping) in iter_texture_slot_values(
            material, "image_name", "coord_mapping"
        ):
            if image_name and coord_mapping == 0:
                conflicts.append(f"{material.name} slot {slot_index}: {image_name}")

    if conflicts:
        raise CmbTextureExportError(
            "Texture coordinate mapping is None for assigned texture slot(s): "
            + "; ".join(conflicts)
        )


def attach_textures_to_model(model, bpy_data):
    _validate_texture_format_consistency(model)
    _validate_texture_coord_mappings(model)

    textures = []
    texture_lookup = {}
    materials = []

    for material in model.materials:
        texture_indices = []

        for _slot_index, image_name, texture_format in _texture_slot_uses(material):
            if not image_name:
                texture_indices.append(-1)
                continue

            key = (image_name, texture_format)
            texture_index = texture_lookup.get(key)
            if texture_index is not None:
                texture_indices.append(texture_index)
                continue

            image = bpy_data.images.get(image_name)
            if image is None:
                raise CmbTextureExportError(
                    f"Material '{material.name}' references missing image '{image_name}'"
                )

            pixels, width, height = _image_pixels(image)
            try:
                encoded = encode_texture_pixels(
                    pixels,
                    width,
                    height,
                    texture_format,
                )
            except CmbTextureEncodeError as exc:
                raise CmbTextureExportError(
                    f"Material '{material.name}' texture export failed: {exc}"
                ) from exc

            texture_index = len(textures)
            texture_lookup[key] = texture_index
            textures.append(
                CmbTexture(
                    name=_safe_texture_name(image.name),
                    encoded=encoded,
                )
            )
            texture_indices.append(texture_index)

        index_updates = {
            texture_slot_attr(slot_index, "index"): texture_index
            for slot_index, texture_index in enumerate(texture_indices)
        }
        materials.append(replace(material, **index_updates))

    return replace(model, materials=tuple(materials), textures=tuple(textures))
