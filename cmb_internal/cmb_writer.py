from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from .binary import BinaryWriter
from .cmb_constants import (
    CMB_MAGIC,
    CMB_VERSION_OOT3D,
    BlendEquation,
    BlendFactor,
    LUTS_MAGIC,
    MATS_MAGIC,
    MSHS_MAGIC,
    PicaDataType,
    PRM_MAGIC,
    PRMS_MAGIC,
    PrimitiveMode,
    SEPD_MAGIC,
    SepdFlags,
    SHP_MAGIC,
    SKL_MAGIC,
    SKLM_MAGIC,
    TEX_MAGIC,
    VATR_MAGIC,
    TestFunction,
    TextureEnvCombine,
    TextureEnvOperandAlpha,
    TextureEnvOperandRgb,
    TextureEnvSource,
    TextureMagFilter,
    TextureMinFilter,
    TextureWrapMode,
)
from .texture_slots import iter_texture_slot_values


MATERIAL_RECORD_SIZE = 0x15C
MAX_PRIMITIVE_BONES = 10


class CmbWriteError(ValueError):
    pass


@dataclass(frozen=True)
class CmbWriteStats:
    filepath: str
    file_size: int
    bone_count: int
    vertex_count: int
    triangle_count: int
    material_count: int
    mesh_count: int
    visibility_id_count: int
    split_meshes: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ShapeWriteInfo:
    primitive: object
    vertices: tuple
    prms: tuple
    vertex_start: int
    bone_data_start: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    center: tuple[float, float, float]
    bone_palette: tuple[int, ...]
    bone_dimension: int
    skinning_mode: int
    has_colors: bool
    uv0_scale: float


@dataclass(frozen=True)
class PrmsWriteInfo:
    indices: tuple[int, ...]
    index_start: int
    bone_palette: tuple[int, ...]
    skinning_mode: int


@dataclass(frozen=True)
class VatrLayout:
    total_vertices: int
    has_colors: bool
    positions_size: int
    normals_size: int
    colors_size: int
    uv0_size: int
    bone_indices_size: int
    bone_weights_size: int
    positions_offset: int
    normals_offset: int
    colors_offset: int
    uv0_offset: int
    bone_indices_offset: int
    bone_weights_offset: int


def _start_chunk(writer, magic, count=None):
    writer.align(4)
    start = writer.offset
    writer.write_magic(magic)
    size_offset = writer.reserve_u32()
    if count is not None:
        writer.write_u32(count)
    return start, size_offset


def _end_chunk(writer, start, size_offset):
    writer.align(4)
    writer.patch_u32(size_offset, writer.offset - start)


def _write_skl_chunk(writer, model):
    start, size_offset = _start_chunk(writer, SKL_MAGIC, len(model.bones))
    writer.write_u32(0)
    for bone_index, bone in enumerate(model.bones):
        writer.write_s16(bone_index)
        writer.write_s16(bone.parent_index)
        writer.write_vector3(bone.scale)
        writer.write_vector3(bone.rotation)
        writer.write_vector3(bone.translation)
    _end_chunk(writer, start, size_offset)
    return start


def _write_bool(writer, value):
    writer.write_u8(1 if value else 0)


def _test_function_value(name, default):
    try:
        return TestFunction[name]
    except KeyError:
        return default


def _blend_settings(material):
    return {
        "blend_mode": 0 if material.blend_mode == "OPAQUE" else 1,
        "alpha_src": _enum_value(BlendFactor, material.blend_alpha_src_function, BlendFactor.SRC_ALPHA),
        "alpha_dst": _enum_value(BlendFactor, material.blend_alpha_dst_function, BlendFactor.ONE_MINUS_SRC_ALPHA),
        "alpha_equation": _enum_value(BlendEquation, material.blend_alpha_equation, BlendEquation.FUNC_ADD),
        "color_src": _enum_value(BlendFactor, material.blend_color_src_function, BlendFactor.ONE),
        "color_dst": _enum_value(BlendFactor, material.blend_color_dst_function, BlendFactor.ZERO),
        "color_equation": _enum_value(BlendEquation, material.blend_color_equation, BlendEquation.FUNC_ADD),
    }


def _enum_value(enum_type, name, default):
    try:
        return enum_type[name]
    except KeyError:
        return default


