import re
from dataclasses import replace
from math import isfinite

from .materials import default_material, material_from_blender
from .mesh_groups import link_mesh_group_names, link_mesh_group_visibility_rules
from .model import CmbModel, CmbPrimitive, CmbVertex
from .skeleton import bones_from_armature


class CmbMeshExportError(ValueError):
    pass


VISIBILITY_ID_PATTERN = re.compile(r"^vis(\d+)_.+")
MATERIAL_ORDER_PATTERN = re.compile(r"^\s*(\d+)(?=$|[._\-\s\]\)])")


def _visibility_id_from_name(name):
    match = VISIBILITY_ID_PATTERN.search(name)
    if match is None:
        raise CmbMeshExportError(
            f"Mesh '{name}' must use the name format 'vis<number>_MeshName'."
        )

    visibility_id = int(match.group(1))
    if visibility_id > 255:
        raise CmbMeshExportError(
            f"Mesh '{name}' cannot have a visibility ID greater than 255."
        )

    return visibility_id


def _visibility_rules_for_object(obj, options):
    if options.simplified_export == "OFF":
        return ((_visibility_id_from_name(obj.name), (0.0, 0.0, 0.0)),)

    visibility_rules = link_mesh_group_visibility_rules(obj.name, options.simplified_export)
    if visibility_rules is None:
        valid_names = ", ".join(link_mesh_group_names(options.simplified_export))
        raise CmbMeshExportError(
            f"Mesh '{obj.name}' is not a Link mesh."
        )
    return visibility_rules


def _translated_vertex_indices(source_indices, translation, global_scale, vertices, vertex_lookup):
    if translation == (0.0, 0.0, 0.0):
        return source_indices

    translated_indices = []
    offset = tuple(component * global_scale for component in translation)
    for source_index in source_indices:
        vertex = vertices[source_index]
        translated_position = tuple(
            vertex.position[axis] + offset[axis]
            for axis in range(3)
        )
        translated_vertex = replace(vertex, position=translated_position)
        translated_index = vertex_lookup.get(translated_vertex)
        if translated_index is None:
            translated_index = len(vertices)
            vertex_lookup[translated_vertex] = translated_index
            vertices.append(translated_vertex)
        translated_indices.append(translated_index)

    return tuple(translated_indices)


def _selected_skeletons(context):
    return [obj for obj in context.selected_objects if obj.type == "ARMATURE"]


def _is_child_of(obj, parent):
    current = obj.parent
    while current is not None:
        if current == parent:
            return True
        current = current.parent
    return False


def _objects_for_export(context):
    skeletons = _selected_skeletons(context)
    if not skeletons:
        raise CmbMeshExportError("Select one skeleton/armature to export")
    if len(skeletons) > 1:
        raise CmbMeshExportError("Select only one skeleton/armature to export")

    skeleton = skeletons[0]
    meshes = [
        obj
        for obj in context.scene.objects
        if obj.type == "MESH" and _is_child_of(obj, skeleton)
    ]
    if not meshes:
        raise CmbMeshExportError(
            f"Selected skeleton '{skeleton.name}' has no child mesh objects"
        )
    multi_material_meshes = [
        obj.name for obj in meshes if len(obj.material_slots) > 1
    ]
    if multi_material_meshes:
        names = ", ".join(sorted(multi_material_meshes))
        raise CmbMeshExportError(
            "Meshes must have no more than one material assigned. "
            f"Culprit mesh(s): {names}"
        )

    bones = bones_from_armature(skeleton)
    bone_lookup = _bone_index_lookup(bones)
    _validate_vertex_weight_counts(meshes, bone_lookup)
    _validate_uv_layer_counts(meshes)

    return skeleton, meshes, bones, bone_lookup


def _safe_name(skeleton):
    return skeleton.name or "cmb_model"


def _rgba_float_to_rgba8(color):
    return tuple(max(0, min(255, round(channel * 255))) for channel in color)


def _active_color_layer(mesh):
    color_attributes = getattr(mesh, "color_attributes", None)
    if color_attributes:
        active_color = getattr(color_attributes, "active_color", None)
        active = getattr(color_attributes, "active", None)
        return active_color or active

    vertex_colors = getattr(mesh, "vertex_colors", None)
    if vertex_colors:
        return vertex_colors.active

    return None


def _loop_color(mesh, color_layer, loop_index, vertex_index):
    if color_layer is None:
        return None

    domain = getattr(color_layer, "domain", "CORNER")
    index = vertex_index if domain == "POINT" else loop_index
    return _rgba_float_to_rgba8(color_layer.data[index].color)


