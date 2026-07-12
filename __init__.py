bl_info = {
    "name": "CMB Exporter",
    "author": "Jameriquiah",
    "version": (1, 2),
    "blender": (3, 5, 0),
    "location": "3D View > Sidebar > CMB",
    "description": "Export models as CMB files for OOT3D",
    "category": "Import-Export",
}

import importlib


MODULE_NAMES = (
    "cmb_internal.properties",
    "cmb_internal.operators",
    "cmb_internal.importer",
    "cmb_internal.panels",
    "cmb_internal.3DS_Link_tool",
)


def _load_modules():
    return tuple(importlib.import_module(f"{__name__}.{name}") for name in MODULE_NAMES)


def register():
    for module in _load_modules():
        try:
            module.unregister()
        except RuntimeError:
            pass
        module.register()


def unregister():
    for module in reversed(_load_modules()):
        module.unregister()