def _write_mat_texture(
    writer,
    texture_index=-1,
    min_filter="LINEAR",
    mag_filter="LINEAR",
    wrap_u="REPEAT",
    wrap_v="REPEAT",
):
    if texture_index < 0:
        writer.write_s16(-1)
        writer.write_s16(0)
        writer.write_u16(0)
        writer.write_u16(0)
        writer.write_u16(0)
        writer.write_u16(0)
        writer.write_f32(0.0)
        writer.write_f32(0.0)
        writer.write_rgba8((0, 0, 0, 0))
        return

    writer.write_s16(texture_index)
    writer.write_s16(0)
    writer.write_u16(_enum_value(TextureMinFilter, min_filter, TextureMinFilter.LINEAR))
    writer.write_u16(_enum_value(TextureMagFilter, mag_filter, TextureMagFilter.LINEAR))
    writer.write_u16(_enum_value(TextureWrapMode, wrap_u, TextureWrapMode.REPEAT))
    writer.write_u16(_enum_value(TextureWrapMode, wrap_v, TextureWrapMode.REPEAT))
    writer.write_f32(0.0)
    writer.write_f32(0.0)
    writer.write_rgba8((0, 0, 0, 255))


def _write_texture_coord(writer, coord, active=False):
    matrix_mode, reference_camera, mapping_method, coordinate_index, scale, rotation, translation = coord
    writer.write_u8(matrix_mode if active else 0)
    writer.write_u8(reference_camera if active else 0)
    writer.write_u8(mapping_method if active else 0)
    writer.write_u8(coordinate_index if active else 0)
    writer.write_vector2(scale)
    writer.write_f32(rotation)
    writer.write_vector2(translation)


def _write_sampler(writer):
    writer.write_u8(1)
    writer.write_u8(0xFF)
    writer.write_u16(0x62A0)
    writer.write_f32(1.0)


def _write_material_support_settings(writer):
    writer.write_u16(TextureEnvSource.TEXTURE0)
    writer.write_u16(0x62C8)
    writer.write_u16(0)
    writer.write_u16(0)
    writer.write_u16(0x62B0)
    writer.write_u16(0)
    writer.write_u16(0x62C0)


def _texture_source(slot):
    return (
        TextureEnvSource.TEXTURE0,
        TextureEnvSource.TEXTURE1,
        TextureEnvSource.TEXTURE2,
    )[slot]


def _env_stage(
    combine_rgb,
    combine_alpha,
    sources_rgb,
    sources_alpha,
    operands_rgb=(
        TextureEnvOperandRgb.SRC_COLOR,
        TextureEnvOperandRgb.SRC_COLOR,
        TextureEnvOperandRgb.SRC_COLOR,
    ),
    operands_alpha=(
        TextureEnvOperandAlpha.SRC_ALPHA,
        TextureEnvOperandAlpha.SRC_ALPHA,
        TextureEnvOperandAlpha.SRC_ALPHA,
    ),
    scale_rgb=1,
    scale_alpha=1,
    constant_color_index=0,
):
    return (
        combine_rgb,
        combine_alpha,
        scale_rgb,
        scale_alpha,
        0x8579,
        0x8579,
        sources_rgb[0],
        sources_rgb[1],
        sources_rgb[2],
        operands_rgb[0],
        operands_rgb[1],
        operands_rgb[2],
        sources_alpha[0],
        sources_alpha[1],
        sources_alpha[2],
        operands_alpha[0],
        operands_alpha[1],
        operands_alpha[2],
        constant_color_index,
        0,
    )


def _material_env_stages(material):
    texture_indices = tuple(
        texture_index
        for _slot_index, (texture_index,) in iter_texture_slot_values(material, "index")
    )
    active_slots = [
        index for index, texture_index in enumerate(texture_indices) if texture_index >= 0
    ]

    if not active_slots:
        return (
            _env_stage(
                TextureEnvCombine.REPLACE,
                TextureEnvCombine.REPLACE,
                (
                    TextureEnvSource.PRIMARY_COLOR,
                    TextureEnvSource.PRIMARY_COLOR,
                    TextureEnvSource.PRIMARY_COLOR,
                ),
                (
                    TextureEnvSource.PRIMARY_COLOR,
                    TextureEnvSource.PRIMARY_COLOR,
                    TextureEnvSource.PRIMARY_COLOR,
                ),
            ),
        )

    if material.tex_env_stages:
        return tuple(tuple(stage) for stage in material.tex_env_stages)

    stages = [
        _env_stage(
            TextureEnvCombine.REPLACE,
            TextureEnvCombine.REPLACE,
            (
                _texture_source(active_slots[0]),
                TextureEnvSource.PRIMARY_COLOR,
                TextureEnvSource.PRIMARY_COLOR,
            ),
            (
                _texture_source(active_slots[0]),
                TextureEnvSource.PRIMARY_COLOR,
                TextureEnvSource.PRIMARY_COLOR,
            ),
        )
    ]

    return tuple(stages)


def _write_tex_env_setting(writer, stage):
    for value in stage:
        writer.write_u16(value)


