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

ETC1_MODIFIER_TABLES = (
    (2, 8, -2, -8),
    (5, 17, -5, -17),
    (9, 29, -9, -29),
    (13, 42, -13, -42),
    (18, 60, -18, -60),
    (24, 80, -24, -80),
    (33, 106, -33, -106),
    (47, 183, -47, -183),
)

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


def _expand4(value):
    return (value << 4) | value


def _expand5(value):
    return (value << 3) | (value >> 2)


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


def _get_pixel_rgba8(pixels, width, height, x, y):
    if 0 <= x < width and 0 <= y < height:
        return _rgba8(pixels[y * width + x])
    return 0, 0, 0, 0


def _avg_color(block, coords):
    red = green = blue = 0
    for x, y in coords:
        pixel = block[y][x]
        red += pixel[0]
        green += pixel[1]
        blue += pixel[2]
    count = len(coords)
    return red / count, green / count, blue / count


def _quantize_color4(color):
    return tuple(max(0, min(15, round(channel / 17.0))) for channel in color)


def _quantize_color5(color):
    return tuple(max(0, min(31, round((channel / 255.0) * 31.0))) for channel in color)


def _base4_candidates(color, radius=1):
    center = _quantize_color4(color)
    ranges = [
        range(max(0, component - radius), min(15, component + radius) + 1)
        for component in center
    ]
    return (
        (red, green, blue)
        for red in ranges[0]
        for green in ranges[1]
        for blue in ranges[2]
    )


def _base5_candidates(color, radius=1):
    center = _quantize_color5(color)
    ranges = [
        range(max(0, component - radius), min(31, component + radius) + 1)
        for component in center
    ]
    return (
        (red, green, blue)
        for red in ranges[0]
        for green in ranges[1]
        for blue in ranges[2]
    )


def _selector_error(pixel, base_color, modifier):
    red = _clamp_u8(base_color[0] + modifier)
    green = _clamp_u8(base_color[1] + modifier)
    blue = _clamp_u8(base_color[2] + modifier)
    return (
        (pixel[0] - red) * (pixel[0] - red)
        + (pixel[1] - green) * (pixel[1] - green)
        + (pixel[2] - blue) * (pixel[2] - blue)
    )


def _fit_etc_subblock(block, coords, base_candidates, expand_base, limit=None):
    base_candidates = tuple(base_candidates)
    best_table = 0
    best_base = None
    best_selectors = {}
    best_error = None
    candidates = []

    for table_index, modifiers in enumerate(ETC1_MODIFIER_TABLES):
        for base in base_candidates:
            base_color = tuple(expand_base(channel) for channel in base)
            table_error = 0
            table_selectors = {}
            for x, y in coords:
                pixel = block[y][x]
                selector, selector_error = min(
                    enumerate(_selector_error(pixel, base_color, modifier) for modifier in modifiers),
                    key=lambda item: item[1],
                )
                table_selectors[(x, y)] = selector
                table_error += selector_error
                if limit is None and best_error is not None and table_error >= best_error:
                    break

            if best_error is None or table_error < best_error:
                best_error = table_error
                best_base = base
                best_table = table_index
                best_selectors = table_selectors
            candidates.append((table_error, base, table_index, table_selectors))

    if limit is not None:
        candidates.sort(key=lambda item: item[0])
        candidates = candidates[:limit]

    return best_base or (0, 0, 0), best_table, best_selectors, best_error or 0, candidates


def _best_etc_subblock4(block, coords, radius):
    average = _avg_color(block, coords)
    base, table, selectors, error, _candidates = _fit_etc_subblock(
        block,
        coords,
        _base4_candidates(average, radius=radius),
        _expand4,
    )
    return base, table, selectors, error


def _etc_subblock5_candidates(block, coords, limit):
    average = _avg_color(block, coords)
    _base, _table, _selectors, _error, candidates = _fit_etc_subblock(
        block,
        coords,
        _base5_candidates(average),
        _expand5,
        limit=limit,
    )
    return candidates


def _etc_pixel_index(x, y):
    return x * 4 + y


def _pack_etc1_individual_block(block, flip, first_coords, second_coords, radius):
    first_color4, first_table, first_selectors, first_error = _best_etc_subblock4(block, first_coords, radius)
    second_color4, second_table, second_selectors, second_error = _best_etc_subblock4(block, second_coords, radius)
    selectors = {**first_selectors, **second_selectors}

    high = (
        (first_color4[0] << 28)
        | (second_color4[0] << 24)
        | (first_color4[1] << 20)
        | (second_color4[1] << 16)
        | (first_color4[2] << 12)
        | (second_color4[2] << 8)
        | (first_table << 5)
        | (second_table << 2)
        | (1 if flip else 0)
    )
    low = 0
    for y in range(4):
        for x in range(4):
            selector = selectors[(x, y)]
            pixel_index = _etc_pixel_index(x, y)
            low |= (selector & 1) << pixel_index
            low |= ((selector >> 1) & 1) << (pixel_index + 16)

    return (((high << 32) | low).to_bytes(8, "little"), first_error + second_error)


