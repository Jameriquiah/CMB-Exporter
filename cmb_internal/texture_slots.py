TEXTURE_SLOT_INDICES = range(3)


def texture_slot_prefix(slot_index):
    return "texture" if slot_index == 0 else f"texture{slot_index}"


def texture_slot_attr(slot_index, field):
    return f"{texture_slot_prefix(slot_index)}_{field}"


def texture_slot_values(obj, slot_index, *fields):
    return tuple(getattr(obj, texture_slot_attr(slot_index, field)) for field in fields)


def iter_texture_slot_values(obj, *fields):
    for slot_index in TEXTURE_SLOT_INDICES:
        yield slot_index, texture_slot_values(obj, slot_index, *fields)