def _write_mats_chunk(writer, model):
    start, size_offset = _start_chunk(writer, MATS_MAGIC, len(model.materials))
    material_envs = [_material_env_stages(material) for material in model.materials]
    env_start_indices = []
    env_count = 0
    for stages in material_envs:
        env_start_indices.append(env_count)
        env_count += len(stages)

    for material_index, material in enumerate(model.materials):
        material_start = writer.offset
        blend = _blend_settings(material)

        _write_bool(writer, material.fragment_lighting)
        _write_bool(writer, material.vertex_lighting)
        _write_bool(writer, material.hemisphere_lighting)
        _write_bool(writer, material.hemisphere_occlusion)
        _write_bool(writer, material.face_culling)
        _write_bool(writer, material.polygon_offset_enabled)
        writer.write_u16(material.polygon_offset)
        texture_indices = tuple(
            texture_index
            for _slot_index, (texture_index,) in iter_texture_slot_values(material, "index")
        )
        texture_coords = tuple(
            values
            for _slot_index, values in iter_texture_slot_values(
                material,
                "coord_matrix_mode",
                "coord_reference_camera",
                "coord_mapping",
                "coord_source",
                "coord_scale",
                "coord_rotation",
                "coord_translation",
            )
        )
        texture_sampler_settings = tuple(
            values
            for _slot_index, values in iter_texture_slot_values(
                material, "min_filter", "mag_filter", "wrap_u", "wrap_v"
            )
        )
        texture_mappers_used = sum(
            1 for texture_index in texture_indices if texture_index >= 0
        )
        writer.write_u32(texture_mappers_used)
        writer.write_u32(texture_mappers_used)
        for texture_index, sampler_settings in zip(texture_indices, texture_sampler_settings):
            _write_mat_texture(writer, texture_index, *sampler_settings)
        for texture_coord, texture_index in zip(texture_coords, texture_indices):
            _write_texture_coord(writer, texture_coord, texture_index >= 0)
        writer.write_rgba8(material.emission_color)
        writer.write_rgba8(material.ambient_color)
        writer.write_rgba8(material.diffuse_color)
        writer.write_rgba8(material.specular0_color)
        writer.write_rgba8(material.specular1_color)
        for color in material.constant_colors:
            writer.write_rgba8(color)
        writer.write_vector4(material.buffer_color)
        _write_material_support_settings(writer)
        for _ in range(6):
            _write_bool(writer, False)
        for _ in range(6):
            _write_sampler(writer)
        stages = material_envs[material_index]
        writer.write_u32(len(stages))
        for stage_index in range(6):
            if stage_index < len(stages):
                writer.write_s16(env_start_indices[material_index] + stage_index)
            else:
                writer.write_s16(-1)
        _write_bool(writer, material.alpha_test_enabled)
        writer.write_u8(material.alpha_reference)
        writer.write_u16(_test_function_value(material.alpha_function, TestFunction.ALWAYS))
        _write_bool(writer, material.depth_test_enabled)
        _write_bool(writer, material.depth_write_enabled)
        writer.write_u16(_test_function_value(material.depth_function, TestFunction.LEQUAL))
        writer.write_u32(blend["blend_mode"])
        writer.write_u16(blend["alpha_src"])
        writer.write_u16(blend["alpha_dst"])
        writer.write_u32(blend["alpha_equation"])
        writer.write_u16(blend["color_src"])
        writer.write_u16(blend["color_dst"])
        writer.write_u32(blend["color_equation"])
        writer.write_vector4(material.blend_color)
        written = writer.offset - material_start
        if written != MATERIAL_RECORD_SIZE:
            raise CmbWriteError(
                "Internal material writer error: "
                f"wrote {written:#x} bytes, expected {MATERIAL_RECORD_SIZE:#x}"
            )
    for stages in material_envs:
        for stage in stages:
            _write_tex_env_setting(writer, stage)
    _end_chunk(writer, start, size_offset)
    return start


def _write_tex_chunk(writer, model):
    start, size_offset = _start_chunk(writer, TEX_MAGIC, len(model.textures))
    data_offset = 0
    for texture in model.textures:
        encoded = texture.encoded
        writer.write_u32(len(encoded.data))
        writer.write_u16(encoded.mipmap_count)
        writer.write_u8(encoded.is_etc1)
        writer.write_u8(0)
        writer.write_u16(encoded.width)
        writer.write_u16(encoded.height)
        writer.write_u16(encoded.texture_format)
        writer.write_u16(encoded.data_type)
        writer.write_u32(data_offset)
        writer.write_fixed_ascii(texture.name, 16)
        data_offset += len(encoded.data)
    _end_chunk(writer, start, size_offset)
    return start


def _bounds_from_vertices(vertices):
    positions = [vertex.position for vertex in vertices]
    mins = tuple(min(position[axis] for position in positions) for axis in range(3))
    maxs = tuple(max(position[axis] for position in positions) for axis in range(3))
    return mins, maxs


