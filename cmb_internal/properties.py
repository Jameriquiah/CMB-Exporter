import bpy

from .material_presets import MATERIAL_PRESET_ITEMS, apply_preset_to_settings


TEST_FUNCTION_ITEMS = (
    ("NEVER", "Never", ""),
    ("LESS", "Less", ""),
    ("EQUAL", "Equal", ""),
    ("LEQUAL", "Less or Equal", ""),
    ("GREATER", "Greater", ""),
    ("NOTEQUAL", "Not Equal", ""),
    ("GEQUAL", "Greater or Equal", ""),
    ("ALWAYS", "Always", ""),
)

BLEND_MODE_ITEMS = (
    ("OPAQUE", "Opaque", ""),
    ("ALPHA", "Alpha Blend", ""),
    ("ADD", "Additive", ""),
)

BLEND_FACTOR_ITEMS = (
    ("ZERO", "Zero", ""),
    ("ONE", "One", ""),
    ("SRC_COLOR", "Source Color", ""),
    ("ONE_MINUS_SRC_COLOR", "One Minus Source Color", ""),
    ("SRC_ALPHA", "Source Alpha", ""),
    ("ONE_MINUS_SRC_ALPHA", "One Minus Source Alpha", ""),
    ("DST_ALPHA", "Destination Alpha", ""),
    ("ONE_MINUS_DST_ALPHA", "One Minus Destination Alpha", ""),
    ("DST_COLOR", "Destination Color", ""),
    ("ONE_MINUS_DST_COLOR", "One Minus Destination Color", ""),
)

BLEND_EQUATION_ITEMS = (
    ("FUNC_ADD", "Add", ""),
    ("FUNC_SUBTRACT", "Subtract", ""),
    ("FUNC_REVERSE_SUBTRACT", "Reverse Subtract", ""),
)

TEXTURE_FORMAT_ITEMS = (
    ("RGB565", "RGB565", "", 2),
    ("RGBA5551", "RGBA5551", "", 3),
    ("LA4", "LA4", "", 5),
    ("LA8", "LA8", "", 6),
    ("L8", "L8", "", 7),
    ("L4", "L4", "", 8),
    ("A8", "A8", "", 9),
    ("ETC1", "ETC1", "", 10),
    ("ETC1A4", "ETC1A4", "", 11),
)

TEXTURE_MIN_FILTER_ITEMS = (
    ("NEAREST", "Nearest", ""),
    ("LINEAR", "Linear", ""),
    ("NEAREST_MIPMAP_NEAREST", "Nearest Mipmap Nearest", ""),
    ("LINEAR_MIPMAP_NEAREST", "Linear Mipmap Nearest", ""),
    ("NEAREST_MIPMAP_LINEAR", "Nearest Mipmap Linear", ""),
    ("LINEAR_MIPMAP_LINEAR", "Linear Mipmap Linear", ""),
)

TEXTURE_MAG_FILTER_ITEMS = (
    ("NEAREST", "Nearest", ""),
    ("LINEAR", "Linear", ""),
)

TEXTURE_WRAP_ITEMS = (
    ("CLAMP", "Clamp", ""),
    ("REPEAT", "Repeat", ""),
    ("CLAMP_TO_BORDER", "Clamp To Border", ""),
    ("CLAMP_TO_EDGE", "Clamp To Edge", ""),
    ("MIRRORED_REPEAT", "Mirror", ""),
)

TEXTURE_COORD_MAPPING_ITEMS = (
    ("NONE", "None", ""),
    ("UV", "UV", ""),
    ("REFLECTION", "Reflection", ""),
)

CULLING_MODE_ITEMS = (
    ("FRONT_AND_BACK", "Front And Back", ""),
    ("BACK", "Back", ""),
    ("FRONT", "Front", ""),
    ("NONE", "None", ""),
)

COMBINER_ITEMS = (
    ("REPLACE", "Replace", ""),
    ("MODULATE", "Modulate", ""),
    ("ADD", "Add", ""),
    ("MULT_ADD", "MultAdd", ""),
)

