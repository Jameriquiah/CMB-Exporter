from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import tempfile

from .cmb_constants import PicaDataType, PicaTextureFormat


class CmbTextureEncodeError(ValueError):
    pass


@dataclass(frozen=True)
class EncodedTexture:
    data: bytes
    width: int
    height: int
    texture_format: PicaTextureFormat
    data_type: int
    is_etc1: int = 0
    mipmap_count: int = 1


TEXTURE_FORMATS = {
    "RGB565": (PicaTextureFormat.RGB_NATIVE_DMP, PicaDataType.UNSIGNED_SHORT_565),
    "RGBA5551": (PicaTextureFormat.RGBA_NATIVE_DMP, PicaDataType.UNSIGNED_SHORT_5551),
    "LA4": (PicaTextureFormat.LUMINANCE_ALPHA_NATIVE_DMP, PicaDataType.UNSIGNED_BYTE_44_DMP),
    "LA8": (PicaTextureFormat.LUMINANCE_ALPHA_NATIVE_DMP, PicaDataType.U8),
    "L8": (PicaTextureFormat.LUMINANCE_NATIVE_DMP, PicaDataType.U8),
    "L4": (PicaTextureFormat.LUMINANCE_NATIVE_DMP, PicaDataType.UNSIGNED_4_BITS_DMP),
    "A8": (PicaTextureFormat.ALPHA_NATIVE_DMP, PicaDataType.U8),
    "ETC1": (PicaTextureFormat.ETC1_RGB8_NATIVE_DMP, 0),
    "ETC1A4": (PicaTextureFormat.ETC1_ALPHA_RGB8_A4_NATIVE_DMP, 0),
}

ETC_BLOCK_SIZE = 4
PICA_TILE_SIZE = 8
ETC_COLOR_BLOCK_BYTES = 8
ETC_ALPHA_BLOCK_BYTES = 8


def _external_compressor_path():
    tools_dir = Path(__file__).resolve().parent / "tools"
    if sys.platform == "win32":
        return tools_dir / "windows" / "etc1compress.exe"
    if sys.platform == "darwin":
        return tools_dir / "macos" / "etc1compress"
    if sys.platform.startswith("linux"):
        return tools_dir / "linux" / "etc1compress"
    raise CmbTextureEncodeError(f"No bundled ETC1 compressor for platform: {sys.platform}")


def _clamp_u8(value):
    return max(0, min(255, round(value)))


def _rgba8(pixel):
    red, green, blue, alpha = (_clamp_u8(channel * 255.0) for channel in pixel)
    return red, green, blue, alpha


def _luminance(red, green, blue):
    return _clamp_u8((0.299 * red) + (0.587 * green) + (0.114 * blue))


