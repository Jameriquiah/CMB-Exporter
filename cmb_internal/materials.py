from .model import CmbMaterial
from .material_presets import ensure_stage_slots, stage_settings_to_words
from .properties import is_cmb_material_settings
from .texture_slots import TEXTURE_SLOT_INDICES, texture_slot_prefix, texture_slot_values


TEXTURE_COORD_MAPPING_VALUES = {
    "NONE": 0,
    "UV": 1,
    "REFLECTION": 3,
    "0": 0,
    "1": 1,
    "3": 3,
}
MATERIAL_TEXTURE_FIELDS = (
    "image",
    "format",
    "min_filter",
    "mag_filter",
    "wrap_u",
    "wrap_v",
    "coord_matrix_mode",
    "coord_reference_camera",
    "coord_mapping",
    "coord_source",
    "coord_scale",
    "coord_rotation",
    "coord_translation",
)


def _texture_coord_mapping_value(value):
    return TEXTURE_COORD_MAPPING_VALUES.get(str(value), 0)


def _float_color_to_rgba8(color):
    return tuple(max(0, min(255, round(channel * 255))) for channel in color)


def _float_color_to_vector4(color):
    return tuple(float(channel) for channel in color)


def default_material():
    return CmbMaterial(name="Default CMB Material")


def _texture_slot_kwargs(settings, slot_index):
    (
        image,
        texture_format,
        min_filter,
        mag_filter,
        wrap_u,
        wrap_v,
        coord_matrix_mode,
        coord_reference_camera,
        coord_mapping,
        coord_source,
        coord_scale,
        coord_rotation,
        coord_translation,
    ) = texture_slot_values(
        settings,
        slot_index,
        *MATERIAL_TEXTURE_FIELDS,
    )
    values = {
        "format": texture_format,
        "image_name": image.name if image else "",
        "min_filter": min_filter,
        "mag_filter": mag_filter,
        "wrap_u": wrap_u,
        "wrap_v": wrap_v,
        "coord_matrix_mode": coord_matrix_mode,
        "coord_reference_camera": coord_reference_camera,
        "coord_mapping": _texture_coord_mapping_value(coord_mapping),
        "coord_source": coord_source,
        "coord_scale": tuple(coord_scale),
        "coord_rotation": coord_rotation,
        "coord_translation": tuple(coord_translation),
    }
    prefix = texture_slot_prefix(slot_index)
    return {f"{prefix}_{field}": value for field, value in values.items()}


def material_from_blender(material):
    settings = material.cmb_settings
    if not is_cmb_material_settings(settings):
        raise ValueError(f"Material is not a CMB material: {material.name}")

    ensure_stage_slots(settings)
    editable_stages = tuple(
        stage_settings_to_words(settings.tex_env_stages[index])
        for index in range(min(settings.tex_env_stage_count, len(settings.tex_env_stages)))
    )
    kwargs = {"name": material.name}
    for slot_index in TEXTURE_SLOT_INDICES:
        kwargs.update(_texture_slot_kwargs(settings, slot_index))
    kwargs.update({
        "fragment_lighting": settings.fragment_lighting,
        "vertex_lighting": settings.vertex_lighting,
        "is_fog_enabled": settings.is_fog_enabled,
        "render_layer": settings.render_layer,
        "face_culling": settings.face_culling,
        "polygon_offset_enabled": settings.polygon_offset_enabled,
        "polygon_offset": settings.polygon_offset,
        "emission_color": _float_color_to_rgba8(settings.emission_color),
        "ambient_color": _float_color_to_rgba8(settings.ambient_color),
        "diffuse_color": _float_color_to_rgba8(settings.diffuse_color),
        "specular0_color": _float_color_to_rgba8(settings.specular0_color),
        "specular1_color": _float_color_to_rgba8(settings.specular1_color),
        "constant_colors": (
            _float_color_to_rgba8(settings.constant0_color),
            _float_color_to_rgba8(settings.constant1_color),
            _float_color_to_rgba8(settings.constant2_color),
            _float_color_to_rgba8(settings.constant3_color),
            _float_color_to_rgba8(settings.constant4_color),
            _float_color_to_rgba8(settings.constant5_color),
        ),
        "buffer_color": _float_color_to_vector4(settings.buffer_color),
        "alpha_test_enabled": settings.alpha_test_enabled,
        "alpha_reference": settings.alpha_reference,
        "alpha_function": settings.alpha_function,
        "depth_test_enabled": settings.depth_test_enabled,
        "depth_write_enabled": settings.depth_write_enabled,
        "depth_function": settings.depth_function,
        "blend_mode": settings.blend_mode,
        "blend_alpha_src_function": settings.blend_alpha_src_function,
        "blend_alpha_dst_function": settings.blend_alpha_dst_function,
        "blend_alpha_equation": settings.blend_alpha_equation,
        "blend_color_src_function": settings.blend_color_src_function,
        "blend_color_dst_function": settings.blend_color_dst_function,
        "blend_color_equation": settings.blend_color_equation,
        "blend_color": _float_color_to_vector4(settings.blend_color),
        "tex_env_stages": editable_stages,
    })
    return CmbMaterial(**kwargs)
