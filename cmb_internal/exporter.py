from dataclasses import dataclass
from pathlib import Path

from .cmb_writer import CmbWriteError, write_cmb_file
from .mesh import CmbMeshExportError, build_cmb_model_from_scene
from .skeleton import CmbSkeletonExportError
from .textures import CmbTextureExportError, attach_textures_to_model


@dataclass(frozen=True)
class ExportOptions:
    filepath: str
    global_scale: float
    simplified_export: str = "OFF"


class CMBExportError(RuntimeError):
    pass


def export_cmb(context, options):
    filepath = Path(options.filepath)
    if filepath.suffix.lower() != ".cmb":
        filepath = filepath.with_suffix(".cmb")

    try:
        model = build_cmb_model_from_scene(context, options)
        model = attach_textures_to_model(
            model,
            context.blend_data,
        )
    except (CmbMeshExportError, CmbSkeletonExportError, CmbTextureExportError) as exc:
        raise CMBExportError(str(exc)) from exc

    try:
        return write_cmb_file(model, filepath)
    except CmbWriteError as exc:
        raise CMBExportError(str(exc)) from exc
