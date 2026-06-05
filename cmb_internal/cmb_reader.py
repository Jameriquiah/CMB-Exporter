import struct
from dataclasses import dataclass
from pathlib import Path

from .cmb_constants import (
    CMB_MAGIC,
    CMB_VERSION_OOT3D,
    LUTS_MAGIC,
    MATS_MAGIC,
    MSHS_MAGIC,
    PRM_MAGIC,
    PRMS_MAGIC,
    SEPD_MAGIC,
    SHP_MAGIC,
    SKL_MAGIC,
    SKLM_MAGIC,
    TEX_MAGIC,
    VATR_MAGIC,
)


@dataclass(frozen=True)
class CmbHeader:
    file_size: int
    version: int
    model_name: str
    vertex_index_count: int
    skl_offset: int
    mats_offset: int
    tex_offset: int
    sklm_offset: int
    luts_offset: int
    vatr_offset: int
    vertex_index_data_offset: int
    texture_data_offset: int


@dataclass(frozen=True)
class CmbChunkInfo:
    name: str
    offset: int
    magic: bytes
    size: int
    count: int | None = None


@dataclass(frozen=True)
class CmbSklmInfo:
    offset: int
    size: int
    mshs_offset: int
    shp_offset: int


@dataclass(frozen=True)
class CmbMeshInfo:
    index: int
    sepd_index: int
    material_index: int
    visibility_id: int


@dataclass(frozen=True)
class CmbShpInfo:
    offset: int
    size: int
    sepd_count: int
    flags: int
    sepd_offsets: tuple[int, ...]


@dataclass(frozen=True)
class CmbVertexListInfo:
    name: str
    offset: int
    scale: float
    data_type: int
    mode: int
    constant: tuple[float, float, float, float]


@dataclass(frozen=True)
class CmbPrmInfo:
    offset: int
    size: int
    is_visible: int
    primitive_mode: int
    data_type: int
    unknown: int
    index_count: int
    first_index: int


@dataclass(frozen=True)
class CmbPrmsInfo:
    offset: int
    size: int
    raw_header_words: tuple[int, ...]
    skinning_mode: int
    bone_count: int
    bone_indices_offset: int
    prm_offset: int
    bone_indices: tuple[int, ...]
    prm: CmbPrmInfo | None


@dataclass(frozen=True)
class CmbSepdInfo:
    index: int
    offset: int
    size: int
    prms_count: int
    flags: int
    center: tuple[float, float, float]
    position_offset: tuple[float, float, float]
    vertex_lists: tuple[CmbVertexListInfo, ...]
    bone_dimension: int
    auto_flags: int
    prms_offsets: tuple[int, ...]
    prms: tuple[CmbPrmsInfo, ...]


@dataclass(frozen=True)
class CmbVatrEntry:
    name: str
    size: int
    data_offset: int
    absolute_data_offset: int | None


@dataclass(frozen=True)
class CmbTextureInfo:
    index: int
    offset: int
    data_size: int
    mipmap_count: int
    is_etc1: int
    is_cubemap: int
    width: int
    height: int
    format: int
    data_type: int
    data_offset: int
    absolute_data_offset: int
    name: str


@dataclass(frozen=True)
class CmbTexInfo:
    offset: int
    size: int
    texture_count: int
    textures: tuple[CmbTextureInfo, ...]


@dataclass(frozen=True)
class CmbBoneInfo:
    index: int
    offset: int
    bone_id: int
    parent_id: int
    scale: tuple[float, float, float]
    rotation: tuple[float, float, float]
    translation: tuple[float, float, float]


@dataclass(frozen=True)
class CmbSklInfo:
    offset: int
    size: int
    bone_count: int
    flags: int
    bones: tuple[CmbBoneInfo, ...]


@dataclass(frozen=True)
class CmbMatTextureInfo:
    texture_index: int
    min_filter: int
    mag_filter: int
    wrap_s: int
    wrap_t: int
    min_lod_bias: float
    lod_bias: float
    border_color: tuple[int, int, int, int]