def _loop_uv(uv_layer, loop_index):
    if uv_layer is None:
        return None

    uv = uv_layer.data[loop_index].uv
    u = float(uv.x)
    v = float(uv.y)
    if not isfinite(u) or not isfinite(v):
        return None
    if abs(u) > 1024.0 or abs(v) > 1024.0:
        return None
    return (u, v)


def _uv_layers(mesh):
    layers = list(mesh.uv_layers)
    return tuple((layers + [None, None, None])[:3])


def _material_index_for_slot(material, materials, material_lookup):
    if material is None:
        key = None
        cmb_material = default_material()
    else:
        key = material.name
        try:
            cmb_material = material_from_blender(material)
        except ValueError as exc:
            raise CmbMeshExportError(str(exc)) from exc

    if key in material_lookup:
        return material_lookup[key]

    material_lookup[key] = len(materials)
    materials.append(cmb_material)
    return material_lookup[key]


def _explicit_material_order(material):
    if material is None:
        return None
    match = MATERIAL_ORDER_PATTERN.match(material.name)
    if match is None:
        return None
    return int(match.group(1))


def _sort_materials_by_explicit_order(materials, primitives):
    explicit_orders = {}
    for index, material in enumerate(materials):
        order = _explicit_material_order(material)
        if order is None:
            continue
        if order in explicit_orders:
            other = materials[explicit_orders[order]].name
            raise CmbMeshExportError(
                f"Duplicate CMB material order {order}: '{other}' and '{material.name}'"
            )
        explicit_orders[order] = index

    if not explicit_orders:
        return tuple(materials), tuple(primitives)

    sorted_old_indices = sorted(
        range(len(materials)),
        key=lambda index: (
            _explicit_material_order(materials[index]) is None,
            _explicit_material_order(materials[index])
            if _explicit_material_order(materials[index]) is not None
            else index,
            index,
        ),
    )
    old_to_new = {
        old_index: new_index for new_index, old_index in enumerate(sorted_old_indices)
    }
    sorted_materials = tuple(materials[old_index] for old_index in sorted_old_indices)
    remapped_primitives = tuple(
        replace(primitive, material_index=old_to_new[primitive.material_index])
        for primitive in primitives
    )
    return sorted_materials, remapped_primitives


def _sort_primitives_by_draw_order(materials, primitives):
    return tuple(
        sorted(
            primitives,
            key=lambda primitive: (
                materials[primitive.material_index].render_layer,
                primitive.visibility_id,
            ),
        )
    )


def _object_material_indices(obj, materials, material_lookup):
    if not obj.material_slots:
        return [_material_index_for_slot(None, materials, material_lookup)]

    return [
        _material_index_for_slot(slot.material, materials, material_lookup)
        for slot in obj.material_slots
    ]


def _bone_index_lookup(bones):
    return {bone.name: index for index, bone in enumerate(bones)}


def _vertex_influences(obj, vertex, bone_lookup):
    influences = []

    for group in vertex.groups:
        if group.weight <= 0.0:
            continue
        if group.group >= len(obj.vertex_groups):
            continue

        bone_index = bone_lookup.get(obj.vertex_groups[group.group].name)
        if bone_index is None:
            continue

        influences.append((bone_index, float(group.weight)))

    if not influences:
        return (0, 0, 0, 0), (100, 0, 0, 0)

    influences.sort(key=lambda item: item[1], reverse=True)
    if len(influences) > 4:
        raise CmbMeshExportError(
            f"Vertex {vertex.index} in mesh '{obj.name}' has more than 4 bone influences"
        )

    total_weight = sum(weight for _bone_index, weight in influences)
    if total_weight <= 0.0:
        return (0, 0, 0, 0), (100, 0, 0, 0)

    normalized = [
        (bone_index, max(0, min(100, round((weight / total_weight) * 100))))
        for bone_index, weight in influences
    ]
    weight_sum = sum(weight for _bone_index, weight in normalized)
    if normalized:
        first_bone, first_weight = normalized[0]
        normalized[0] = (first_bone, max(0, min(100, first_weight + (100 - weight_sum))))

    bone_indices = [bone_index for bone_index, _weight in normalized]
    bone_weights = [weight for _bone_index, weight in normalized]
    while len(bone_indices) < 4:
        bone_indices.append(0)
        bone_weights.append(0)

    return tuple(bone_indices[:4]), tuple(bone_weights[:4])


