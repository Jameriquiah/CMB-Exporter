bl_info = {
    "name": "3DSLinkTool",
    "author": "Skilar Babcock",
    "version": (1, 0, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > Sidebar > 3DSLinkTool",
    "description": (
        "Renames Ocarina of Time 3D Link bones and vertex groups "
        "between readable edit names and original export names"
    ),
    "category": "Rigging",
}

import bpy


# =========================================================
# Bone name mappings
# =========================================================

EXPORT_TO_EDIT_NAMES = {
    "Bone_2": "waist",
    "Bone_3": "legL1",
    "Bone_4": "legL2",
    "Bone_5": "footL",
    "Bone_6": "legR1",
    "Bone_7": "legR2",
    "Bone_8": "footR",
    "Bone_9": "backbone1",
    "Bone_10": "backbone2",
    "Bone_11": "head",
    "Bone_12": "z_cap",
    "Bone_13": "shoulderL",
    "Bone_14": "armL1",
    "Bone_15": "armL2",
    "Bone_16": "handL",
    "Bone_17": "shoulderR",
    "Bone_18": "armR1",
    "Bone_19": "armR2",
    "Bone_20": "handR",
}

EDIT_TO_EXPORT_NAMES = {
    edit_name: export_name
    for export_name, edit_name in EXPORT_TO_EDIT_NAMES.items()
}


# =========================================================
# Utility functions
# =========================================================

def find_target_armature(context):
    """
    Finds the armature associated with the current selection.

    Search order:
    1. Active object if it is an armature.
    2. Active mesh's Armature modifier.
    3. Active mesh's armature parent.
    4. Any selected armature.
    5. Any selected mesh's Armature modifier or parent.
    """

    active_object = context.active_object

    if active_object is not None:
        if active_object.type == 'ARMATURE':
            return active_object

        if active_object.type == 'MESH':
            for modifier in active_object.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object is not None:
                    return modifier.object

            if (
                active_object.parent is not None
                and active_object.parent.type == 'ARMATURE'
            ):
                return active_object.parent

    for obj in context.selected_objects:
        if obj.type == 'ARMATURE':
            return obj

    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue

        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object is not None:
                return modifier.object

        if obj.parent is not None and obj.parent.type == 'ARMATURE':
            return obj.parent

    return None


def get_related_meshes(armature_object):
    """
    Finds every mesh in the current Blender file associated with
    the specified armature.

    A mesh is considered related when:
    - It has an Armature modifier targeting the armature.
    - It is directly parented to the armature.
    - It is bone-parented to the armature.
    """

    related_meshes = []

    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue

        is_related = False

        if obj.parent == armature_object:
            is_related = True

        if not is_related:
            for modifier in obj.modifiers:
                if (
                    modifier.type == 'ARMATURE'
                    and modifier.object == armature_object
                ):
                    is_related = True
                    break

        if is_related:
            related_meshes.append(obj)

    return related_meshes


def make_temporary_name(original_name):
    """
    Generates a temporary name used to avoid Blender name collisions.
    """

    return f"__3DSLINKTOOL_TEMP__{original_name}"


def rename_bones(armature_object, name_mapping):
    """
    Renames bones on the supplied armature.

    Uses a two-stage rename:
    1. Source names become temporary names.
    2. Temporary names become final names.

    This avoids conflicts with existing names.
    """

    bones = armature_object.data.bones
    rename_jobs = []

    for source_name, destination_name in name_mapping.items():
        bone = bones.get(source_name)

        if bone is not None:
            rename_jobs.append((bone, destination_name))

    for bone, destination_name in rename_jobs:
        bone.name = make_temporary_name(bone.name)

    renamed_count = 0

    for bone, destination_name in rename_jobs:
        bone.name = destination_name
        renamed_count += 1

    return renamed_count


def rename_vertex_groups(mesh_object, name_mapping):
    """
    Renames matching vertex groups on one mesh object.

    Uses the same two-stage rename system as the bones.
    """

    rename_jobs = []

    for source_name, destination_name in name_mapping.items():
        vertex_group = mesh_object.vertex_groups.get(source_name)

        if vertex_group is not None:
            rename_jobs.append((vertex_group, destination_name))

    for vertex_group, destination_name in rename_jobs:
        vertex_group.name = make_temporary_name(vertex_group.name)

    renamed_count = 0

    for vertex_group, destination_name in rename_jobs:
        vertex_group.name = destination_name
        renamed_count += 1

    return renamed_count


def restore_previous_mode(context, previous_active_object, previous_mode):
    """
    Attempts to restore the previous active object and interaction mode.
    """

    if previous_active_object is None:
        return

    try:
        context.view_layer.objects.active = previous_active_object
        previous_active_object.select_set(True)
    except RuntimeError:
        return

    mode_map = {
        'EDIT_ARMATURE': 'EDIT',
        'EDIT_MESH': 'EDIT',
        'POSE': 'POSE',
        'OBJECT': 'OBJECT',
        'WEIGHT_PAINT': 'WEIGHT_PAINT',
        'VERTEX_PAINT': 'VERTEX_PAINT',
        'TEXTURE_PAINT': 'TEXTURE_PAINT',
        'SCULPT': 'SCULPT',
    }

    restore_mode = mode_map.get(previous_mode)

    if restore_mode is None or restore_mode == 'OBJECT':
        return

    try:
        bpy.ops.object.mode_set(mode=restore_mode)
    except RuntimeError:
        pass


def perform_rename(context, name_mapping):
    """
    Renames the armature bones and all associated mesh vertex groups.
    """

    armature_object = find_target_armature(context)

    if armature_object is None:
        return None

    previous_active_object = context.view_layer.objects.active
    previous_mode = context.mode
    previous_selected_objects = list(context.selected_objects)

    if context.object is not None and context.object.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass

    related_meshes = get_related_meshes(armature_object)

    renamed_bones = rename_bones(
        armature_object,
        name_mapping,
    )

    renamed_vertex_groups = 0

    for mesh_object in related_meshes:
        renamed_vertex_groups += rename_vertex_groups(
            mesh_object,
            name_mapping,
        )

    try:
        bpy.ops.object.select_all(action='DESELECT')
    except RuntimeError:
        pass

    for obj in previous_selected_objects:
        if obj.name in bpy.data.objects:
            try:
                obj.select_set(True)
            except RuntimeError:
                pass

    restore_previous_mode(
        context,
        previous_active_object,
        previous_mode,
    )

    return {
        "armature": armature_object,
        "mesh_count": len(related_meshes),
        "bone_count": renamed_bones,
        "vertex_group_count": renamed_vertex_groups,
    }


# =========================================================
# Operators
# =========================================================

class LINK3DS_OT_edit_ready(bpy.types.Operator):
    bl_idname = "link3ds.edit_ready"
    bl_label = "Edit Ready"
    bl_description = (
        "Rename Bone_number names to readable bone and vertex group names"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        result = perform_rename(
            context,
            EXPORT_TO_EDIT_NAMES,
        )

        if result is None:
            self.report(
                {'ERROR'},
                "No armature found. Select the skeleton or a connected mesh.",
            )
            return {'CANCELLED'}

        if result["bone_count"] == 0:
            self.report(
                {'WARNING'},
                "No export-ready Bone_number names were found.",
            )
            return {'FINISHED'}

        self.report(
            {'INFO'},
            (
                f"Edit Ready: renamed {result['bone_count']} bones and "
                f"{result['vertex_group_count']} vertex groups across "
                f"{result['mesh_count']} mesh object(s)."
            ),
        )

        return {'FINISHED'}


class LINK3DS_OT_export_ready(bpy.types.Operator):
    bl_idname = "link3ds.export_ready"
    bl_label = "Export Ready"
    bl_description = (
        "Restore readable bone and vertex group names to Bone_number names"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        result = perform_rename(
            context,
            EDIT_TO_EXPORT_NAMES,
        )

        if result is None:
            self.report(
                {'ERROR'},
                "No armature found. Select the skeleton or a connected mesh.",
            )
            return {'CANCELLED'}

        if result["bone_count"] == 0:
            self.report(
                {'WARNING'},
                "No edit-ready readable bone names were found.",
            )
            return {'FINISHED'}

        self.report(
            {'INFO'},
            (
                f"Export Ready: renamed {result['bone_count']} bones and "
                f"{result['vertex_group_count']} vertex groups across "
                f"{result['mesh_count']} mesh object(s)."
            ),
        )

        return {'FINISHED'}


# =========================================================
# Weight optimizer
# =========================================================

def quantize_weight(value, steps):
    step_size = 1.0 / steps
    return round(value / step_size) * step_size


def optimize_weights_on_object(obj, steps):
    """
    Quantizes and normalizes weights on one mesh object.
    """

    if obj.type != 'MESH':
        return 0

    if not obj.vertex_groups:
        return 0

    optimized_vertices = 0

    for vertex in obj.data.vertices:
        assignments = list(vertex.groups)

        if not assignments:
            continue

        quantized = []

        for assignment in assignments:
            weight = quantize_weight(
                assignment.weight,
                steps,
            )

            weight = min(max(weight, 0.0), 1.0)

            quantized.append(
                (assignment.group, weight)
            )

        total = sum(
            weight
            for group_index, weight in quantized
        )

        if total == 0.0:
            equal_weight = 1.0 / len(quantized)

            quantized = [
                (group_index, equal_weight)
                for group_index, weight in quantized
            ]

        else:
            quantized = [
                (group_index, weight / total)
                for group_index, weight in quantized
            ]

        for group_index, weight in quantized:
            vertex_group = obj.vertex_groups[group_index]

            vertex_group.add(
                [vertex.index],
                weight,
                'REPLACE',
            )

        optimized_vertices += 1

    return optimized_vertices


class LINK3DS_OT_optimize_weights(bpy.types.Operator):
    bl_idname = "link3ds.optimize_weights"
    bl_label = "Optimize Weights"
    bl_description = (
        "Clamp, quantize, and normalize vertex weights "
        "on all visible mesh objects"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        steps = int(
            context.scene.link3ds_optimize_weights_steps
        )

        optimized_meshes = 0
        optimized_vertices = 0

        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            if not obj.visible_get():
                continue

            vertex_count = optimize_weights_on_object(
                obj,
                steps,
            )

            if vertex_count > 0:
                optimized_meshes += 1
                optimized_vertices += vertex_count

        self.report(
            {'INFO'},
            (
                f"Optimized {optimized_vertices} vertices across "
                f"{optimized_meshes} visible mesh object(s) "
                f"using {steps} quantize steps."
            ),
        )

        return {'FINISHED'}


# =========================================================
# User interface
# =========================================================

class LINK3DS_PT_main_panel(bpy.types.Panel):
    bl_label = "3DSLinkTool"
    bl_idname = "LINK3DS_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSLinkTool"

    def draw(self, context):
        layout = self.layout

        column = layout.column(align=True)
        column.label(text="Bone Names")

        edit_button = column.operator(
            "link3ds.edit_ready",
            text="Edit Ready",
            icon='ARMATURE_DATA',
        )

        export_button = column.operator(
            "link3ds.export_ready",
            text="Export Ready",
            icon='EXPORT',
        )

        layout.separator()

        box = layout.box()
        box.label(text="Edit Ready")
        box.label(text="Readable bone names", icon='CHECKMARK')

        box = layout.box()
        box.label(text="Export Ready")
        box.label(text="Original Bone_number names", icon='CHECKMARK')


# =========================================================
# Registration
# =========================================================

classes = (
    LINK3DS_OT_edit_ready,
    LINK3DS_OT_export_ready,
    LINK3DS_OT_optimize_weights,
    LINK3DS_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.link3ds_optimize_weights_steps = bpy.props.EnumProperty(
        name="Optimize Weights Steps",
        description="How finely vertex weights are quantized",
        items=[
            (
                '4',
                "Lowest Quality (4 steps)",
                "Most optimized, lowest weight precision",
            ),
            (
                '10',
                "Balanced (10 steps)",
                "Balanced optimization and weight precision",
            ),
            (
                '25',
                "Highest Quality (25 steps)",
                "Least optimized, highest weight precision",
            ),
        ],
        default='10',
    )


def unregister():
    if hasattr(
        bpy.types.Scene,
        "link3ds_optimize_weights_steps",
    ):
        del bpy.types.Scene.link3ds_optimize_weights_steps

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()