@dataclass(frozen=True)
class CmbTextureCoordInfo:
    matrix_mode: int
    reference_camera: int
    mapping_method: int
    coordinate_index: int
    scale: tuple[float, float]
    rotation: float
    translation: tuple[float, float]


@dataclass(frozen=True)
class CmbMaterialInfo:
    index: int
    offset: int
    fragment_lighting: bool
    vertex_lighting: bool
    is_fog_enabled: bool
    render_layer: int
    face_culling: bool
    polygon_offset_enabled: bool
    polygon_offset: int
    texture_mappers_used: int
    texture_coords_used: int
    textures: tuple[CmbMatTextureInfo, ...]
    texture_coords: tuple[CmbTextureCoordInfo, ...]
    emission_color: tuple[int, int, int, int]
    ambient_color: tuple[int, int, int, int]
    diffuse_color: tuple[int, int, int, int]
    specular0_color: tuple[int, int, int, int]
    specular1_color: tuple[int, int, int, int]
    constant_colors: tuple[tuple[int, int, int, int], ...]
    buffer_color: tuple[float, float, float, float]
    used_tex_env_stages: int
    tex_env_stage_indices: tuple[int, ...]
    alpha_test_enabled: bool
    alpha_reference: int
    alpha_function: int
    depth_test_enabled: bool
    depth_write_enabled: bool
    depth_function: int
    blend_mode: int
    alpha_src_function: int
    alpha_dst_function: int
    alpha_equation: int
    color_src_function: int
    color_dst_function: int
    color_equation: int
    blend_color: tuple[float, float, float, float]


@dataclass(frozen=True)
class CmbTextureEnvInfo:
    index: int
    offset: int
    combine_rgb: int
    combine_alpha: int
    source_rgb: tuple[int, int, int]
    operand_rgb: tuple[int, int, int]
    source_alpha: tuple[int, int, int]
    operand_alpha: tuple[int, int, int]
    raw_words: tuple[int, ...]


@dataclass(frozen=True)
class CmbMatsInfo:
    offset: int
    size: int
    material_count: int
    material_stride: int
    trailing_bytes: int
    materials: tuple[CmbMaterialInfo, ...]
    texture_envs: tuple[CmbTextureEnvInfo, ...]


class CmbReadError(ValueError):
    pass


def _read_u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _read_fixed_ascii(data, offset, size):
    raw = data[offset : offset + size].split(b"\0", 1)[0]
    return raw.decode("ascii", errors="replace")


def _read_f32(data, offset):
    return struct.unpack_from("<f", data, offset)[0]


def _read_vector3(data, offset):
    return struct.unpack_from("<fff", data, offset)


def _read_vector4(data, offset):
    return struct.unpack_from("<ffff", data, offset)


def _read_rgba8(data, offset):
    return struct.unpack_from("<BBBB", data, offset)


def read_cmb_header(data):
    if data[:4] != CMB_MAGIC:
        raise CmbReadError(f"Expected CMB magic {CMB_MAGIC!r}, got {data[:4]!r}")

    header = CmbHeader(
        file_size=_read_u32(data, 0x04),
        version=_read_u32(data, 0x08),
        model_name=_read_fixed_ascii(data, 0x10, 16),
        vertex_index_count=_read_u32(data, 0x20),
        skl_offset=_read_u32(data, 0x24),
        mats_offset=_read_u32(data, 0x28),
        tex_offset=_read_u32(data, 0x2C),
        sklm_offset=_read_u32(data, 0x30),
        luts_offset=_read_u32(data, 0x34),
        vatr_offset=_read_u32(data, 0x38),
        vertex_index_data_offset=_read_u32(data, 0x3C),
        texture_data_offset=_read_u32(data, 0x40),
    )

    if header.version != CMB_VERSION_OOT3D:
        raise CmbReadError(
            f"Expected OoT3D CMB version {CMB_VERSION_OOT3D}, got {header.version}"
        )
    if header.file_size != len(data):
        raise CmbReadError(
            f"Header file size {header.file_size} does not match actual size {len(data)}"
        )

    return header


