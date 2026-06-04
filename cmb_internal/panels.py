import bpy

from .blender_context import active_material_from_context
from .material_presets import ensure_stage_slots
from .properties import is_cmb_material_settings
from .texture_slots import TEXTURE_SLOT_INDICES, texture_slot_attr


_REORDERED_MATERIAL_PANELS = []


def draw_texture_tab(layout, settings):
    box = layout.box()
    box.label(text="Textures")
    for slot_index in TEXTURE_SLOT_INDICES:
        col = box.column(align=True)
        col.template_ID(
            settings, texture_slot_attr(slot_index, "image"), open="image.open"
        )
        col.prop(
            settings, texture_slot_attr(slot_index, "format"), text=f"Format {slot_index}"
        )
        col.prop(
            settings,
            texture_slot_attr(slot_index, "coord_mapping"),
            text=f"Mapping {slot_index}",
        )
        row = col.row(align=True)
        row.prop(
            settings, texture_slot_attr(slot_index, "min_filter"), text=f"Min {slot_index}"
        )
        row.prop(
            settings, texture_slot_attr(slot_index, "mag_filter"), text=f"Mag {slot_index}"
        )
        row = col.row(align=True)
        row.prop(
            settings, texture_slot_attr(slot_index, "wrap_u"), text=f"Wrap U {slot_index}"
        )
        row.prop(
            settings, texture_slot_attr(slot_index, "wrap_v"), text=f"Wrap V {slot_index}"
        )


def draw_combiner_tab(layout, settings):
    box = layout.box()
    box.label(text="Combiner")
    box.prop(settings, "tex_env_stage_count")
    for stage_index in range(min(settings.tex_env_stage_count, len(settings.tex_env_stages))):
        stage = settings.tex_env_stages[stage_index]
        stage_box = box.box()
        stage_box.label(text=f"Stage {stage_index}")
        row = stage_box.row(align=True)
        row.prop(stage, "combine_rgb", text="Color")
        row.prop(stage, "combine_alpha", text="Alpha")
        row = stage_box.row(align=True)
        row.prop(stage, "scale_rgb", text="Color Scale")
        row.prop(stage, "scale_alpha", text="Alpha Scale")
        row = stage_box.row(align=True)
        row.prop(stage, "buffer_input_rgb", text="Color Buffer")
        row.prop(stage, "buffer_input_alpha", text="Alpha Buffer")

        stage_box.label(text="Color Sources")
        for source_index in range(3):
            row = stage_box.row(align=True)
            row.prop(stage, f"source_rgb{source_index}", text=f"Src {source_index}")
            row.prop(stage, f"operand_rgb{source_index}", text=f"Op {source_index}")

        stage_box.label(text="Alpha Sources")
        for source_index in range(3):
            row = stage_box.row(align=True)
            row.prop(stage, f"source_alpha{source_index}", text=f"Src {source_index}")
            row.prop(stage, f"operand_alpha{source_index}", text=f"Op {source_index}")

        stage_box.prop(stage, "constant_color_index")


def draw_lighting_tab(layout, settings):
    box = layout.box()
    box.label(text="Lighting")
    col = box.column(align=True)
    col.prop(settings, "fragment_lighting")
    col.prop(settings, "vertex_lighting")
    col.prop(settings, "hemisphere_lighting")
    col.prop(settings, "hemisphere_occlusion")

    box = layout.box()
    box.label(text="Geometry")
    col = box.column(align=True)
    col.prop(settings, "face_culling")
    col.prop(settings, "polygon_offset_enabled")
    if settings.polygon_offset_enabled:
        col.prop(settings, "polygon_offset")


def draw_color_tab(layout, settings):
    box = layout.box()
    box.label(text="Colors")
    box.prop(settings, "emission_color")
    box.prop(settings, "ambient_color")
    box.prop(settings, "diffuse_color")
    box.prop(settings, "specular0_color")
    box.prop(settings, "specular1_color")
    box.prop(settings, "buffer_color")

    box = layout.box()
    box.label(text="Constants")
    box.prop(settings, "constant0_color")
    box.prop(settings, "constant1_color")
    box.prop(settings, "constant2_color")
    box.prop(settings, "constant3_color")
    box.prop(settings, "constant4_color")
    box.prop(settings, "constant5_color")


def draw_alpha_depth_tab(layout, settings):
    box = layout.box()
    box.label(text="Alpha / Depth")
    box.prop(settings, "alpha_test_enabled")
    if settings.alpha_test_enabled:
        box.prop(settings, "alpha_reference")
        box.prop(settings, "alpha_function")
    box.prop(settings, "depth_test_enabled")
    if settings.depth_test_enabled:
        box.prop(settings, "depth_function")
    box.prop(settings, "depth_write_enabled")
    box.prop(settings, "blend_mode")
    box.prop(settings, "blend_color")