SOURCE_ITEMS = (
    ("PRIMARY_COLOR", "Primary Color", ""),
    ("FRAGMENT_PRIMARY_COLOR_DMP", "Fragment Primary Color", ""),
    ("TEXTURE0", "Texture 0", ""),
    ("TEXTURE1", "Texture 1", ""),
    ("TEXTURE2", "Texture 2", ""),
    ("PREVIOUS_BUFFER_DMP", "Previous Buffer", ""),
    ("CONSTANT", "Constant", ""),
    ("PREVIOUS", "Previous", ""),
)

OPERAND_RGB_ITEMS = (
    ("SRC_COLOR", "Color", ""),
    ("SRC_ALPHA", "Alpha", ""),
)

OPERAND_ALPHA_ITEMS = (
    ("SRC_ALPHA", "Alpha", ""),
    ("SRC_COLOR", "Color", ""),
)

SCALE_ITEMS = (
    ("1", "One", ""),
    ("2", "Two", ""),
    ("4", "Four", ""),
)

CMB_MATERIAL_TAB_ITEMS = (
    ("TEXTURES", "Textures", ""),
    ("COMBINER", "Combiner", ""),
    ("LIGHTING", "Lighting", ""),
    ("COLORS", "Colors", ""),
    ("ALPHA_DEPTH", "Alpha / Depth", ""),
)

CMB_MATERIAL_TYPE_ITEMS = (
    ("BLENDER", "Blender", ""),
    ("CMB", "CMB", ""),
)

ETC_COMPRESSION_MODE_ITEMS = (
    ("FAST", "Fast", "Fast ETC compression with lower color search quality"),
    ("HIGH", "High Quality", "Slow ETC compression with the best current color search quality"),
)


def update_material_preset(self, context):
    apply_preset_to_settings(self, self.material_preset)
    sync_preview(self, context)


def update_material_type(self, context):
    if self.material_type == "CMB":
        self.enabled = True
        apply_preset_to_settings(self, self.material_preset)
        sync_preview(self, context, force=True)


def sync_preview(settings, context, force=False):
    if is_cmb_material_settings(settings):
        from .viewport import sync_cmb_material_preview_from_settings

        sync_cmb_material_preview_from_settings(settings, context, force=force)


def update_preview(self, context):
    if is_cmb_material_settings(self):
        from .viewport import sync_cmb_material_preview_from_settings

        sync_cmb_material_preview_from_settings(self, context)


def update_stage_preview(self, context):
    material = getattr(self, "id_data", None)
    if material is not None:
        from .viewport import sync_cmb_material_preview

        sync_cmb_material_preview(material)


def is_cmb_material_settings(settings):
    return settings.material_type == "CMB" or settings.enabled