def _chunk_info(data, name, offset, expected_magic, has_count=True):
    magic = data[offset : offset + 4]
    if magic != expected_magic:
        raise CmbReadError(
            f"Expected {expected_magic!r} for {name} at {offset:#x}, got {magic!r}"
        )

    count = _read_u32(data, offset + 8) if has_count and offset + 12 <= len(data) else None
    return CmbChunkInfo(
        name=name,
        offset=offset,
        magic=magic,
        size=_read_u32(data, offset + 4),
        count=count,
    )


def read_top_level_chunks(data, header):
    return (
        _chunk_info(data, "skl", header.skl_offset, SKL_MAGIC),
        _chunk_info(data, "mats", header.mats_offset, MATS_MAGIC),
        _chunk_info(data, "tex", header.tex_offset, TEX_MAGIC),
        _chunk_info(data, "sklm", header.sklm_offset, SKLM_MAGIC, has_count=False),
        _chunk_info(data, "luts", header.luts_offset, LUTS_MAGIC),
        _chunk_info(data, "vatr", header.vatr_offset, VATR_MAGIC),
    )


def _expect_magic(data, offset, expected_magic, name):
    magic = data[offset : offset + 4]
    if magic != expected_magic:
        raise CmbReadError(
            f"Expected {expected_magic!r} for {name} at {offset:#x}, got {magic!r}"
        )


def read_sklm_info(data, header):
    offset = header.sklm_offset
    _expect_magic(data, offset, SKLM_MAGIC, "sklm")
    size = _read_u32(data, offset + 4)
    mshs_rel = _read_u32(data, offset + 8)
    shp_rel = _read_u32(data, offset + 0x0C)
    return CmbSklmInfo(
        offset=offset,
        size=size,
        mshs_offset=offset + mshs_rel,
        shp_offset=offset + shp_rel,
    )


def read_skl_info(data, header):
    offset = header.skl_offset
    _expect_magic(data, offset, SKL_MAGIC, "skl")
    size = _read_u32(data, offset + 4)
    bone_count = _read_u32(data, offset + 8)
    flags = _read_u32(data, offset + 0x0C)
    bones = []
    record_start = offset + 0x10
    for index in range(bone_count):
        bone_offset = record_start + index * 0x28
        bones.append(
            CmbBoneInfo(
                index=index,
                offset=bone_offset,
                bone_id=struct.unpack_from("<h", data, bone_offset)[0],
                parent_id=struct.unpack_from("<h", data, bone_offset + 2)[0],
                scale=_read_vector3(data, bone_offset + 4),
                rotation=_read_vector3(data, bone_offset + 0x10),
                translation=_read_vector3(data, bone_offset + 0x1C),
            )
        )

    return CmbSklInfo(
        offset=offset,
        size=size,
        bone_count=bone_count,
        flags=flags,
        bones=tuple(bones),
    )


def read_mshs_meshes(data, mshs_offset):
    _expect_magic(data, mshs_offset, MSHS_MAGIC, "mshs")
    mesh_count = _read_u32(data, mshs_offset + 8)
    meshes = []
    for index in range(mesh_count):
        offset = mshs_offset + 0x10 + index * 4
        sepd_index, material_index, visibility_id = struct.unpack_from("<HBB", data, offset)
        meshes.append(
            CmbMeshInfo(
                index=index,
                sepd_index=sepd_index,
                material_index=material_index,
                visibility_id=visibility_id,
            )
        )
    return tuple(meshes)


def read_shp_info(data, shp_offset):
    _expect_magic(data, shp_offset, SHP_MAGIC, "shp")
    size = _read_u32(data, shp_offset + 4)
    sepd_count = _read_u32(data, shp_offset + 8)
    flags = _read_u32(data, shp_offset + 0x0C)
    sepd_offsets = struct.unpack_from(f"<{sepd_count}H", data, shp_offset + 0x10)
    return CmbShpInfo(
        offset=shp_offset,
        size=size,
        sepd_count=sepd_count,
        flags=flags,
        sepd_offsets=tuple(sepd_offsets),
    )