def _center_from_bounds(bounds_min, bounds_max):
    return tuple((bounds_min[axis] + bounds_max[axis]) * 0.5 for axis in range(3))


def _shape_bone_palette(vertices):
    palette = []
    for vertex in vertices:
        for bone_index, weight in zip(vertex.bone_indices, vertex.bone_weights):
            if weight <= 0:
                continue
            if bone_index not in palette:
                palette.append(bone_index)

    if not palette:
        palette.append(0)

    if len(palette) > MAX_PRIMITIVE_BONES:
        raise CmbWriteError(
            "Current PRMS writer supports at most "
            f"{MAX_PRIMITIVE_BONES} unique bones per mesh primitive"
        )

    return tuple(palette)


def _vertex_bone_set(vertex):
    return {
        bone_index
        for bone_index, weight in zip(vertex.bone_indices, vertex.bone_weights)
        if weight > 0
    } or {0}


def _triangle_bone_set(model, triangle_indices):
    bones = set()
    for source_index in triangle_indices:
        bones.update(_vertex_bone_set(model.vertices[source_index]))
    return bones


def _split_primitive_indices_by_bone_palette(
    model, primitive, max_bones=MAX_PRIMITIVE_BONES
):
    chunks = []
    current_indices = []
    current_bones = set()

    for triangle_start in range(0, len(primitive.indices), 3):
        triangle = primitive.indices[triangle_start : triangle_start + 3]
        if len(triangle) != 3:
            raise CmbWriteError(
                f"Mesh '{primitive.mesh_name}' has a primitive with a non-triangle index tail"
            )

        triangle_bones = _triangle_bone_set(model, triangle)
        if len(triangle_bones) > max_bones:
            raise CmbWriteError(
                f"Mesh '{primitive.mesh_name}' has one triangle using {len(triangle_bones)} unique bones; "
                f"CMB PRMS supports at most {max_bones} bones per primitive"
            )

        combined_bones = current_bones | triangle_bones
        if current_indices and len(combined_bones) > max_bones:
            chunks.append(tuple(current_indices))
            current_indices = list(triangle)
            current_bones = set(triangle_bones)
        else:
            current_indices.extend(triangle)
            current_bones = combined_bones

    if current_indices:
        chunks.append(tuple(current_indices))

    return tuple(chunks)


def _vertex_influence_count(vertex):
    return max(1, sum(1 for weight in vertex.bone_weights if weight > 0))


def _shape_bone_dimension_from_palettes(vertices, palettes):
    max_influences = max(_vertex_influence_count(vertex) for vertex in vertices)
    max_palette_size = max((len(palette) for palette in palettes), default=1)
    if max_palette_size == 1 and max_influences == 1:
        return 1
    return max(2, max_influences)


def _transform_point(matrix, point):
    return tuple(
        sum(matrix[row][column] * point[column] for column in range(3)) + matrix[row][3]
        for row in range(3)
    )


def _transform_vector(matrix, vector):
    return tuple(
        sum(matrix[row][column] * vector[column] for column in range(3))
        for row in range(3)
    )


def _normalize_vector(vector):
    length = sum(component * component for component in vector) ** 0.5
    if length <= 0.0:
        return vector
    return tuple(component / length for component in vector)


def _vertex_for_skinning_mode(model, vertex, skinning_mode, bone_palette):
    if skinning_mode != 0 or len(bone_palette) != 1:
        return vertex

    inverse_bind_matrix = model.bones[bone_palette[0]].inverse_bind_matrix
    normal = vertex.normal
    return vertex.__class__(
        position=_transform_point(inverse_bind_matrix, vertex.position),
        normal=None if normal is None else _normalize_vector(_transform_vector(inverse_bind_matrix, normal)),
        color=vertex.color,
        uv0=vertex.uv0,
        bone_indices=vertex.bone_indices,
        bone_weights=vertex.bone_weights,
    )


def _vertex_for_prms(model, vertex, skinning_mode, bone_palette):
    if skinning_mode == 0:
        return _vertex_for_skinning_mode(model, vertex, skinning_mode, bone_palette)

    palette_lookup = {
        bone_index: palette_index
        for palette_index, bone_index in enumerate(bone_palette)
    }
    return vertex.__class__(
        position=vertex.position,
        normal=vertex.normal,
        color=vertex.color,
        uv0=vertex.uv0,
        bone_indices=tuple(palette_lookup.get(bone_index, 0) for bone_index in vertex.bone_indices),
        bone_weights=vertex.bone_weights,
    )


def _align4_size(size):
    return (size + 3) & ~3


