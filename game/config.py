from dataclasses import dataclass


@dataclass
class Settings:
    seed: int = 938472
    chunk_size: int = 64
    world_half_size: int = 1024
    terrain_step: int = 4
    render_radius: int = 2
    active_radius: int = 1
    trees_per_chunk: int = 32
    grass_per_chunk: int = 40000
    rocks_per_chunk: int = 12
    ducks_per_chunk: int = 5
    upload_budget_ms: float = 2.0
    upload_steps_per_frame: int = 8
    chunk_cache_count: int = 8
    chunk_cache_mb: int = 96
    grass_cell_size: int = 16
    width: int = 1280
    height: int = 720

    def __post_init__(self):
        if self.chunk_size <= 0 or self.terrain_step <= 0:
            raise ValueError('Chunk e passo do terreno devem ser positivos.')
        if self.chunk_size % self.terrain_step:
            raise ValueError('O passo do terreno deve dividir o chunk.')
        if self.world_half_size % self.chunk_size:
            raise ValueError('O limite do mundo deve ser multiplo do chunk.')
        if not 1 <= self.render_radius <= 5:
            raise ValueError('Render radius deve estar entre 1 e 5.')
        if self.upload_budget_ms <= 0 or self.upload_steps_per_frame <= 0:
            raise ValueError('Orcamento de upload deve ser positivo.')
        if self.chunk_cache_count < 0 or self.chunk_cache_mb < 0:
            raise ValueError('Limites de cache devem ser nao negativos.')
        if self.grass_cell_size <= 0 or self.chunk_size % self.grass_cell_size:
            raise ValueError('A celula de grama deve dividir o chunk.')
