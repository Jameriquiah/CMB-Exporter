def active_material_from_context(context):
    material = getattr(context, "material", None)
    if material is not None:
        return material

    obj = getattr(context, "object", None)
    return getattr(obj, "active_material", None) if obj is not None else None