def draw_material_settings(layout, material):
    settings = material.cmb_settings
    ensure_stage_slots(settings)

    if not is_cmb_material_settings(settings):
        row = layout.row(align=True)
        row.operator("cmb.convert_material", text="Convert to CMB")
        row.operator("cmb.create_material", text="New CMB")
        layout.operator("cmb.convert_all_materials", text="Convert All Materials")
        return

    row = layout.row(align=True)
    row.label(text="CMB Material")
    row.operator("cmb.create_material", text="New")
    row.operator("cmb.convert_all_materials", text="Convert All")
    layout.operator("cmb.refresh_all_material_presets", text="Refresh All Presets")

    layout.prop(settings, "material_preset")
    layout.row().prop(settings, "ui_tab", expand=True)

    if settings.ui_tab == "TEXTURES":
        draw_texture_tab(layout, settings)
    elif settings.ui_tab == "COMBINER":
        draw_combiner_tab(layout, settings)
    elif settings.ui_tab == "LIGHTING":
        draw_lighting_tab(layout, settings)
    elif settings.ui_tab == "COLORS":
        draw_color_tab(layout, settings)
    elif settings.ui_tab == "ALPHA_DEPTH":
        draw_alpha_depth_tab(layout, settings)


class CMB_PT_sidebar(bpy.types.Panel):
    bl_label = "CMB Exporter"
    bl_idname = "CMB_PT_sidebar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CMB"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cmb_export_settings
        layout.label(text="Viewport is not 100% accurate to ingame!", icon="INFO")
        box = layout.box()
        box.label(text="Export")
        box.prop(settings, "filepath")
        box.prop(settings, "etc_compression_mode")
        box.operator("export_scene.cmb")

        box = layout.box()
        box.label(text="Materials")
        box.operator("cmb.convert_all_materials")
        box.operator("cmb.refresh_all_material_presets")
        box.operator("cmb.create_material")


class MATERIAL_PT_cmb_material_settings(bpy.types.Panel):
    bl_label = "CMB Material"
    bl_idname = "MATERIAL_PT_cmb_material_settings"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_order = -100000

    @classmethod
    def poll(cls, context):
        return active_material_from_context(context) is not None

    def draw(self, context):
        draw_material_settings(self.layout, active_material_from_context(context))


classes = (
    CMB_PT_sidebar,
    MATERIAL_PT_cmb_material_settings,
)


def _material_panel_class(panel_id):
    panel = getattr(bpy.types, panel_id, None)
    if panel is not None:
        return panel
    return bpy.types.Panel.bl_rna_get_subclass_py(panel_id, None)


def _unregister_builtin_material_panels():
    panel_ids = (
        "MATERIAL_PT_preview",
        "EEVEE_MATERIAL_PT_surface",
        "EEVEE_MATERIAL_PT_volume",
        "EEVEE_MATERIAL_PT_displacement",
        "EEVEE_MATERIAL_PT_thickness",
        "EEVEE_MATERIAL_PT_settings",
        "MATERIAL_PT_surface",
        "MATERIAL_PT_volume",
        "MATERIAL_PT_displacement",
        "MATERIAL_PT_thickness",
        "MATERIAL_PT_settings",
        "EEVEE_MATERIAL_PT_settings_surface",
        "EEVEE_MATERIAL_PT_settings_volume",
        "EEVEE_MATERIAL_PT_viewport_settings",
        "MATERIAL_PT_lineart",
        "MATERIAL_PT_viewport",
        "MATERIAL_PT_animation",
        "MATERIAL_PT_custom_props",
    )
    unregistered = []

    for panel_id in panel_ids:
        panel_cls = _material_panel_class(panel_id)
        if panel_cls is None:
            continue
        try:
            bpy.utils.unregister_class(panel_cls)
        except RuntimeError:
            continue
        unregistered.append(panel_cls)

    return unregistered


def _restore_builtin_material_panels(panel_classes):
    top_level = [
        panel_cls for panel_cls in panel_classes if not getattr(panel_cls, "bl_parent_id", "")
    ]
    children = [
        panel_cls for panel_cls in panel_classes if getattr(panel_cls, "bl_parent_id", "")
    ]
    for panel_cls in (*top_level, *children):
        try:
            bpy.utils.register_class(panel_cls)
        except RuntimeError:
            continue


def register():
    global _REORDERED_MATERIAL_PANELS
    bpy.utils.register_class(CMB_PT_sidebar)
    _REORDERED_MATERIAL_PANELS = _unregister_builtin_material_panels()
    bpy.utils.register_class(MATERIAL_PT_cmb_material_settings)
    _restore_builtin_material_panels(_REORDERED_MATERIAL_PANELS)


def unregister():
    global _REORDERED_MATERIAL_PANELS
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    _REORDERED_MATERIAL_PANELS = []
