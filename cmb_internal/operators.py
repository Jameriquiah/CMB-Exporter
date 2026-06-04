import re
from pathlib import Path

import bpy

from .blender_context import active_material_from_context
from .exporter import CMBExportError, ExportOptions, export_cmb
from .material_presets import apply_preset_to_settings
from .viewport import sync_cmb_material_preview
from .properties import is_cmb_material_settings


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _selected_armature(context):
    armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
    return armatures[0] if len(armatures) == 1 else None


def _safe_filename_stem(name):
    stem = INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    return stem or "cmb_model"


def _filepath_with_armature_name(filepath, armature):
    path = Path(filepath)
    if path.suffix.lower() == ".cmb":
        directory = path.parent
    elif path.exists() and path.is_dir():
        directory = path
    else:
        directory = path.parent

    return str(directory / f"{_safe_filename_stem(armature.name)}.cmb")


def _principled_base_color(material):
    if not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        base_color = node.inputs.get("Base Color")
        if base_color is not None:
            return tuple(base_color.default_value)

    return None


def _principled_base_color_image(material):
    if not material.use_nodes or material.node_tree is None:
        return None

    node_tree = material.node_tree
    for node in node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        base_color = node.inputs.get("Base Color")
        if base_color is None:
            continue
        for link in base_color.links:
            from_node = link.from_node
            if from_node.type == "TEX_IMAGE" and from_node.image is not None:
                return from_node.image

    for node in node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            return node.image

    return None


def _set_cmb_material_type(material):
    material.cmb_settings.material_type = "CMB"
    material.cmb_settings.enabled = True
    sync_cmb_material_preview(material, force=True)


def _image_uses_alpha(image):
    if image is None:
        return False

    try:
        if not image.has_data:
            image.pixels[0]
        pixels = image.pixels
        return any(pixels[index] < 0.999 for index in range(3, len(pixels), 4))
    except Exception:
        return True


def _cmb_format_for_image(image):
    return "RGBA5551" if _image_uses_alpha(image) else "RGB565"


def _convert_material_to_cmb(material):
    base_color = _principled_base_color(material)
    base_color_image = _principled_base_color_image(material)
    if base_color is not None:
        material.diffuse_color = base_color

    material.use_nodes = False
    _set_cmb_material_type(material)
    if base_color is not None:
        material.cmb_settings.diffuse_color = base_color
    if base_color_image is not None:
        material.cmb_settings.texture_image = base_color_image
        material.cmb_settings.texture_format = _cmb_format_for_image(base_color_image)
        material.cmb_settings.texture_coord_mapping = "UV"
    sync_cmb_material_preview(material, force=True)


class CMB_OT_convert_material(bpy.types.Operator):
    bl_idname = "cmb.convert_material"
    bl_label = "Convert to CMB Material"
    bl_description = "Convert the active Blender material to a CMB material"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_material_from_context(context) is not None

    def execute(self, context):
        material = active_material_from_context(context)
        if material is None:
            self.report({"ERROR"}, "No active material to convert")
            return {"CANCELLED"}

        if is_cmb_material_settings(material.cmb_settings):
            self.report({"INFO"}, f"Material is already CMB: {material.name}")
            return {"FINISHED"}

        _convert_material_to_cmb(material)
        self.report({"INFO"}, f"Converted material to CMB: {material.name}")
        return {"FINISHED"}


class CMB_OT_create_material(bpy.types.Operator):
    bl_idname = "cmb.create_material"
    bl_label = "New CMB Material"
    bl_description = "Create a material configured for CMB export"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(
        name="Name",
        default="CMB Material",
    )

    assign_to_active: bpy.props.BoolProperty(
        name="Assign to Active Object",
        default=True,
    )

    def execute(self, context):
        material = bpy.data.materials.new(self.name)
        material.use_nodes = False
        _set_cmb_material_type(material)
        material.diffuse_color = material.cmb_settings.diffuse_color

        obj = context.object
        if self.assign_to_active and obj is not None and hasattr(obj.data, "materials"):
            obj.data.materials.append(material)
            obj.active_material = material

        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"Created CMB material: {material.name}")
        return {"FINISHED"}


class CMB_OT_convert_all_materials(bpy.types.Operator):
    bl_idname = "cmb.convert_all_materials"
    bl_label = "Convert All Materials"
    bl_description = "Convert every Blender material in the file to a CMB material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        converted = 0
        for material in bpy.data.materials:
            if is_cmb_material_settings(material.cmb_settings):
                continue
            _convert_material_to_cmb(material)
            converted += 1

        self.report({"INFO"}, f"Converted {converted} material(s) to CMB.")
        return {"FINISHED"}


class CMB_OT_refresh_all_material_presets(bpy.types.Operator):
    bl_idname = "cmb.refresh_all_material_presets"
    bl_label = "Refresh All Material Presets"
    bl_description = "Reapply each CMB material's selected preset to its current settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        refreshed = 0
        for material in bpy.data.materials:
            if not is_cmb_material_settings(material.cmb_settings):
                continue
            apply_preset_to_settings(material.cmb_settings, material.cmb_settings.material_preset)
            sync_cmb_material_preview(material, force=True)
            refreshed += 1

        self.report({"INFO"}, f"Refreshed {refreshed} CMB material preset(s)")
        return {"FINISHED"}


class CMB_OT_export(bpy.types.Operator):
    bl_idname = "export_scene.cmb"
    bl_label = "Export CMB"
    bl_description = "Export the scene to a CMB file"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.cmb_export_settings
        filepath = bpy.path.abspath(settings.filepath).strip()
        if not filepath:
            self.report({"ERROR"}, "Set a CMB export path in the CMB sidebar")
            return {"CANCELLED"}

        armature = _selected_armature(context)
        if armature is not None:
            filepath = _filepath_with_armature_name(filepath, armature)
        elif not filepath.lower().endswith(".cmb"):
            filepath += ".cmb"

        options = ExportOptions(
            filepath=filepath,
            global_scale=1.0,
            etc_compression_mode=settings.etc_compression_mode,
        )

        try:
            export_cmb(context, options)
        except CMBExportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, "Success!")
        return {"FINISHED"}


classes = (
    CMB_OT_convert_material,
    CMB_OT_create_material,
    CMB_OT_convert_all_materials,
    CMB_OT_refresh_all_material_presets,
    CMB_OT_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
