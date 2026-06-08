from dataclasses import dataclass

from .texture_slots import TEXTURE_SLOT_INDICES, texture_slot_values


PREVIEW_VERSION = 8

PREVIEW_LIGHT_FLOOR = 0.72
PREVIEW_AMBIENT_WEIGHT = 0.28

ALPHA_BLEND_MODES = frozenset({"ALPHA", "ADD"})
CLAMP_WRAP_MODES = frozenset({"CLAMP", "CLAMP_TO_EDGE", "CLAMP_TO_BORDER"})
PREVIEW_TEXTURE_FIELDS = (
    "image",
    "min_filter",
    "mag_filter",
    "wrap_u",
    "wrap_v",
    "coord_mapping",
)
SIGNATURE_TEXTURE_FIELDS = ("format", *PREVIEW_TEXTURE_FIELDS[1:])


@dataclass(frozen=True)
class PreviewTexture:
    index: int
    image: object
    min_filter: str
    mag_filter: str
    wrap_u: str
    wrap_v: str
    coord_mapping: str

    @property
    def is_reflection(self):
        return self.coord_mapping == "REFLECTION"


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _rgba_tuple(color):
    return tuple(_clamp01(channel) for channel in color)


def _display_diffuse(color):
    diffuse = _rgba_tuple(color)
    max_rgb = max(diffuse[:3])
    if 0.0 < max_rgb < 1.0:
        rgb = tuple(_clamp01(channel / max_rgb) for channel in diffuse[:3])
    else:
        rgb = diffuse[:3]
    return (*rgb, diffuse[3])


def _preview_color(settings):
    diffuse = _display_diffuse(settings.diffuse_color)
    ambient = _rgba_tuple(settings.ambient_color)
    emission = _rgba_tuple(settings.emission_color)

    if settings.fragment_lighting or settings.vertex_lighting:
        light = tuple(
            min(
                1.0,
                PREVIEW_LIGHT_FLOOR
                + ambient[index] * PREVIEW_AMBIENT_WEIGHT,
            )
            for index in range(3)
        )
        rgb = tuple(_clamp01(diffuse[index] * light[index] + emission[index]) for index in range(3))
    else:
        rgb = tuple(_clamp01(diffuse[index] + emission[index]) for index in range(3))

    return (*rgb, diffuse[3])


def _texture_extension(wrap_u, wrap_v):
    if wrap_u == "MIRRORED_REPEAT" or wrap_v == "MIRRORED_REPEAT":
        return "MIRROR"
    if wrap_u in CLAMP_WRAP_MODES or wrap_v in CLAMP_WRAP_MODES:
        return "EXTEND"
    return "REPEAT"


def _uses_texture_alpha(settings):
    return settings.alpha_test_enabled or settings.blend_mode in ALPHA_BLEND_MODES


def _set_material_display_flags(material, settings):
    material.diffuse_color = _preview_color(settings)
    culling_enabled = settings.face_culling != "NONE"
    material.use_backface_culling = culling_enabled

    if settings.alpha_test_enabled:
        material.alpha_threshold = settings.alpha_reference / 255.0
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        else:
            material.blend_method = "CLIP"
    elif settings.blend_mode in ALPHA_BLEND_MODES or material.diffuse_color[3] < 1.0:
        material.blend_method = "BLEND"
    else:
        material.blend_method = "OPAQUE"

    if hasattr(material, "use_transparency_overlap"):
        material.use_transparency_overlap = not settings.alpha_test_enabled
    elif hasattr(material, "show_transparent_back"):
        material.show_transparent_back = not culling_enabled


def _set_node_location(node, x, y):
    node.location.x = x
    node.location.y = y


def _new_node(nodes, node_type, x, y):
    node = nodes.new(node_type)
    _set_node_location(node, x, y)
    return node


def _set_image_extension(node, extension):
    try:
        node.extension = extension
    except TypeError:
        node.extension = "REPEAT" if extension == "MIRROR" else extension


