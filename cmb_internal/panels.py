import bpy

from .blender_context import active_material_from_context
from .material_presets import ensure_stage_slots
from .properties import is_cmb_material_settings
from .texture_slots import TEXTURE_SLOT_INDICES, texture_slot_attr


def draw_cmab_texture_swap_frame(layout, frame, index):
    box = layout.box().column()
    box.template_ID(frame, "image", new="image.new", open="image.open")

    row = box.row()
    buttons = row.row(align=True)

    visualize = buttons.operator("cmb.visualize_cmab_texture", text="Visualize", icon="VIEW_CAMERA")
    visualize.index = index

    add = buttons.operator("cmb.add_cmab_texture", text="", icon="ADD")
    add.index = index + 1

    remove = buttons.operator("cmb.remove_cmab_texture", text="", icon="REMOVE")
    remove.index = index

    move_up = buttons.operator("cmb.move_cmab_texture", text="", icon="TRIA_UP")
    move_up.index = index
    move_up.offset = -1

    move_down = buttons.operator("cmb.move_cmab_texture", text="", icon="TRIA_DOWN")
    move_down.index = index
    move_down.offset = 1


def draw_cmab_texture_swap(layout, settings):
    box = layout.box().column()
    box.prop(settings, "cmab_texture_swap_enabled", text="Export CMAB")
    if not settings.cmab_texture_swap_enabled:
        return

    for index, frame in enumerate(settings.cmab_texture_swap_images):
        draw_cmab_texture_swap_frame(box, frame, index)

    add = box.operator("cmb.add_cmab_texture", text="Add Texture")
    add.index = len(settings.cmab_texture_swap_images)


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

    draw_cmab_texture_swap(layout, settings)


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

    box = layout.box()
    box.label(text="Render State")
    col = box.column(align=True)
    col.prop(settings, "is_fog_enabled")
    col.prop(settings, "render_layer")

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
        box.prop(settings, "simplified_export_enabled")
        if settings.simplified_export_enabled:
            box.prop(settings, "simplified_export_mode")
        box.operator("export_scene.cmb")

        box = layout.box()
        box.label(text="Materials")
        box.operator("cmb.convert_all_materials")
        box.operator("cmb.refresh_all_material_presets")
        box.operator("cmb.create_material")


class MATERIAL_PT_cmb_material_settings(bpy.types.Panel):
    bl_label = "CMB Material"
    bl_idname = "MATERIAL_PT_CMB_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return active_material_from_context(context) is not None

    def draw(self, context):
        draw_material_settings(self.layout, active_material_from_context(context))


classes = (
    CMB_PT_sidebar,
    MATERIAL_PT_cmb_material_settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