def _shape_uv0_scale(vertices):
    max_abs = 0.0
    for vertex in vertices:
        uv = vertex.uv0 or (0.0, 0.0)
        if not isfinite(uv[0]) or not isfinite(uv[1]):
            continue
        max_abs = max(max_abs, abs(uv[0]), abs(uv[1]))
    if max_abs <= 0.0:
        return 1.0
    return max_abs / 32767.0


def _build_shape_write_info(model):
    shapes = []
    vertex_start = 0
    index_start = 0
    bone_data_start = 0
    split_counts = {}

    for primitive in model.primitives:
        primitive_chunks = _split_primitive_indices_by_bone_palette(model, primitive)
        if len(primitive_chunks) > 1:
            split_counts[primitive.mesh_name] = len(primitive_chunks)

        chunk_palettes = [
            _shape_bone_palette(model.vertices[source_index] for source_index in primitive_indices)
            for primitive_indices in primitive_chunks
        ]
        source_vertices = [
            model.vertices[source_index]
            for primitive_indices in primitive_chunks
            for source_index in primitive_indices
        ]
        bone_dimension = _shape_bone_dimension_from_palettes(source_vertices, chunk_palettes)

        local_vertices = []
        local_chunk_indices = []
        prms = []

        for primitive_indices, bone_palette in zip(primitive_chunks, chunk_palettes):
            skinning_mode = 0 if len(bone_palette) == 1 and bone_dimension == 1 else 2
            local_lookup = {}
            local_indices = []
            for source_index in primitive_indices:
                vertex = _vertex_for_prms(
                    model,
                    model.vertices[source_index],
                    skinning_mode,
                    bone_palette,
                )
                local_index = local_lookup.get(vertex)
                if local_index is None:
                    local_index = len(local_vertices)
                    local_lookup[vertex] = local_index
                    local_vertices.append(vertex)
                local_indices.append(local_index)
            local_chunk_indices.append(tuple(local_indices))
            prms.append(
                PrmsWriteInfo(
                    indices=local_indices,
                    index_start=index_start,
                    bone_palette=bone_palette,
                    skinning_mode=skinning_mode,
                )
            )
            index_start += len(local_indices)

        if len(local_vertices) > 0xFFFF:
            raise CmbWriteError(
                f"Mesh '{primitive.mesh_name}' has {len(local_vertices)} vertices; U16 indices support at most 65535"
            )

        shape_skinning_mode = 0 if all(prm.skinning_mode == 0 for prm in prms) else 2
        shape_palette = chunk_palettes[0] if shape_skinning_mode == 0 and chunk_palettes else (0,)
        bounds_min, bounds_max = _bounds_from_vertices(local_vertices)
        shapes.append(
            ShapeWriteInfo(
                primitive=primitive,
                vertices=tuple(local_vertices),
                prms=tuple(prms),
                vertex_start=vertex_start,
                bone_data_start=bone_data_start,
                bounds_min=bounds_min,
                bounds_max=bounds_max,
                center=_center_from_bounds(bounds_min, bounds_max),
                bone_palette=shape_palette,
                bone_dimension=bone_dimension,
                skinning_mode=shape_skinning_mode,
                has_colors=any(vertex.color is not None for vertex in local_vertices),
                uv0_scale=_shape_uv0_scale(local_vertices),
            )
        )
        vertex_start += len(local_vertices)
        if shape_skinning_mode != 0:
            bone_data_start += len(local_vertices) * bone_dimension

    return tuple(shapes), tuple(sorted(split_counts.items()))


def _build_vatr_layout(shapes):
    total_vertices = sum(len(shape.vertices) for shape in shapes)
    has_colors = any(shape.has_colors for shape in shapes)
    positions_size = total_vertices * 12
    normals_size = _align4_size(total_vertices * 3)
    colors_size = total_vertices * 4 if has_colors else 0
    uv0_size = total_vertices * 4
    bone_indices_raw_size = sum(
        len(shape.vertices) * shape.bone_dimension
        for shape in shapes
        if shape.skinning_mode != 0
    )
    bone_indices_size = _align4_size(bone_indices_raw_size)
    bone_weights_size = _align4_size(bone_indices_raw_size)
    positions_offset = 0x4C
    normals_offset = positions_offset + positions_size
    colors_offset = normals_offset + normals_size
    uv0_offset = colors_offset + colors_size
    bone_indices_offset = uv0_offset + uv0_size
    bone_weights_offset = bone_indices_offset + bone_indices_size
    return VatrLayout(
        total_vertices=total_vertices,
        has_colors=has_colors,
        positions_size=positions_size,
        normals_size=normals_size,
        colors_size=colors_size,
        uv0_size=uv0_size,
        bone_indices_size=bone_indices_size,
        bone_weights_size=bone_weights_size,
        positions_offset=positions_offset,
        normals_offset=normals_offset,
        colors_offset=colors_offset,
        uv0_offset=uv0_offset,
        bone_indices_offset=bone_indices_offset,
        bone_weights_offset=bone_weights_offset,
    )