def _read_vertex_list(data, offset, name):
    return CmbVertexListInfo(
        name=name,
        offset=_read_u32(data, offset),
        scale=_read_f32(data, offset + 4),
        data_type=struct.unpack_from("<H", data, offset + 8)[0],
        mode=struct.unpack_from("<H", data, offset + 0x0A)[0],
        constant=_read_vector4(data, offset + 0x0C),
    )


def _read_prm(data, prm_offset):
    if data[prm_offset : prm_offset + 4] != PRM_MAGIC:
        return None

    return CmbPrmInfo(
        offset=prm_offset,
        size=_read_u32(data, prm_offset + 4),
        is_visible=_read_u32(data, prm_offset + 8),
        primitive_mode=_read_u32(data, prm_offset + 0x0C),
        data_type=struct.unpack_from("<H", data, prm_offset + 0x10)[0],
        unknown=struct.unpack_from("<H", data, prm_offset + 0x12)[0],
        index_count=struct.unpack_from("<H", data, prm_offset + 0x14)[0],
        first_index=struct.unpack_from("<H", data, prm_offset + 0x16)[0],
    )


def _read_prms(data, prms_offset):
    _expect_magic(data, prms_offset, PRMS_MAGIC, "prms")
    size = _read_u32(data, prms_offset + 4)
    raw_words = struct.unpack_from("<5I", data, prms_offset + 8)
    skinning_mode = raw_words[1] & 0xFFFF
    bone_count = (raw_words[1] >> 16) & 0xFFFF
    bone_indices_offset = raw_words[2]
    prm_offset = raw_words[3]
    bone_indices = ()
    if bone_count and bone_indices_offset + bone_count * 2 <= size:
        bone_indices = struct.unpack_from(
            f"<{bone_count}H", data, prms_offset + bone_indices_offset
        )
    prm = None
    for rel_offset in raw_words:
        if 0 < rel_offset < size and data[prms_offset + rel_offset : prms_offset + rel_offset + 4] == PRM_MAGIC:
            prm = _read_prm(data, prms_offset + rel_offset)
            break
    return CmbPrmsInfo(
        offset=prms_offset,
        size=size,
        raw_header_words=tuple(raw_words),
        skinning_mode=skinning_mode,
        bone_count=bone_count,
        bone_indices_offset=bone_indices_offset,
        prm_offset=prm_offset,
        bone_indices=tuple(bone_indices),
        prm=prm,
    )


def read_sepd_info(data, shp_offset, sepd_index, sepd_rel_offset):
    offset = shp_offset + sepd_rel_offset
    _expect_magic(data, offset, SEPD_MAGIC, "sepd")
    prms_count = struct.unpack_from("<H", data, offset + 8)[0]
    flags = struct.unpack_from("<H", data, offset + 0x0A)[0]
    vertex_lists = (
        _read_vertex_list(data, offset + 0x24, "positions"),
        _read_vertex_list(data, offset + 0x40, "normals"),
        _read_vertex_list(data, offset + 0x5C, "colors"),
        _read_vertex_list(data, offset + 0x78, "uv0"),
        _read_vertex_list(data, offset + 0x94, "uv1"),
        _read_vertex_list(data, offset + 0xB0, "uv2"),
        _read_vertex_list(data, offset + 0xCC, "bone_indices"),
        _read_vertex_list(data, offset + 0xE8, "bone_weights"),
    )
    prms_offsets = struct.unpack_from(f"<{prms_count}H", data, offset + 0x108)
    return CmbSepdInfo(
        index=sepd_index,
        offset=offset,
        size=_read_u32(data, offset + 4),
        prms_count=prms_count,
        flags=flags,
        center=_read_vector3(data, offset + 0x0C),
        position_offset=_read_vector3(data, offset + 0x18),
        vertex_lists=vertex_lists,
        bone_dimension=struct.unpack_from("<H", data, offset + 0x104)[0],
        auto_flags=struct.unpack_from("<H", data, offset + 0x106)[0],
        prms_offsets=tuple(prms_offsets),
        prms=tuple(_read_prms(data, offset + rel_offset) for rel_offset in prms_offsets),
    )