def _set_image_interpolation(node, min_filter, mag_filter):
    if min_filter.startswith("NEAREST") and mag_filter == "NEAREST":
        node.interpolation = "Closest"
    else:
        node.interpolation = "Linear"


def _rgb_node(nodes, color, x, y, label="Color"):
    node = _new_node(nodes, "ShaderNodeRGB", x, y)
    node.label = label
    node.outputs["Color"].default_value = color
    return node.outputs["Color"]


def _value_node(nodes, value, x, y, label="Value"):
    node = _new_node(nodes, "ShaderNodeValue", x, y)
    node.label = label
    node.outputs["Value"].default_value = value
    return node.outputs["Value"]


def _mix_node(nodes, links, blend_type, input_a, input_b, x, y, label):
    node = _new_node(nodes, "ShaderNodeMixRGB", x, y)
    node.label = label
    node.blend_type = blend_type
    node.use_clamp = True
    node.inputs["Fac"].default_value = 1.0
    links.new(input_a, node.inputs["Color1"])
    links.new(input_b, node.inputs["Color2"])
    return node.outputs["Color"]


def _matcap_vector(nodes, links):
    geometry = _new_node(nodes, "ShaderNodeNewGeometry", -1100, -460)
    transform = _new_node(nodes, "ShaderNodeVectorTransform", -900, -460)
    transform.vector_type = "NORMAL"
    transform.convert_from = "WORLD"
    transform.convert_to = "CAMERA"
    scale = _new_node(nodes, "ShaderNodeVectorMath", -700, -460)
    scale.operation = "SCALE"
    scale.inputs["Scale"].default_value = 0.5
    offset = _new_node(nodes, "ShaderNodeVectorMath", -500, -460)
    offset.operation = "ADD"
    offset.inputs[1].default_value = (0.5, 0.5, 0.0)
    links.new(geometry.outputs["Normal"], transform.inputs["Vector"])
    links.new(transform.outputs["Vector"], scale.inputs[0])
    links.new(scale.outputs["Vector"], offset.inputs[0])
    return offset.outputs["Vector"]


def _texture_source_node(nodes, links, texture, x, y, matcap_vector):
    node = _new_node(nodes, "ShaderNodeTexImage", x, y)
    node.label = f"CMB Texture {texture.index}"
    node.image = texture.image
    _set_image_interpolation(node, texture.min_filter, texture.mag_filter)
    _set_image_extension(node, _texture_extension(texture.wrap_u, texture.wrap_v))
    if texture.is_reflection:
        links.new(matcap_vector, node.inputs["Vector"])
    return node.outputs["Color"], node.outputs["Alpha"]


def _preview_texture(settings, index):
    image, *settings_values = texture_slot_values(
        settings, index, *PREVIEW_TEXTURE_FIELDS
    )
    if image is None:
        return None
    return PreviewTexture(index, image, *settings_values)


def _preview_textures(settings):
    return tuple(
        texture
        for index in TEXTURE_SLOT_INDICES
        if (texture := _preview_texture(settings, index)) is not None
    )


def _split_preview_textures(textures):
    base = next((texture for texture in textures if not texture.is_reflection), None)
    reflections = tuple(texture for texture in textures if texture.is_reflection)
    return base, reflections


def _alpha_output(nodes, links, settings, texture_alpha):
    if not _uses_texture_alpha(settings):
        return _value_node(nodes, 1.0, 500, -240, "Opaque Alpha")
    if not settings.alpha_test_enabled:
        return texture_alpha

    alpha_test = _new_node(nodes, "ShaderNodeMath", 500, -240)
    alpha_test.label = "Alpha Test"
    alpha_test.operation = "GREATER_THAN"
    alpha_test.inputs[1].default_value = settings.alpha_reference / 255.0
    links.new(texture_alpha, alpha_test.inputs[0])
    return alpha_test.outputs["Value"]