class CMBTexEnvStageSettings(bpy.types.PropertyGroup):
    combine_rgb: bpy.props.EnumProperty(
        name="Color",
        items=COMBINER_ITEMS,
        default="REPLACE",
        update=update_stage_preview,
    )
    combine_alpha: bpy.props.EnumProperty(
        name="Alpha",
        items=COMBINER_ITEMS,
        default="REPLACE",
        update=update_stage_preview,
    )
    scale_rgb: bpy.props.EnumProperty(
        name="Color Scale",
        items=SCALE_ITEMS,
        default="1",
        update=update_stage_preview,
    )
    scale_alpha: bpy.props.EnumProperty(
        name="Alpha Scale",
        items=SCALE_ITEMS,
        default="1",
        update=update_stage_preview,
    )
    buffer_input_rgb: bpy.props.EnumProperty(
        name="Color Buffer",
        items=SOURCE_ITEMS,
        default="PREVIOUS_BUFFER_DMP",
        update=update_stage_preview,
    )
    buffer_input_alpha: bpy.props.EnumProperty(
        name="Alpha Buffer",
        items=SOURCE_ITEMS,
        default="PREVIOUS_BUFFER_DMP",
        update=update_stage_preview,
    )
    source_rgb0: bpy.props.EnumProperty(
        name="Color Source 0", items=SOURCE_ITEMS, default="PRIMARY_COLOR", update=update_stage_preview
    )
    source_rgb1: bpy.props.EnumProperty(
        name="Color Source 1", items=SOURCE_ITEMS, default="PRIMARY_COLOR", update=update_stage_preview
    )
    source_rgb2: bpy.props.EnumProperty(
        name="Color Source 2", items=SOURCE_ITEMS, default="PRIMARY_COLOR", update=update_stage_preview
    )
    operand_rgb0: bpy.props.EnumProperty(
        name="Color Operand 0", items=OPERAND_RGB_ITEMS, default="SRC_COLOR", update=update_stage_preview
    )
    operand_rgb1: bpy.props.EnumProperty(
        name="Color Operand 1", items=OPERAND_RGB_ITEMS, default="SRC_COLOR", update=update_stage_preview
    )
    operand_rgb2: bpy.props.EnumProperty(
        name="Color Operand 2", items=OPERAND_RGB_ITEMS, default="SRC_COLOR", update=update_stage_preview
    )
    source_alpha0: bpy.props.EnumProperty(
        name="Alpha Source 0", items=SOURCE_ITEMS, default="PRIMARY_COLOR", update=update_stage_preview
    )
    source_alpha1: bpy.props.EnumProperty(
        name="Alpha Source 1", items=SOURCE_ITEMS, default="PRIMARY_COLOR", update=update_stage_preview
    )
    source_alpha2: bpy.props.EnumProperty(
        name="Alpha Source 2", items=SOURCE_ITEMS, default="PRIMARY_COLOR", update=update_stage_preview
    )
    operand_alpha0: bpy.props.EnumProperty(
        name="Alpha Operand 0", items=OPERAND_ALPHA_ITEMS, default="SRC_ALPHA", update=update_stage_preview
    )
    operand_alpha1: bpy.props.EnumProperty(
        name="Alpha Operand 1", items=OPERAND_ALPHA_ITEMS, default="SRC_ALPHA", update=update_stage_preview
    )
    operand_alpha2: bpy.props.EnumProperty(
        name="Alpha Operand 2", items=OPERAND_ALPHA_ITEMS, default="SRC_ALPHA", update=update_stage_preview
    )
    constant_color_index: bpy.props.IntProperty(
        name="Constant",
        default=0,
        min=0,
        max=5,
        update=update_stage_preview,
    )


class CMABTextureImageSlot(bpy.types.PropertyGroup):
    image: bpy.props.PointerProperty(
        name="Image",
        type=bpy.types.Image,
    )