def read_vatr_entries(data, header):
    vatr_offset = header.vatr_offset
    _expect_magic(data, vatr_offset, VATR_MAGIC, "vatr")
    names = (
        "positions",
        "normals",
        "colors",
        "uv0",
        "uv1",
        "uv2",
        "bone_indices",
        "bone_weights",
    )
    entries = []
    for index, name in enumerate(names):
        offset = vatr_offset + 0x0C + index * 8
        size, data_offset = struct.unpack_from("<II", data, offset)
        entries.append(
            CmbVatrEntry(
                name=name,
                size=size,
                data_offset=data_offset,
                absolute_data_offset=vatr_offset + data_offset if size else None,
            )
        )
    return tuple(entries)


def read_tex_info(data, header):
    tex_offset = header.tex_offset
    _expect_magic(data, tex_offset, TEX_MAGIC, "tex")
    size = _read_u32(data, tex_offset + 4)
    count = _read_u32(data, tex_offset + 8)
    textures = []

    for index in range(count):
        offset = tex_offset + 0x0C + index * 0x24
        data_offset = _read_u32(data, offset + 0x10)
        textures.append(
            CmbTextureInfo(
                index=index,
                offset=offset,
                data_size=_read_u32(data, offset),
                mipmap_count=struct.unpack_from("<H", data, offset + 4)[0],
                is_etc1=data[offset + 6],
                is_cubemap=data[offset + 7],
                width=struct.unpack_from("<H", data, offset + 8)[0],
                height=struct.unpack_from("<H", data, offset + 0x0A)[0],
                format=struct.unpack_from("<H", data, offset + 0x0C)[0],
                data_type=struct.unpack_from("<H", data, offset + 0x0E)[0],
                data_offset=data_offset,
                absolute_data_offset=header.texture_data_offset + data_offset,
                name=_read_fixed_ascii(data, offset + 0x14, 16),
            )
        )

    return CmbTexInfo(
        offset=tex_offset,
        size=size,
        texture_count=count,
        textures=tuple(textures),
    )


def _read_mat_texture(data, offset):
    return CmbMatTextureInfo(
        texture_index=struct.unpack_from("<h", data, offset)[0],
        min_filter=struct.unpack_from("<H", data, offset + 4)[0],
        mag_filter=struct.unpack_from("<H", data, offset + 6)[0],
        wrap_s=struct.unpack_from("<H", data, offset + 8)[0],
        wrap_t=struct.unpack_from("<H", data, offset + 0x0A)[0],
        min_lod_bias=_read_f32(data, offset + 0x0C),
        lod_bias=_read_f32(data, offset + 0x10),
        border_color=_read_rgba8(data, offset + 0x14),
    )


def _read_texture_coord(data, offset):
    return CmbTextureCoordInfo(
        matrix_mode=data[offset],
        reference_camera=data[offset + 1],
        mapping_method=data[offset + 2],
        coordinate_index=data[offset + 3],
        scale=struct.unpack_from("<ff", data, offset + 4),
        rotation=_read_f32(data, offset + 0x0C),
        translation=struct.unpack_from("<ff", data, offset + 0x10),
    )


def _material_stride(data, header, size, count):
    if count == 0:
        return 0

    payload_size = size - 0x0C
    if payload_size >= count * 0x15C:
        return 0x15C

    if payload_size % count == 0:
        return payload_size // count

    return payload_size // count