def _pack_etc1_differential_block(block, flip, first_coords, second_coords, candidate_limit):
    if candidate_limit <= 0:
        return None, float("inf")

    first_candidates = _etc_subblock5_candidates(block, first_coords, candidate_limit)
    second_candidates = _etc_subblock5_candidates(block, second_coords, candidate_limit)
    best = None

    for first_error, first_color5, first_table, first_selectors in first_candidates:
        for second_error, second_color5, second_table, second_selectors in second_candidates:
            delta = tuple(second_color5[index] - first_color5[index] for index in range(3))
            if any(component < -4 or component > 3 for component in delta):
                continue

            error = first_error + second_error
            if best is None or error < best[0]:
                best = (
                    error,
                    first_color5,
                    delta,
                    first_table,
                    second_table,
                    {**first_selectors, **second_selectors},
                )

    if best is None:
        return None, float("inf")

    error, first_color5, delta, first_table, second_table, selectors = best
    high = (
        (first_color5[0] << 27)
        | ((delta[0] & 0x7) << 24)
        | (first_color5[1] << 19)
        | ((delta[1] & 0x7) << 16)
        | (first_color5[2] << 11)
        | ((delta[2] & 0x7) << 8)
        | (first_table << 5)
        | (second_table << 2)
        | (1 << 1)
        | (1 if flip else 0)
    )
    low = 0
    for y in range(4):
        for x in range(4):
            selector = selectors[(x, y)]
            pixel_index = _etc_pixel_index(x, y)
            low |= (selector & 1) << pixel_index
            low |= ((selector >> 1) & 1) << (pixel_index + 16)

    return (((high << 32) | low).to_bytes(8, "little"), error)


def _decode_etc1_block_for_error(block_bytes):
    value = int.from_bytes(block_bytes, "little")
    high = (value >> 32) & 0xFFFFFFFF
    low = value & 0xFFFFFFFF
    flip = high & 1
    differential = (high >> 1) & 1
    table1 = (high >> 5) & 0x7
    table2 = (high >> 2) & 0x7

    if differential:
        red1 = (high >> 27) & 0x1F
        green1 = (high >> 19) & 0x1F
        blue1 = (high >> 11) & 0x1F
        red_delta = (high >> 24) & 0x7
        green_delta = (high >> 16) & 0x7
        blue_delta = (high >> 8) & 0x7
        red_delta = red_delta - 8 if red_delta & 0x4 else red_delta
        green_delta = green_delta - 8 if green_delta & 0x4 else green_delta
        blue_delta = blue_delta - 8 if blue_delta & 0x4 else blue_delta
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
            pixel_index = _etc_pixel_index(x, y)
            selector = ((low >> pixel_index) & 1) | (((low >> (pixel_index + 16)) & 1) << 1)
            subblock = (y >= 2) if flip else (x >= 2)
            color = colors[1 if subblock else 0]
            modifier = ETC1_MODIFIER_TABLES[table2 if subblock else table1][selector]
            row.append(tuple(_clamp_u8(channel + modifier) for channel in color))
        decoded.append(row)
    return decoded


def _etc1_decoded_error(block_bytes, source_block):
    decoded = _decode_etc1_block_for_error(block_bytes)
    error = 0
    for y in range(4):
        for x in range(4):
            pixel = source_block[y][x]
            red, green, blue = decoded[y][x]
            error += (pixel[0] - red) * (pixel[0] - red)
            error += (pixel[1] - green) * (pixel[1] - green)
            error += (pixel[2] - blue) * (pixel[2] - blue)
    return error


def _pack_etc1_block(block, flip, first_coords, second_coords, individual_radius, candidate_limit):
    individual_block, _individual_error = _pack_etc1_individual_block(
        block, flip, first_coords, second_coords, individual_radius
    )
    individual_error = _etc1_decoded_error(individual_block, block)
    differential_block, _differential_error = _pack_etc1_differential_block(
        block, flip, first_coords, second_coords, candidate_limit
    )
    if differential_block is not None:
        differential_error = _etc1_decoded_error(differential_block, block)
        if differential_error < individual_error:
            return differential_block, differential_error
    return individual_block, individual_error


def _encode_etc1_block(block, individual_radius, candidate_limit):
    vertical_first = tuple((x, y) for y in range(4) for x in range(2))
    vertical_second = tuple((x, y) for y in range(4) for x in range(2, 4))
    horizontal_first = tuple((x, y) for y in range(2) for x in range(4))
    horizontal_second = tuple((x, y) for y in range(2, 4) for x in range(4))

    vertical_block, vertical_error = _pack_etc1_block(
        block, False, vertical_first, vertical_second, individual_radius, candidate_limit
    )
    horizontal_block, horizontal_error = _pack_etc1_block(
        block, True, horizontal_first, horizontal_second, individual_radius, candidate_limit
    )
    return horizontal_block if horizontal_error < vertical_error else vertical_block


def _encode_etc1a4_alpha_block(block):
    value = 0
    for y in range(4):
        for x in range(4):
            value |= (block[y][x][3] >> 4) << (_etc_pixel_index(x, y) * 4)
    return value.to_bytes(8, "little")


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


def _encode_etc_texture(pixels, width, height, texture_format):
    encoded = bytearray()
    for block_x, block_y in _etc_block_order(width, height):
        block = [
            [
                _get_pixel_rgba8(pixels, width, height, block_x + x, block_y + y)
                for x in range(ETC_BLOCK_SIZE)
            ]
            for y in range(ETC_BLOCK_SIZE)
        ]
        if texture_format == "ETC1A4":
            encoded.extend(_encode_etc1a4_alpha_block(block))
        encoded.extend(_encode_etc1_block(block, 1, 48))
    return bytes(encoded)


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