def _write_mshs_chunk(writer, model, shapes):
    start, size_offset = _start_chunk(writer, MSHS_MAGIC)
    writer.write_u32(len(shapes))
    writer.write_u16(0)
    writer.write_u16(model.visibility_id_count)

    for shape_index, shape in enumerate(shapes):
        primitive = shape.primitive
        writer.write_u16(shape_index)
        writer.write_u8(primitive.material_index)
        writer.write_u8(primitive.visibility_id)

    _end_chunk(writer, start, size_offset)
    return start


def _write_vertex_list(writer, offset, scale, data_type, mode=0, constant=(0.0, 0.0, 0.0, 1.0)):
    writer.write_u32(offset)
    writer.write_f32(scale)
    writer.write_u16(data_type)
    writer.write_u16(mode)
    writer.write_vector4(constant)


def _write_prm_chunk(writer, prms):
    start, size_offset = _start_chunk(writer, PRM_MAGIC)
    writer.write_u32(1)
    writer.write_u32(PrimitiveMode.TRIANGLES)
    writer.write_u16(PicaDataType.U16)
    writer.write_u16(0)
    writer.write_u16(len(prms.indices))
    writer.write_u16(prms.index_start)
    _end_chunk(writer, start, size_offset)
    return start


def _pack_bone_pair(first, second=0):
    return (second << 16) | first


def _write_prms_chunk(writer, prms):
    start, size_offset = _start_chunk(writer, PRMS_MAGIC)
    palette = prms.bone_palette
    packed_palette = [
        _pack_bone_pair(palette[index], palette[index + 1] if index + 1 < len(palette) else 0)
        for index in range(0, len(palette), 2)
    ]
    prm_rel_offset = 0x18 + len(packed_palette) * 4

    writer.write_u32(1)
    writer.write_u32((len(palette) << 16) | prms.skinning_mode)
    writer.write_u32(0x18)
    writer.write_u32(prm_rel_offset)
    for packed in packed_palette:
        writer.write_u32(packed)
    _write_prm_chunk(writer, prms)
    _end_chunk(writer, start, size_offset)
    return start


def _write_sepd_chunk(writer, shape, vatr_layout):
    start, size_offset = _start_chunk(writer, SEPD_MAGIC)
    writer.write_u16(len(shape.prms))
    flags = SepdFlags.HAS_POSITION | SepdFlags.HAS_NORMALS | SepdFlags.HAS_UV0
    if shape.has_colors:
        flags |= SepdFlags.HAS_COLORS
    if shape.skinning_mode != 0:
        flags |= SepdFlags.HAS_INDICES | SepdFlags.HAS_WEIGHTS
    writer.write_u16(flags)
    writer.write_vector3(shape.center)
    writer.write_vector3((0.0, 0.0, 0.0))

    position_offset = shape.vertex_start * 12
    normal_offset = shape.vertex_start * 3
    color_offset = shape.vertex_start * 4 if vatr_layout.has_colors and shape.has_colors else 0
    uv0_offset = shape.vertex_start * 4
    bone_indices_offset = shape.bone_data_start if shape.skinning_mode != 0 else 0
    bone_weights_offset = shape.bone_data_start if shape.skinning_mode != 0 else 0

    _write_vertex_list(writer, position_offset, 1.0, PicaDataType.F32)
    _write_vertex_list(writer, normal_offset, 1.0 / 127.0, PicaDataType.S8)
    if shape.has_colors:
        _write_vertex_list(writer, color_offset, 1.0 / 255.0, PicaDataType.U8)
    else:
        _write_vertex_list(writer, 0, 1.0, PicaDataType.F32)
    _write_vertex_list(writer, uv0_offset, shape.uv0_scale, PicaDataType.S16)
    _write_vertex_list(writer, 0, 1.0, PicaDataType.F32)
    _write_vertex_list(writer, 0, 1.0, PicaDataType.F32)
    if shape.skinning_mode != 0:
        _write_vertex_list(writer, bone_indices_offset, 1.0, PicaDataType.U8)
        _write_vertex_list(writer, bone_weights_offset, 0.01, PicaDataType.U8)
    else:
        _write_vertex_list(writer, 0, 1.0, PicaDataType.F32)
        _write_vertex_list(writer, 0, 1.0, PicaDataType.F32)

    writer.write_u16(shape.bone_dimension)
    writer.write_u16(0)
    prms_pointer_offsets = []
    for _prms in shape.prms:
        prms_pointer_offsets.append(writer.offset)
        writer.write_u16(0)
    writer.align(4)
    for pointer_offset, prms in zip(prms_pointer_offsets, shape.prms):
        prms_start = _write_prms_chunk(writer, prms)
        prms_rel = prms_start - start
        if prms_rel > 0xFFFF:
            raise CmbWriteError("SEPD PRMS relative offsets exceeded u16 range")
        _patch_u16(writer, pointer_offset, prms_rel)
    _end_chunk(writer, start, size_offset)
    return start


