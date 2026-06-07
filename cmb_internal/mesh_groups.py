import re


BLENDER_NUMERIC_SUFFIX_PATTERN = re.compile(r"\.\d{3}$")
ADULT_MESH_GROUP_VISIBILITY_IDS = {
    'BiggoronsBlade': (37,),
    'BiggoronsSheath': (7, 8, 9, 10, 11, 12),
    'BiggoronsSwordA': (37, 38),
    'BiggoronsSwordB': (8, 11, 12),
    'Body': (45,),
    'Bottle': (25,),
    'BottleHand': (24,),
    'Bow': (29,),
    'BowString': (43,),
    'BrokenBlade': (38,),
    'DekuStick': (44,),
    'Earrings': (47,),
    'FPSArmL': (26,),
    'FPSArmR': (28,),
    'FPSBow': (30,),
    'FPSHandL': (27,),
    'FPSHookshot': (34,),
    'FistL': (14,),
    'FistR': (21,),
    'GauntletArmL': (4,),
    'GauntletArmR': (17,),
    'GauntletFistL': (5,),
    'GauntletFistR': (18,),
    'GauntletHandL': (6,),
    'GauntletHandR': (19,),
    'Hammer': (32,),
    'HandL': (13,),
    'HandR': (20,),
    'Head': (46,),
    'Hookshot': (33,),
    'HoverBootL': (15,),
    'HoverBootR': (22,),
    'HylianShieldA': (23,),
    'HylianShieldB': (0, 1, 10, 11),
    'IronBootL': (35,),
    'IronBootR': (36,),
    'MasterSheath': (0, 1, 2, 3, 31, 42),
    'MasterSwordA': (16,),
    'MasterSwordB': (0, 2, 31),
    'MirrorShieldA': (39,),
    'MirrorShieldB': (2, 3, 7, 8),
    'OcarinaHolding': (41,),
    'OcarinaPlaying': (40,),
}

CHILD_MESH_GROUP_VISIBILITY_IDS = {
    'Body': (24,),
    'BodyInner': (25,),
    'Boomerang': (6,),
    'Bottle': (8,),
    'BottleHand': (7,),
    'DekuShieldA': (5,),
    'DekuShieldB': (11, 12, 13),
    'DekuStick': (23,),
    'FPSSlingshot': (20,),
    'FairyOcarina': (17,),
    'FistL': (1,),
    'FistR': (4,),
    'GoronBracelet': (15,),
    'HandL': (0,),
    'HandR': (3,),
    'Head': (26,),
    'HylianShield': (9, 10),
    'KokiriSwordA': (2,),
    'KokiriSwordB': (9, 11, 14),
    'MasterSword': (16,),
    'OcarinaOfTime': (18,),
    'Sheath': (9, 10, 11, 12, 14, 21),
    'Slingshot': (19,),
    'SlingshotString': (22,),
}

CHILD_MESH_GROUP_TRANSLATIONS = {
    "KokiriSwordB": {
        14: (0.0, 0.0, -45.0),
    },
    "Sheath": {
        14: (0.0, 0.0, -45.0),
        21: (0.0, 0.0, -45.0),
    },
}

MESH_GROUP_VISIBILITY_IDS = {
    "ADULT": ADULT_MESH_GROUP_VISIBILITY_IDS,
    "CHILD": CHILD_MESH_GROUP_VISIBILITY_IDS,
}


def base_mesh_group_name(name):
    base_name = BLENDER_NUMERIC_SUFFIX_PATTERN.sub("", name)
    return base_name.split("_", 1)[0]


def link_mesh_group_visibility_ids(name, mode):
    return MESH_GROUP_VISIBILITY_IDS[mode].get(base_mesh_group_name(name))


def link_mesh_group_visibility_rules(name, mode):
    group_name = base_mesh_group_name(name)
    visibility_ids = MESH_GROUP_VISIBILITY_IDS[mode].get(group_name)
    if visibility_ids is None:
        return None
    translations = CHILD_MESH_GROUP_TRANSLATIONS.get(group_name, {}) if mode == "CHILD" else {}
    return tuple((visibility_id, translations.get(visibility_id, (0.0, 0.0, 0.0))) for visibility_id in visibility_ids)


def link_mesh_group_names(mode):
    return tuple(sorted(MESH_GROUP_VISIBILITY_IDS[mode]))