def read_mats_info(data, header):
    offset = header.mats_offset
    _expect_magic(data, offset, MATS_MAGIC, "mats")
    size = _read_u32(data, offset + 4)
    count = _read_u32(data, offset + 8)
    stride = _material_stride(data, header, size, count)
    materials = []

    if count and stride < 0x15C:
        raise CmbReadError(
            f"MATS material stride {stride:#x} is too small for documented OoT3D fields"
        )

    for index in range(count):
        material_offset = offset + 0x0C + index * stride
        material_end = material_offset + 0x15C
        if material_end > offset + size:
            raise CmbReadError(
                f"Material {index} exceeds MATS chunk bounds at {material_offset:#x}"
            )

        constant_colors = tuple(
            _read_rgba8(data, material_offset + 0xB4 + color_index * 4)
            for color_index in range(6)
        )
        materials.append(
            CmbMaterialInfo(
                index=index,
                offset=material_offset,
                fragment_lighting=bool(data[material_offset + 0x00]),
                vertex_lighting=bool(data[material_offset + 0x01]),
                is_fog_enabled=bool(data[material_offset + 0x02]),
                render_layer=data[material_offset + 0x03],
                face_culling=bool(data[material_offset + 0x04]),
                polygon_offset_enabled=bool(data[material_offset + 0x05]),
                polygon_offset=struct.unpack_from("<H", data, material_offset + 0x06)[0],
                texture_mappers_used=_read_u32(data, material_offset + 0x08),
                texture_coords_used=_read_u32(data, material_offset + 0x0C),
                textures=tuple(
                    _read_mat_texture(data, material_offset + 0x10 + texture_index * 0x18)
                    for texture_index in range(3)
                ),
                texture_coords=tuple(
                    _read_texture_coord(data, material_offset + 0x58 + coord_index * 0x18)
                    for coord_index in range(3)
                ),
                emission_color=_read_rgba8(data, material_offset + 0xA0),
                ambient_color=_read_rgba8(data, material_offset + 0xA4),
                diffuse_color=_read_rgba8(data, material_offset + 0xA8),
                specular0_color=_read_rgba8(data, material_offset + 0xAC),
                specular1_color=_read_rgba8(data, material_offset + 0xB0),
                constant_colors=constant_colors,
                buffer_color=_read_vector4(data, material_offset + 0xCC),
                used_tex_env_stages=_read_u32(data, material_offset + 0x120),
                tex_env_stage_indices=struct.unpack_from(
                    "<6h", data, material_offset + 0x124
                ),
                alpha_test_enabled=bool(data[material_offset + 0x130]),
                alpha_reference=data[material_offset + 0x131],
                alpha_function=struct.unpack_from("<H", data, material_offset + 0x132)[0],
                depth_test_enabled=bool(data[material_offset + 0x134]),
                depth_write_enabled=bool(data[material_offset + 0x135]),
                depth_function=struct.unpack_from("<H", data, material_offset + 0x136)[0],
                blend_mode=_read_u32(data, material_offset + 0x138),
                alpha_src_function=struct.unpack_from("<H", data, material_offset + 0x13C)[0],
                alpha_dst_function=struct.unpack_from("<H", data, material_offset + 0x13E)[0],
                alpha_equation=_read_u32(data, material_offset + 0x140),
                color_src_function=struct.unpack_from("<H", data, material_offset + 0x144)[0],
                color_dst_function=struct.unpack_from("<H", data, material_offset + 0x146)[0],
                color_equation=_read_u32(data, material_offset + 0x148),
                blend_color=_read_vector4(data, material_offset + 0x14C),
            )
        )

    env_start = offset + 0x0C + count * stride
    env_bytes = max(0, header.tex_offset - env_start)
    env_count = env_bytes // 0x28
    texture_envs = []
    for env_index in range(env_count):
        env_offset = env_start + env_index * 0x28
        raw_words = struct.unpack_from("<20H", data, env_offset)
        texture_envs.append(
            CmbTextureEnvInfo(
                index=env_index,
                offset=env_offset,
                combine_rgb=raw_words[0],
                combine_alpha=raw_words[1],
                source_rgb=raw_words[6:9],
                operand_rgb=raw_words[9:12],
                source_alpha=raw_words[12:15],
                operand_alpha=raw_words[15:18],
                raw_words=raw_words,
            )
        )

    trailing_bytes = env_bytes
    return CmbMatsInfo(
        offset=offset,
        size=size,
        material_count=count,
        material_stride=stride,
        trailing_bytes=trailing_bytes,
        materials=tuple(materials),
        texture_envs=tuple(texture_envs),
    )


def read_cmb_file(path):
    data = Path(path).read_bytes()
    header = read_cmb_header(data)
    chunks = read_top_level_chunks(data, header)
    return header, chunks