def _patch_u16(writer, offset, value):
    writer._data[offset : offset + 2] = value.to_bytes(2, "little")


def _write_shp_chunk(writer, shapes, vatr_layout):
    start, size_offset = _start_chunk(writer, SHP_MAGIC, len(shapes))
    writer.write_u32(0)
    sepd_pointer_offsets = []
    for _shape in shapes:
        sepd_pointer_offsets.append(writer.offset)
        writer.write_u16(0)
    writer.align(4)

    for pointer_offset, shape in zip(sepd_pointer_offsets, shapes):
        sepd_start = _write_sepd_chunk(writer, shape, vatr_layout)
        sepd_rel = sepd_start - start
        if sepd_rel > 0xFFFF:
            raise CmbWriteError("SHP SEPD relative offsets exceeded u16 range")
        _patch_u16(writer, pointer_offset, sepd_rel)

    _end_chunk(writer, start, size_offset)
    return start

def _write_sklm_chunk(writer, model, shapes, vatr_layout):
    start, size_offset = _start_chunk(writer, SKLM_MAGIC)
    mshs_rel_offset = writer.reserve_u32()
    shp_rel_offset = writer.reserve_u32()

    mshs_start = _write_mshs_chunk(writer, model, shapes)
    shp_start = _write_shp_chunk(writer, shapes, vatr_layout)

    writer.patch_u32(mshs_rel_offset, mshs_start - start)
    writer.patch_u32(shp_rel_offset, shp_start - start)
    _end_chunk(writer, start, size_offset)
    return start


def _write_luts_chunk(writer):
    start, size_offset = _start_chunk(writer, LUTS_MAGIC, 0)
    writer.write_u32(0)
    _end_chunk(writer, start, size_offset)
    return start


def _write_vatr_entry(writer, size, offset):
    writer.write_u32(size)
    writer.write_u32(offset)


def _iter_shape_vertices(shapes):
    for shape in shapes:
        for vertex in shape.vertices:
            yield vertex


def _clamp_int(value, minimum, maximum):
    return max(minimum, min(maximum, int(round(value))))


def _write_padding(writer, size):
    for _index in range(size):
        writer.write_u8(0)


def _write_stream_padding(writer, raw_size):
    _write_padding(writer, _align4_size(raw_size) - raw_size)


def _write_vatr_chunk(writer, shapes, vatr_layout):
    start, size_offset = _start_chunk(writer, VATR_MAGIC, vatr_layout.total_vertices)
    _write_vatr_entry(writer, vatr_layout.positions_size, vatr_layout.positions_offset)
    _write_vatr_entry(writer, vatr_layout.normals_size, vatr_layout.normals_offset)
    _write_vatr_entry(writer, vatr_layout.colors_size, vatr_layout.colors_offset)
    _write_vatr_entry(writer, vatr_layout.uv0_size, vatr_layout.uv0_offset)
    current_end = vatr_layout.uv0_offset + vatr_layout.uv0_size
    _write_vatr_entry(writer, 0, current_end)
    _write_vatr_entry(writer, 0, current_end)
    _write_vatr_entry(writer, vatr_layout.bone_indices_size, vatr_layout.bone_indices_offset)
    _write_vatr_entry(writer, vatr_layout.bone_weights_size, vatr_layout.bone_weights_offset)

    for vertex in _iter_shape_vertices(shapes):
        writer.write_vector3(vertex.position)
    for vertex in _iter_shape_vertices(shapes):
        normal = vertex.normal or (0.0, 0.0, 1.0)
        writer.write_s8(_clamp_int(normal[0] * 127.0, -128, 127))
        writer.write_s8(_clamp_int(normal[1] * 127.0, -128, 127))
        writer.write_s8(_clamp_int(normal[2] * 127.0, -128, 127))
    _write_stream_padding(writer, vatr_layout.total_vertices * 3)
    if vatr_layout.has_colors:
        for vertex in _iter_shape_vertices(shapes):
            writer.write_rgba8(vertex.color or (255, 255, 255, 255))
    for shape in shapes:
        uv_scale = shape.uv0_scale
        for vertex in shape.vertices:
            uv = vertex.uv0 or (0.0, 0.0)
            if not isfinite(uv[0]) or not isfinite(uv[1]):
                uv = (0.0, 0.0)
            writer.write_s16(_clamp_int(uv[0] / uv_scale, -32768, 32767))
            writer.write_s16(_clamp_int(uv[1] / uv_scale, -32768, 32767))
    for shape in shapes:
        if shape.skinning_mode == 0:
            continue
        for vertex in shape.vertices:
            for bone_index in vertex.bone_indices[: shape.bone_dimension]:
                if bone_index > 0xFF:
                    raise CmbWriteError(
                        f"Bone palette index {bone_index} exceeds U8 range supported by current VATR writer"
                    )
                writer.write_u8(bone_index)
    _write_stream_padding(
        writer,
        sum(
            len(shape.vertices) * shape.bone_dimension
            for shape in shapes
            if shape.skinning_mode != 0
        ),
    )
    for shape in shapes:
        if shape.skinning_mode == 0:
            continue
        for vertex in shape.vertices:
            for bone_weight in vertex.bone_weights[: shape.bone_dimension]:
                if bone_weight > 0xFF:
                    raise CmbWriteError(
                        f"Bone weight {bone_weight} exceeds U8 range supported by current VATR writer"
                    )
                writer.write_u8(bone_weight)
    _write_stream_padding(
        writer,
        sum(
            len(shape.vertices) * shape.bone_dimension
            for shape in shapes
            if shape.skinning_mode != 0
        ),
    )
    _end_chunk(writer, start, size_offset)
    return start