def _validate_vertex_weight_counts(objects, bone_lookup):
    offenders = []

    for obj in objects:
        vertex_groups = obj.vertex_groups
        for vertex in obj.data.vertices:
            influence_count = 0
            for group in vertex.groups:
                if group.weight <= 0.0:
                    continue
                if group.group >= len(vertex_groups):
                    continue
                if obj.vertex_groups[group.group].name in bone_lookup:
                    influence_count += 1

            if influence_count > 4:
                offenders.append(f"{obj.name}[v{vertex.index}: {influence_count}]")

    if offenders:
        preview = ", ".join(offenders[:16])
        suffix = "" if len(offenders) <= 16 else f", ... {len(offenders) - 16} more"
        raise CmbMeshExportError(
            "CMB export supports at most 4 bone weights per vertex. "
            f"Culprit vertex(s): {preview}{suffix}"
        )


def _validate_uv_layer_counts(objects):
    offenders = [
        f"{obj.name} ({len(obj.data.uv_layers)} UV maps)"
        for obj in objects
        if len(obj.data.uv_layers) > 3
    ]
    if offenders:
        raise CmbMeshExportError(
            "Mesh(es) " + ", ".join(offenders) + " contain more than 3 UV maps!"
        )


def _normal_matrix(matrix):
    matrix3 = matrix.to_3x3()
    try:
        return matrix3.inverted().transposed()
    except ValueError:
        return matrix3


def _append_object_mesh(
    skeleton,
    obj,
    options,
    bone_lookup,
    vertices,
    vertex_lookup,
    primitives,
    materials,
    material_lookup,
):
    visibility_rules = _visibility_rules_for_object(obj, options)
    mesh = obj.data

    mesh.calc_loop_triangles()
    uv_layers = _uv_layers(mesh)
    color_layer = _active_color_layer(mesh)
    object_materials = _object_material_indices(obj, materials, material_lookup)
    mesh_to_armature = skeleton.matrix_world.inverted() @ obj.matrix_world
    normal_matrix = _normal_matrix(mesh_to_armature)
    object_indices = []

    for loop_triangle in mesh.loop_triangles:
        if len(loop_triangle.loops) != 3:
            continue

        material_slot_index = min(loop_triangle.material_index, len(object_materials) - 1)
        material_index = object_materials[material_slot_index]

        for loop_index in loop_triangle.loops:
            loop = mesh.loops[loop_index]
            vertex = mesh.vertices[loop.vertex_index]

            position = mesh_to_armature @ vertex.co
            position = position * options.global_scale
            normal = normal_matrix @ loop.normal
            normal.normalize()
            bone_indices, bone_weights = _vertex_influences(
                obj, vertex, bone_lookup
            )

            cmb_vertex = CmbVertex(
                position=(float(position.x), float(position.y), float(position.z)),
                normal=(float(normal.x), float(normal.y), float(normal.z)),
                color=_loop_color(mesh, color_layer, loop_index, loop.vertex_index),
                uv0=_loop_uv(uv_layers[0], loop_index),
                uv1=_loop_uv(uv_layers[1], loop_index),
                uv2=_loop_uv(uv_layers[2], loop_index),
                bone_indices=bone_indices,
                bone_weights=bone_weights,
            )

            vertex_index = vertex_lookup.get(cmb_vertex)
            if vertex_index is None:
                vertex_index = len(vertices)
                vertex_lookup[cmb_vertex] = vertex_index
                vertices.append(cmb_vertex)

            object_indices.append(vertex_index)

    if object_indices:
        for visibility_id, translation in visibility_rules:
            primitive_indices = _translated_vertex_indices(
                tuple(object_indices),
                translation,
                options.global_scale,
                vertices,
                vertex_lookup,
            )
            primitives.append(
                CmbPrimitive(
                    indices=primitive_indices,
                    material_index=object_materials[0],
                    visibility_id=visibility_id,
                    mesh_name=obj.name,
                )
            )


def build_cmb_model_from_scene(context, options):
    skeleton, objects, bones, bone_lookup = _objects_for_export(context)

    vertices = []
    vertex_lookup = {}
    primitives = []
    materials = []
    material_lookup = {}

    for obj in objects:
        _append_object_mesh(
            skeleton,
            obj,
            options,
            bone_lookup,
            vertices,
            vertex_lookup,
            primitives,
            materials,
            material_lookup,
        )

    if not vertices or not primitives:
        raise CmbMeshExportError("Mesh objects did not produce any triangles")

    sorted_materials, remapped_primitives = _sort_materials_by_explicit_order(
        materials, primitives
    )
    sorted_primitives = _sort_primitives_by_draw_order(
        sorted_materials, remapped_primitives
    )

    return CmbModel(
        name=_safe_name(skeleton),
        bones=bones,
        vertices=tuple(vertices),
        primitives=sorted_primitives,
        materials=sorted_materials,
    )
