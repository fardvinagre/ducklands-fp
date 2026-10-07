from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from game.config import Settings
from game.world.terrain import Terrain


class ChunkState(Enum):
    UNLOADED = auto()
    LOADING = auto()
    ACTIVE = auto()
    SLEEPING = auto()


@dataclass
class ChunkData:
    key: tuple[int, int]
    vertices: np.ndarray
    triangles: np.ndarray
    colors: np.ndarray
    trees: np.ndarray
    grass: np.ndarray
    rocks: np.ndarray
    ducks: np.ndarray


def generate_chunk(key: tuple[int, int], settings: Settings, terrain: Terrain) -> ChunkData:
    """Worker: somente dados NumPy, sem acesso ao scene graph."""
    cx, cy = key
    rng = np.random.default_rng(np.random.SeedSequence([settings.seed, cx & 0xffffffff, cy & 0xffffffff]))
    size, step = settings.chunk_size, settings.terrain_step
    axis = np.arange(0, size + step, step)
    xx, yy = np.meshgrid(axis + cx * size, axis + cy * size)
    zz = terrain.height(xx, yy)
    vertices = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel())).astype(np.float32)
    n = len(axis)
    idx = np.arange(n*n).reshape(n, n)[:-1, :-1].ravel()
    triangles = np.stack((np.column_stack((idx, idx+1, idx+n)),
                          np.column_stack((idx+1, idx+n+1, idx+n))), axis=1).reshape(-1, 3)
    moisture = terrain.noise(xx, yy, 120, 82).ravel()
    tint = rng.uniform(-.025, .025, (len(vertices), 1))
    colors = np.column_stack((.28 + moisture * .09, .43 + moisture * .12,
                             .16 + moisture * .035)) + tint
    for lake in terrain.lakes:
        reach = lake.extent*1.55
        if lake.x+reach < xx.min() or lake.x-reach > xx.max() or lake.y+reach < yy.min() or lake.y-reach > yy.max():
            continue
        distance = lake.distance(xx,yy).ravel()
        variation = terrain.noise(xx,yy,9,163).ravel()
        bank = np.exp(-((distance-1.015)/(.09+variation*.09))**2)
        bank *= .55 + variation*.25
        mud = np.column_stack((.34+variation*.06,.32+variation*.08,.20+variation*.035))
        colors = colors*(1-bank[:,None]) + mud*bank[:,None]

    def placements(count, water_allowed=False, grass=False):
        points = np.column_stack((rng.uniform(cx*size, (cx+1)*size, count),
                                  rng.uniform(cy*size, (cy+1)*size, count),
                                  np.zeros(count), rng.uniform(.8, 1.5, count)))
        points[:, 2] = terrain.height(points[:, 0], points[:, 1]) if len(points) else []
        if not water_allowed and count:
            mask = np.ones(count, dtype=bool)
            for lake in terrain.lakes:
                reach = lake.extent*1.15
                nearby = (np.abs(points[:,0]-lake.x) < reach) & (np.abs(points[:,1]-lake.y) < reach)
                indices = np.flatnonzero(nearby)
                if not len(indices):
                    continue
                # Na margem, usa os triangulos renderizados para evitar vegetacao submersa.
                points[indices,2] = terrain.surface(points[indices,0],points[indices,1])
                d = lake.distance(points[indices,0],points[indices,1])
                shore_meters = (d-1)*lake.radius
                dry = (d >= 1.10) | (points[indices,2] > lake.level+.055)
                if grass:
                    patch = terrain.noise(points[indices,0],points[indices,1],4,197)
                    density = .35 + .65*np.clip((shore_meters+.2)/2.8,0,1)
                    dry &= patch < density
                    points[indices,3] *= .45 + .55*np.clip(shore_meters/3,0,1)
                else:
                    dry &= shore_meters > .7
                mask[indices] &= dry
            points = points[mask]
        return points.astype(np.float32)

    return ChunkData(key, vertices, triangles.astype(np.int32), colors.astype(np.float32),
                     placements(settings.trees_per_chunk), placements(settings.grass_per_chunk,grass=True),
                     placements(settings.rocks_per_chunk), placements(settings.ducks_per_chunk, True))