def _write_indices(writer, shapes):
    writer.align(4)
    start = writer.offset
    for shape in shapes:
        for prms in shape.prms:
            for index in prms.indices:
                if index > 0xFFFF:
                    raise CmbWriteError(
                        f"CMB currently supports only U16 vertex indices; got index {index}"
                    )
                writer.write_u16(index)
    writer.align(4)
    return start


def _write_texture_data(writer, model):
    writer.align(4)
    start = writer.offset
    for texture in model.textures:
        writer.write(texture.encoded.data)
    writer.align(4)
    return start


def _write_header(writer, model, index_count):
    writer.write_magic(CMB_MAGIC)
    file_size_offset = writer.reserve_u32()
    writer.write_u32(CMB_VERSION_OOT3D)
    writer.write_u32(0)
    writer.write_fixed_ascii(model.name, 16)
    writer.write_u32(index_count)

    pointer_offsets = {
        "skl": writer.reserve_u32(),
        "mats": writer.reserve_u32(),
        "tex": writer.reserve_u32(),
        "sklm": writer.reserve_u32(),
        "luts": writer.reserve_u32(),
        "vatr": writer.reserve_u32(),
        "indices": writer.reserve_u32(),
        "textures": writer.reserve_u32(),
    }
    return file_size_offset, pointer_offsets


def _written_index_count(shapes):
    index_count = sum(len(prms.indices) for shape in shapes for prms in shape.prms)
    return index_count + (index_count & 1)


def write_cmb_file(model, filepath):
    triangle_count = sum(len(primitive.indices) // 3 for primitive in model.primitives)
    if not model.bones:
        raise CmbWriteError("Cannot write CMB without skeleton bones")
    if not model.vertices:
        raise CmbWriteError("Cannot write CMB without vertices")
    if not model.primitives:
        raise CmbWriteError("Cannot write CMB without mesh primitives")

    shapes, split_meshes = _build_shape_write_info(model)
    vatr_layout = _build_vatr_layout(shapes)
    index_count = _written_index_count(shapes)

    writer = BinaryWriter()
    file_size_offset, pointer_offsets = _write_header(writer, model, index_count)

    chunk_offsets = {
        "skl": _write_skl_chunk(writer, model),
        "mats": _write_mats_chunk(writer, model),
        "tex": _write_tex_chunk(writer, model),
        "sklm": _write_sklm_chunk(writer, model, shapes, vatr_layout),
        "luts": _write_luts_chunk(writer),
        "vatr": _write_vatr_chunk(writer, shapes, vatr_layout),
        "indices": _write_indices(writer, shapes),
    }
    chunk_offsets["textures"] = _write_texture_data(writer, model)

    for name, offset in chunk_offsets.items():
        writer.patch_u32(pointer_offsets[name], offset)

    writer.patch_u32(file_size_offset, writer.offset)

    path = Path(filepath)
    path.write_bytes(writer.bytes())

    return CmbWriteStats(
        filepath=str(path),
        file_size=writer.offset,
        bone_count=len(model.bones),
        vertex_count=len(model.vertices),
        triangle_count=triangle_count,
        material_count=len(model.materials),
        mesh_count=len(shapes),
        visibility_id_count=model.visibility_id_count,
        split_meshes=split_meshes,
    )
