from dataclasses import dataclass, field


@dataclass(frozen=True)
class CmbBone:
    name: str
    parent_index: int
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float]
    scale: tuple[float, float, float]
    local_matrix: tuple[tuple[float, float, float, float], ...]
    inverse_bind_matrix: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True)
class CmbVertex:
    position: tuple[float, float, float]
    normal: tuple[float, float, float] | None = None
    color: tuple[int, int, int, int] | None = None
    uv0: tuple[float, float] | None = None
    uv1: tuple[float, float] | None = None
    uv2: tuple[float, float] | None = None
    bone_indices: tuple[int, int, int, int] = (0, 0, 0, 0)
    bone_weights: tuple[int, int, int, int] = (100, 0, 0, 0)


@dataclass(frozen=True)
class CmbPrimitive:
    indices: tuple[int, ...]
    material_index: int = 0
    visibility_id: int = 0
    mesh_name: str = ""


@dataclass(frozen=True)
class CmbMaterial:
    name: str
    texture_format: str = "RGB565"
    texture_image_name: str = ""
    texture_index: int = -1
    texture_min_filter: str = "LINEAR"
    texture_mag_filter: str = "LINEAR"
    texture_wrap_u: str = "REPEAT"
    texture_wrap_v: str = "REPEAT"
    texture_coord_matrix_mode: int = 0
    texture_coord_reference_camera: int = 0
    texture_coord_mapping: int = 1
    texture_coord_source: int = 0
    texture_coord_scale: tuple[float, float] = (1.0, 1.0)
    texture_coord_rotation: float = 0.0
    texture_coord_translation: tuple[float, float] = (0.0, 0.0)
    texture1_format: str = "RGB565"
    texture1_image_name: str = ""
    texture1_index: int = -1
    texture1_min_filter: str = "LINEAR"
    texture1_mag_filter: str = "LINEAR"
    texture1_wrap_u: str = "REPEAT"
    texture1_wrap_v: str = "REPEAT"
    texture1_coord_matrix_mode: int = 0
    texture1_coord_reference_camera: int = 0
    texture1_coord_mapping: int = 3
    texture1_coord_source: int = 0
    texture1_coord_scale: tuple[float, float] = (1.0, 1.0)
    texture1_coord_rotation: float = 0.0
    texture1_coord_translation: tuple[float, float] = (0.0, 0.0)
    texture2_format: str = "RGB565"
    texture2_image_name: str = ""
    texture2_index: int = -1
    texture2_min_filter: str = "LINEAR"
    texture2_mag_filter: str = "LINEAR"
    texture2_wrap_u: str = "REPEAT"
    texture2_wrap_v: str = "REPEAT"
    texture2_coord_matrix_mode: int = 0
    texture2_coord_reference_camera: int = 0
    texture2_coord_mapping: int = 3
    texture2_coord_source: int = 0
    texture2_coord_scale: tuple[float, float] = (1.0, 1.0)
    texture2_coord_rotation: float = 0.0
    texture2_coord_translation: tuple[float, float] = (0.0, 0.0)
    fragment_lighting: bool = False
    vertex_lighting: bool = False
    is_fog_enabled: bool = False
    render_layer: int = 0
    face_culling: bool = True
    polygon_offset_enabled: bool = False
    polygon_offset: int = 0
    emission_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    ambient_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    diffuse_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    specular0_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    specular1_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    constant_colors: tuple[tuple[int, int, int, int], ...] = (
        (255, 255, 255, 255),
        (255, 255, 255, 255),
        (255, 255, 255, 255),
        (255, 255, 255, 255),
        (255, 255, 255, 255),
        (255, 255, 255, 255),
    )
    buffer_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    alpha_test_enabled: bool = False
    alpha_reference: int = 0
    alpha_function: str = "ALWAYS"
    depth_test_enabled: bool = True
    depth_write_enabled: bool = True
    depth_function: str = "LEQUAL"
    blend_mode: str = "OPAQUE"
    blend_alpha_src_function: str = ""
    blend_alpha_dst_function: str = ""
    blend_alpha_equation: str = ""
    blend_color_src_function: str = ""
    blend_color_dst_function: str = ""
    blend_color_equation: str = ""
    blend_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    tex_env_stages: tuple[tuple[int, ...], ...] = ()


@dataclass(frozen=True)
class CmbModel:
    name: str
    bones: tuple[CmbBone, ...] = field(default_factory=tuple)
    vertices: tuple[CmbVertex, ...] = field(default_factory=tuple)
    primitives: tuple[CmbPrimitive, ...] = field(default_factory=tuple)
    materials: tuple[CmbMaterial, ...] = field(default_factory=tuple)
    textures: tuple = field(default_factory=tuple)

    @property
    def visibility_id_count(self):
        return 48
