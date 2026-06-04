from .model import CmbBone
from math import pi


class CmbSkeletonExportError(ValueError):
    pass


def _matrix_to_tuple(matrix):
    return tuple(tuple(float(value) for value in row) for row in matrix)


def _vector_to_tuple(vector):
    return (float(vector.x), float(vector.y), float(vector.z))


def _euler_to_tuple(euler):
    return _canonical_xyz_euler(float(euler.x), float(euler.y), float(euler.z))


def _wrap_pi(value):
    while value > pi:
        value -= pi * 2.0
    while value <= -pi:
        value += pi * 2.0
    return value


def _canonical_xyz_euler(x, y, z):
    if y > pi / 2.0:
        x += pi
        y = pi - y
        z += pi
    elif y < -pi / 2.0:
        x += pi
        y = -pi - y
        z += pi

    return (_wrap_pi(x), _wrap_pi(y), _wrap_pi(z))


def _ordered_bones(armature):
    ordered = []

    def visit(bone):
        ordered.append(bone)
        children = [child for child in armature.data.bones if child.parent == bone]
        for child in children:
            visit(child)

    roots = [bone for bone in armature.data.bones if bone.parent is None]
    for root in roots:
        visit(root)

    return ordered


def _local_matrix(bone):
    if bone.parent is None:
        return bone.matrix_local.copy()
    return bone.parent.matrix_local.inverted() @ bone.matrix_local


def bones_from_armature(armature):
    if armature.type != "ARMATURE":
        raise CmbSkeletonExportError(f"Object '{armature.name}' is not an armature")

    ordered = _ordered_bones(armature)
    if not ordered:
        raise CmbSkeletonExportError(f"Selected armature '{armature.name}' has no bones")

    bone_indices = {bone.name: index for index, bone in enumerate(ordered)}
    bones = []

    for bone in ordered:
        local_matrix = _local_matrix(bone)
        translation, rotation, scale = local_matrix.decompose()
        parent_index = -1 if bone.parent is None else bone_indices[bone.parent.name]

        bones.append(
            CmbBone(
                name=bone.name,
                parent_index=parent_index,
                translation=_vector_to_tuple(translation),
                rotation=_euler_to_tuple(rotation.to_euler("XYZ")),
                scale=_vector_to_tuple(scale),
                local_matrix=_matrix_to_tuple(local_matrix),
                inverse_bind_matrix=_matrix_to_tuple(bone.matrix_local.inverted()),
            )
        )

    return tuple(bones)