def _build_preview_nodes(material, settings):
    material.use_nodes = True
    tree = material.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = _new_node(nodes, "ShaderNodeOutputMaterial", 1100, 0)
    emission = _new_node(nodes, "ShaderNodeEmission", 880, 0)
    transparent = _new_node(nodes, "ShaderNodeBsdfTransparent", 880, -180)
    shader_mix = _new_node(nodes, "ShaderNodeMixShader", 1100, -80)
    primary_color = _preview_color(settings)
    color = _rgb_node(nodes, primary_color, -700, 220, "CMB Preview Color")
    alpha = _value_node(nodes, primary_color[3], -700, 140, "CMB Preview Alpha")
    matcap_vector = _matcap_vector(nodes, links)

    base_texture, reflection_textures = _split_preview_textures(
        _preview_textures(settings)
    )
    if base_texture is not None:
        color, alpha = _texture_source_node(
            nodes,
            links,
            base_texture,
            -500,
            300,
            matcap_vector,
        )

    alpha = _alpha_output(nodes, links, settings, alpha)

    for reflection_index, texture in enumerate(reflection_textures):
        reflection_color, _reflection_alpha = _texture_source_node(
            nodes,
            links,
            texture,
            -500,
            -40 - reflection_index * 220,
            matcap_vector,
        )
        color = _mix_node(
            nodes,
            links,
            "ADD",
            color,
            reflection_color,
            -100 + reflection_index * 220,
            120,
            f"Reflection {texture.index}",
        )

    emission.inputs["Strength"].default_value = 1.0
    links.new(color, emission.inputs["Color"])
    links.new(alpha, shader_mix.inputs[0])
    links.new(transparent.outputs[0], shader_mix.inputs[1])
    links.new(emission.outputs["Emission"], shader_mix.inputs[2])
    links.new(shader_mix.outputs[0], output.inputs["Surface"])


def _preview_signature(settings):
    images = tuple(
        image.name if image else ""
        for texture_index in TEXTURE_SLOT_INDICES
        for image in texture_slot_values(settings, texture_index, "image")
    )
    texture_settings = tuple(
        value
        for texture_index in TEXTURE_SLOT_INDICES
        for value in texture_slot_values(
            settings,
            texture_index,
            *SIGNATURE_TEXTURE_FIELDS,
        )
    )
    return repr(
        (
            PREVIEW_VERSION,
            images,
            tuple(settings.emission_color),
            tuple(settings.diffuse_color),
            tuple(settings.ambient_color),
            tuple(settings.specular0_color),
            tuple(settings.specular1_color),
            settings.fragment_lighting,
            settings.vertex_lighting,
            settings.is_fog_enabled,
            settings.render_layer,
            settings.face_culling,
            settings.alpha_test_enabled,
            settings.alpha_reference,
            settings.alpha_function,
            settings.depth_test_enabled,
            settings.depth_write_enabled,
            settings.depth_function,
            settings.blend_mode,
            tuple(settings.blend_color),
            texture_settings,
        )
    )


def sync_cmb_material_preview(material, force=False):
    if material is None or not hasattr(material, "cmb_settings"):
        return

    settings = material.cmb_settings
    if settings.material_type != "CMB" and not settings.enabled:
        return

    signature = _preview_signature(settings)
    _set_material_display_flags(material, settings)
    if force or material.get("_cmb_preview_signature") != signature:
        _build_preview_nodes(material, settings)
        material["_cmb_preview_signature"] = signature

    material.update_tag()


def visualize_cmb_material_preview_texture(material, image):
    if material is None or image is None:
        return

    sync_cmb_material_preview(material)
    tree = material.node_tree
    if tree is None:
        return

    for node in tree.nodes:
        if node.type == "TEX_IMAGE" and node.label == "CMB Texture 0":
            node.image = image
            material.update_tag()
            return


def sync_cmb_material_preview_from_settings(settings, context=None, force=False):
    material = getattr(settings, "id_data", None)
    sync_cmb_material_preview(material, force=force)

    if context is not None:
        screen = getattr(context, "screen", None)
        for area in (screen.areas if screen is not None else ()):
            area.tag_redraw()