class CMBMaterialSettings(bpy.types.PropertyGroup):
    material_type: bpy.props.EnumProperty(
        name="Material Type",
        items=CMB_MATERIAL_TYPE_ITEMS,
        default="BLENDER",
        update=update_material_type,
    )
    ui_tab: bpy.props.EnumProperty(
        name="Menu",
        items=CMB_MATERIAL_TAB_ITEMS,
        default="TEXTURES",
    )
    enabled: bpy.props.BoolProperty(
        name="CMB Material",
        default=False,
    )
    cmab_texture_swap_enabled: bpy.props.BoolProperty(
        name="CMAB Texture Swap",
        default=False,
    )
    cmab_texture_swap_images: bpy.props.CollectionProperty(type=CMABTextureImageSlot)
    fragment_lighting: bpy.props.BoolProperty(
        name="Fragment Lighting",
        default=False,
        update=update_preview,
    )
    vertex_lighting: bpy.props.BoolProperty(
        name="Vertex Lighting",
        default=False,
        update=update_preview,
    )
    is_fog_enabled: bpy.props.BoolProperty(
        name="Fog Enabled",
        default=False,
        update=update_preview,
    )
    render_layer: bpy.props.IntProperty(
        name="Render Layer",
        default=0,
        min=0,
        max=255,
        update=update_preview,
    )
    face_culling: bpy.props.EnumProperty(
        name="Culling",
        items=CULLING_MODE_ITEMS,
        default="BACK",
        update=update_preview,
    )
    polygon_offset_enabled: bpy.props.BoolProperty(
        name="Polygon Offset",
        default=False,
    )
    polygon_offset: bpy.props.IntProperty(
        name="Offset",
        default=0,
        min=0,
        max=65535,
    )

    emission_color: bpy.props.FloatVectorProperty(
        name="Emission",
        subtype="COLOR",
        size=4,
        default=(0.0, 0.0, 0.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    ambient_color: bpy.props.FloatVectorProperty(
        name="Ambient",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    diffuse_color: bpy.props.FloatVectorProperty(
        name="Diffuse",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    specular0_color: bpy.props.FloatVectorProperty(
        name="Specular 0",
        subtype="COLOR",
        size=4,
        default=(0.0, 0.0, 0.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    specular1_color: bpy.props.FloatVectorProperty(
        name="Specular 1",
        subtype="COLOR",
        size=4,
        default=(0.0, 0.0, 0.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    constant0_color: bpy.props.FloatVectorProperty(
        name="Constant 0",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    constant1_color: bpy.props.FloatVectorProperty(
        name="Constant 1",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    constant2_color: bpy.props.FloatVectorProperty(
        name="Constant 2",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    constant3_color: bpy.props.FloatVectorProperty(
        name="Constant 3",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    constant4_color: bpy.props.FloatVectorProperty(
        name="Constant 4",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    constant5_color: bpy.props.FloatVectorProperty(
        name="Constant 5",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    buffer_color: bpy.props.FloatVectorProperty(
        name="Buffer",
        subtype="COLOR",
        size=4,
        default=(0.0, 0.0, 0.0, 0.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )

    alpha_test_enabled: bpy.props.BoolProperty(
        name="Alpha Test",
        default=False,
        update=update_preview,
    )
    alpha_reference: bpy.props.IntProperty(
        name="Reference",
        default=0,
        min=0,
        max=255,
        update=update_preview,
    )
    alpha_function: bpy.props.EnumProperty(
        name="Function",
        items=TEST_FUNCTION_ITEMS,
        default="ALWAYS",
        update=update_preview,
    )
    depth_test_enabled: bpy.props.BoolProperty(
        name="Depth Test",
        default=True,
        update=update_preview,
    )
    depth_write_enabled: bpy.props.BoolProperty(
        name="Depth Write",
        default=True,
        update=update_preview,
    )
    depth_function: bpy.props.EnumProperty(
        name="Function",
        items=TEST_FUNCTION_ITEMS,
        default="LEQUAL",
        update=update_preview,
    )
    blend_mode: bpy.props.EnumProperty(
        name="Blend Mode",
        items=BLEND_MODE_ITEMS,
        default="OPAQUE",
        update=update_preview,
    )
    blend_alpha_src_function: bpy.props.EnumProperty(
        name="Alpha Src",
        items=BLEND_FACTOR_ITEMS,
        default="SRC_ALPHA",
        update=update_preview,
    )
    blend_alpha_dst_function: bpy.props.EnumProperty(
        name="Alpha Dst",
        items=BLEND_FACTOR_ITEMS,
        default="ONE_MINUS_SRC_ALPHA",
        update=update_preview,
    )
    blend_alpha_equation: bpy.props.EnumProperty(
        name="Alpha Equation",
        items=BLEND_EQUATION_ITEMS,
        default="FUNC_ADD",
        update=update_preview,
    )
    blend_color_src_function: bpy.props.EnumProperty(
        name="Color Src",
        items=BLEND_FACTOR_ITEMS,
        default="ONE",
        update=update_preview,
    )
    blend_color_dst_function: bpy.props.EnumProperty(
        name="Color Dst",
        items=BLEND_FACTOR_ITEMS,
        default="ZERO",
        update=update_preview,
    )
    blend_color_equation: bpy.props.EnumProperty(
        name="Color Equation",
        items=BLEND_EQUATION_ITEMS,
        default="FUNC_ADD",
        update=update_preview,
    )
    blend_color: bpy.props.FloatVectorProperty(
        name="Blend Color",
        subtype="COLOR",
        size=4,
        default=(0.0, 0.0, 0.0, 0.0),
        min=0.0,
        max=1.0,
        update=update_preview,
    )
    texture_format: bpy.props.EnumProperty(
        name="Texture Format",
        items=TEXTURE_FORMAT_ITEMS,
        default="RGB565",
        update=update_preview,
    )
    texture_image: bpy.props.PointerProperty(
        name="Image",
        type=bpy.types.Image,
        update=update_preview,
    )
    texture_min_filter: bpy.props.EnumProperty(
        name="Min Filter",
        items=TEXTURE_MIN_FILTER_ITEMS,
        default="LINEAR",
        update=update_preview,
    )
    texture_mag_filter: bpy.props.EnumProperty(
        name="Mag Filter",
        items=TEXTURE_MAG_FILTER_ITEMS,
        default="LINEAR",
        update=update_preview,
    )
    texture_wrap_u: bpy.props.EnumProperty(
        name="Wrap U",
        items=TEXTURE_WRAP_ITEMS,
        default="REPEAT",
        update=update_preview,
    )
    texture_wrap_v: bpy.props.EnumProperty(
        name="Wrap V",
        items=TEXTURE_WRAP_ITEMS,
        default="REPEAT",
        update=update_preview,
    )
    texture_coord_mapping: bpy.props.EnumProperty(
        name="Mapping 0",
        items=TEXTURE_COORD_MAPPING_ITEMS,
        default="UV",
        update=update_preview,
    )
    texture_coord_matrix_mode: bpy.props.IntProperty(name="Matrix 0", default=0, min=0, max=255, update=update_preview)
    texture_coord_reference_camera: bpy.props.IntProperty(name="Camera 0", default=0, min=0, max=255, update=update_preview)
    texture_coord_source: bpy.props.IntProperty(name="Source Coord 0", default=0, min=0, max=255, update=update_preview)
    texture_coord_scale: bpy.props.FloatVectorProperty(name="Scale 0", size=2, default=(1.0, 1.0), update=update_preview)
    texture_coord_rotation: bpy.props.FloatProperty(name="Rotation 0", default=0.0, update=update_preview)
    texture_coord_translation: bpy.props.FloatVectorProperty(name="Translation 0", size=2, default=(0.0, 0.0), update=update_preview)
    texture1_format: bpy.props.EnumProperty(
        name="Texture 1 Format",
        items=TEXTURE_FORMAT_ITEMS,
        default="RGB565",
        update=update_preview,
    )
    texture1_image: bpy.props.PointerProperty(
        name="Texture 1 Image",
        type=bpy.types.Image,
        update=update_preview,
    )
    texture1_min_filter: bpy.props.EnumProperty(
        name="Texture 1 Min Filter",
        items=TEXTURE_MIN_FILTER_ITEMS,
        default="LINEAR",
        update=update_preview,
    )
    texture1_mag_filter: bpy.props.EnumProperty(
        name="Texture 1 Mag Filter",
        items=TEXTURE_MAG_FILTER_ITEMS,
        default="LINEAR",
        update=update_preview,
    )
    texture1_wrap_u: bpy.props.EnumProperty(
        name="Texture 1 Wrap U",
        items=TEXTURE_WRAP_ITEMS,
        default="REPEAT",
        update=update_preview,
    )
    texture1_wrap_v: bpy.props.EnumProperty(
        name="Texture 1 Wrap V",
        items=TEXTURE_WRAP_ITEMS,
        default="REPEAT",
        update=update_preview,
    )
    texture1_coord_mapping: bpy.props.EnumProperty(
        name="Mapping 1",
        items=TEXTURE_COORD_MAPPING_ITEMS,
        default="REFLECTION",
        update=update_preview,
    )
    texture1_coord_matrix_mode: bpy.props.IntProperty(name="Matrix 1", default=0, min=0, max=255, update=update_preview)
    texture1_coord_reference_camera: bpy.props.IntProperty(name="Camera 1", default=0, min=0, max=255, update=update_preview)
    texture1_coord_source: bpy.props.IntProperty(name="Source Coord 1", default=0, min=0, max=255, update=update_preview)
    texture1_coord_scale: bpy.props.FloatVectorProperty(name="Scale 1", size=2, default=(1.0, 1.0), update=update_preview)
    texture1_coord_rotation: bpy.props.FloatProperty(name="Rotation 1", default=0.0, update=update_preview)
    texture1_coord_translation: bpy.props.FloatVectorProperty(name="Translation 1", size=2, default=(0.0, 0.0), update=update_preview)
    texture2_format: bpy.props.EnumProperty(
        name="Texture 2 Format",
        items=TEXTURE_FORMAT_ITEMS,
        default="RGB565",
        update=update_preview,
    )
    texture2_image: bpy.props.PointerProperty(
        name="Texture 2 Image",
        type=bpy.types.Image,
        update=update_preview,
    )
    texture2_min_filter: bpy.props.EnumProperty(
        name="Texture 2 Min Filter",
        items=TEXTURE_MIN_FILTER_ITEMS,
        default="LINEAR",
        update=update_preview,
    )
    texture2_mag_filter: bpy.props.EnumProperty(
        name="Texture 2 Mag Filter",
        items=TEXTURE_MAG_FILTER_ITEMS,
        default="LINEAR",
        update=update_preview,
    )
    texture2_wrap_u: bpy.props.EnumProperty(
        name="Texture 2 Wrap U",
        items=TEXTURE_WRAP_ITEMS,
        default="REPEAT",
        update=update_preview,
    )
    texture2_wrap_v: bpy.props.EnumProperty(
        name="Texture 2 Wrap V",
        items=TEXTURE_WRAP_ITEMS,
        default="REPEAT",
        update=update_preview,
    )
    texture2_coord_mapping: bpy.props.EnumProperty(
        name="Mapping 2",
        items=TEXTURE_COORD_MAPPING_ITEMS,
        default="REFLECTION",
        update=update_preview,
    )
    texture2_coord_matrix_mode: bpy.props.IntProperty(name="Matrix 2", default=0, min=0, max=255, update=update_preview)
    texture2_coord_reference_camera: bpy.props.IntProperty(name="Camera 2", default=0, min=0, max=255, update=update_preview)
    texture2_coord_source: bpy.props.IntProperty(name="Source Coord 2", default=0, min=0, max=255, update=update_preview)
    texture2_coord_scale: bpy.props.FloatVectorProperty(name="Scale 2", size=2, default=(1.0, 1.0), update=update_preview)
    texture2_coord_rotation: bpy.props.FloatProperty(name="Rotation 2", default=0.0, update=update_preview)
    texture2_coord_translation: bpy.props.FloatVectorProperty(name="Translation 2", size=2, default=(0.0, 0.0), update=update_preview)
    material_preset: bpy.props.EnumProperty(
        name="Material Preset",
        items=MATERIAL_PRESET_ITEMS,
        default="ADULT0",
        update=update_material_preset,
    )
    tex_env_stage_count: bpy.props.IntProperty(
        name="Combiner Stages",
        default=1,
        min=1,
        max=6,
        update=update_preview,
    )
    tex_env_stages: bpy.props.CollectionProperty(type=CMBTexEnvStageSettings)


class CMBExportSettings(bpy.types.PropertyGroup):
    filepath: bpy.props.StringProperty(
        name="Export Path",
        subtype="FILE_PATH",
        default="",
    )
    etc_compression_mode: bpy.props.EnumProperty(
        name="ETC Compression",
        items=ETC_COMPRESSION_MODE_ITEMS,
        default="HIGH",
    )
    simplified_export_enabled: bpy.props.BoolProperty(
        name="Simplified Export",
        default=False,
    )
    simplified_export_mode: bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("ADULT", "Adult", ""),
            ("CHILD", "Child", ""),
        ),
        default="ADULT",
    )


classes = (
    CMBTexEnvStageSettings,
    CMABTextureImageSlot,
    CMBMaterialSettings,
    CMBExportSettings,
)


def register():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Material.cmb_settings = bpy.props.PointerProperty(type=CMBMaterialSettings)
    bpy.types.Scene.cmb_export_settings = bpy.props.PointerProperty(type=CMBExportSettings)


def unregister():
    if hasattr(bpy.types.Scene, "cmb_export_settings"):
        del bpy.types.Scene.cmb_export_settings
    if hasattr(bpy.types.Material, "cmb_settings"):
        del bpy.types.Material.cmb_settings
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