def _pack_u16(value):
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def _encode_pixel(pixel, texture_format):
    red, green, blue, alpha = _rgba8(pixel)

    if texture_format == "RGB565":
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        return _pack_u16(value)
    if texture_format == "RGBA5551":
        value = ((red >> 3) << 11) | ((green >> 3) << 6) | ((blue >> 3) << 1) | (1 if alpha >= 128 else 0)
        return _pack_u16(value)
    if texture_format == "LA4":
        return bytes(((_luminance(red, green, blue) >> 4) | ((alpha >> 4) << 4),))
    if texture_format == "LA8":
        return bytes((alpha, _luminance(red, green, blue)))
    if texture_format == "L8":
        return bytes((_luminance(red, green, blue),))
    if texture_format == "A8":
        return bytes((alpha,))

    raise CmbTextureEncodeError(
        f"Texture format {texture_format} needs a dedicated compressor and is not implemented yet"
    )


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
    padded_width = ((width + PICA_TILE_SIZE - 1) // PICA_TILE_SIZE) * PICA_TILE_SIZE
    padded_height = ((height + PICA_TILE_SIZE - 1) // PICA_TILE_SIZE) * PICA_TILE_SIZE
    for tile_y in range(0, padded_height, PICA_TILE_SIZE):
        for tile_x in range(0, padded_width, PICA_TILE_SIZE):
            coords = []
            for y in range(PICA_TILE_SIZE):
                for x in range(PICA_TILE_SIZE):
                    coords.append((_morton_index_8x8(x, y), tile_x + x, tile_y + y))
            for _order, x, y in sorted(coords):
                yield x, y


def _etc_block_order(width, height):
    padded_width = ((width + PICA_TILE_SIZE - 1) // PICA_TILE_SIZE) * PICA_TILE_SIZE
    padded_height = ((height + PICA_TILE_SIZE - 1) // PICA_TILE_SIZE) * PICA_TILE_SIZE
    block_offsets = ((0, 0), (ETC_BLOCK_SIZE, 0), (0, ETC_BLOCK_SIZE), (ETC_BLOCK_SIZE, ETC_BLOCK_SIZE))
    for tile_y in range(0, padded_height, PICA_TILE_SIZE):
        for tile_x in range(0, padded_width, PICA_TILE_SIZE):
            for offset_x, offset_y in block_offsets:
                yield tile_x + offset_x, tile_y + offset_y


def _expected_etc_size(width, height, texture_format):
    padded_width = ((width + PICA_TILE_SIZE - 1) // PICA_TILE_SIZE) * PICA_TILE_SIZE
    padded_height = ((height + PICA_TILE_SIZE - 1) // PICA_TILE_SIZE) * PICA_TILE_SIZE
    block_count = (padded_width // ETC_BLOCK_SIZE) * (padded_height // ETC_BLOCK_SIZE)
    bytes_per_block = ETC_COLOR_BLOCK_BYTES
    if texture_format == "ETC1A4":
        bytes_per_block += ETC_ALPHA_BLOCK_BYTES
    return block_count * bytes_per_block


def _rgba8_bytes(pixels):
    raw = bytearray()
    for pixel in pixels:
        raw.extend(_rgba8(pixel))
    return bytes(raw)


def _encode_etc_texture_external(pixels, width, height, texture_format):
    executable = _external_compressor_path()
    if not executable.exists():
        raise CmbTextureEncodeError(f"Bundled ETC1 compressor not found: {executable}")

    if sys.platform != "win32":
        try:
            executable.chmod(executable.stat().st_mode | 0o755)
        except OSError:
            pass

    cli_format = "etc1a4" if texture_format == "ETC1A4" else "etc1"
    with tempfile.TemporaryDirectory(prefix="cmb_etc1_") as temp_dir:
        input_path = Path(temp_dir) / "input.rgba"
        output_path = Path(temp_dir) / "output.bin"
        input_path.write_bytes(_rgba8_bytes(pixels))
        result = subprocess.run(
            [
                str(executable),
                cli_format,
                str(width),
                str(height),
                str(input_path),
                str(output_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "unknown compressor error").strip()
            raise CmbTextureEncodeError(f"ETC1 compressor failed: {message}")
        encoded = output_path.read_bytes()

    expected_size = _expected_etc_size(width, height, texture_format)
    if len(encoded) != expected_size:
        raise CmbTextureEncodeError(
            f"ETC1 compressor wrote {len(encoded)} bytes, expected {expected_size}"
        )
    return encoded


def encode_texture_pixels(pixels, width, height, texture_format):
    if texture_format not in TEXTURE_FORMATS:
        raise CmbTextureEncodeError(f"Unknown texture format: {texture_format}")

    pica_format, data_type = TEXTURE_FORMATS[texture_format]
    if len(pixels) != width * height:
        raise CmbTextureEncodeError(
            f"Expected {width * height} RGBA pixels, got {len(pixels)}"
        )

    encoded = bytearray()
    transparent = (0.0, 0.0, 0.0, 0.0)
    if texture_format in {"ETC1", "ETC1A4"}:
        encoded = bytearray(
            _encode_etc_texture_external(
                pixels,
                width,
                height,
                texture_format,
            )
        )
    elif texture_format == "L4":
        pending_luminance = None
        for x, y in _tile_order(width, height):
            pixel = pixels[y * width + x] if x < width and y < height else transparent
            red, green, blue, _alpha = _rgba8(pixel)
            luminance = _luminance(red, green, blue) >> 4
            if pending_luminance is None:
                pending_luminance = luminance
            else:
                encoded.append(pending_luminance | (luminance << 4))
                pending_luminance = None
        if pending_luminance is not None:
            encoded.append(pending_luminance)
    else:
        for x, y in _tile_order(width, height):
            pixel = pixels[y * width + x] if x < width and y < height else transparent
            encoded.extend(_encode_pixel(pixel, texture_format))

    return EncodedTexture(
        data=bytes(encoded),
        width=width,
        height=height,
        texture_format=pica_format,
        data_type=data_type,
        is_etc1=1 if texture_format in {"ETC1", "ETC1A4"} else 0,
    )
