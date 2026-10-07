import math
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np

from game.config import Settings


@dataclass(frozen=True)
class Lake:
    x: float
    y: float
    radius: float
    level: float
    phase: float = 0.0

    @property
    def extent(self):
        """Meia largura maxima do lago, incluindo variacoes do contorno."""
        return self.radius * 1.16

    def distance(self, x, y):
        """Distancia normalizada: a margem corresponde ao valor 1."""
        if np.isscalar(x) and np.isscalar(y):
            dx, dy = x-self.x, y-self.y
            angle = math.atan2(dy,dx)
            profile = (.84 + .17*math.sin(2*angle+self.phase)
                       + .095*math.sin(3*angle-self.phase*.7)
                       + .045*math.sin(5*angle+self.phase*1.3))
            return math.hypot(dx,dy)/(self.radius*profile)
        dx, dy = np.asarray(x)-self.x, np.asarray(y)-self.y
        angle = np.arctan2(dy,dx)
        profile = (.84 + .17*np.sin(2*angle+self.phase)
                   + .095*np.sin(3*angle-self.phase*.7)
                   + .045*np.sin(5*angle+self.phase*1.3))
        return np.hypot(dx,dy) / (self.radius*profile)


class Terrain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._surface_tiles = OrderedDict()
        rng = np.random.default_rng(settings.seed)
        self.lakes = [Lake(26, 40, 21, float(self.base_height(26,40))-1.2, settings.seed*.017)]
        bound = settings.world_half_size
        for x in range(-bound + 128, bound, 256):
            for y in range(-bound + 128, bound, 256):
                lx, ly = x + rng.uniform(-60, 60), y + rng.uniform(-60, 60)
                if math.hypot(lx - 26, ly - 40) > 100:
                    self.lakes.append(Lake(lx, ly, rng.uniform(13, 29),
                                           float(self.base_height(lx, ly)) - 1,
                                           settings.seed*.017+lx*.019+ly*.031))

    def noise(self, x, y, scale, salt):
        """Value noise vetorizado, estavel entre processos e chunks."""
        x, y = np.asarray(x, dtype=float) / scale, np.asarray(y, dtype=float) / scale
        ix, iy = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
        fx, fy = x - ix, y - iy
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

        def hash_value(a, b):
            n = (a * 374761393 + b * 668265263 + self.settings.seed * 1447 + salt) & 0xffffffff
            n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
            return (n ^ (n >> 16)) / 4294967295.0

        a = hash_value(ix, iy) * (1 - fx) + hash_value(ix + 1, iy) * fx
        b = hash_value(ix, iy + 1) * (1 - fx) + hash_value(ix + 1, iy + 1) * fx
        return a * (1 - fy) + b * fy

    def base_height(self, x, y):
        return (self.noise(x, y, 170, 11) - .5) * 13 + (self.noise(x, y, 55, 27) - .5) * 3

    def height(self, x, y):
        x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        h = self.base_height(x, y)
        # Apenas lagos que intersectam os dados consultados.
        xmin, xmax, ymin, ymax = x.min(), x.max(), y.min(), y.max()
        for lake in self.lakes:
            r = lake.extent * 1.55
            if lake.x + r < xmin or lake.x - r > xmax or lake.y + r < ymin or lake.y - r > ymax:
                continue
            d = lake.distance(x,y)
            # A encosta continua subindo depois da linha d'agua.
            floor = (lake.level - 1.65 + 1.65 * np.minimum(d, 1) ** 2
                     + 2.6*np.maximum(d-1,0))
            blend = np.clip((d - 1.12) / .43, 0, 1)
            blend = blend * blend * (3 - 2 * blend)
            h = np.where(d < 1.55, floor * (1 - blend) + h * blend, h)
        return h

    def surface(self, x, y):
        """Altura dos triangulos efetivamente renderizados, inclusive nas bordas."""
        s = self.settings.terrain_step
        if np.isscalar(x) and np.isscalar(y):
            # Consultas escalares reutilizam o terreno; workers usam o caminho vetorizado.
            size = self.settings.chunk_size
            key = (math.floor(x/size),math.floor(y/size))
            tile = self._surface_tiles.get(key)
            if tile is None:
                axis = np.arange(0,size+s,s)
                xx, yy = np.meshgrid(axis+key[0]*size,axis+key[1]*size)
                tile = self.height(xx,yy)
                self._surface_tiles[key] = tile
                if len(self._surface_tiles) > 64:
                    self._surface_tiles.popitem(last=False)
            else:
                self._surface_tiles.move_to_end(key)
            u, v = (x-key[0]*size)/s, (y-key[1]*size)/s
            i, j = math.floor(u), math.floor(v)
            fx, fy = u-i, v-j
            a, b, c, d = (float(tile[j,i]),float(tile[j,i+1]),
                          float(tile[j+1,i]),float(tile[j+1,i+1]))
            if fx+fy <= 1:
                return a+(b-a)*fx+(c-a)*fy
            return d+(c-d)*(1-fx)+(b-d)*(1-fy)
        x, y = np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
        ix, iy = np.floor(x / s) * s, np.floor(y / s) * s
        fx, fy = (x - ix) / s, (y - iy) / s
        a, b, c, d = self.height([ix, ix+s, ix, ix+s], [iy, iy, iy+s, iy+s])
        result = np.where(fx+fy <= 1, a+(b-a)*fx+(c-a)*fy,
                          d+(c-d)*(1-fx)+(b-d)*(1-fy))
        return float(result) if result.ndim == 0 else result

    def water(self, x, y):
        for lake in self.lakes:
            if abs(x-lake.x) < lake.extent and abs(y-lake.y) < lake.extent:
                if lake.distance(x,y) < 1.10 and self.surface(x,y) < lake.level-.015:
                    return lake.level
        return None

    def nearest_lake(self, x, y):
        return min(self.lakes, key=lambda l: (x-l.x)**2 + (y-l.y)**2)

    def biome(self, x, y):
        if self.water(x, y) is not None:
            return 'Lago'
        humidity = float(self.noise(x, y, 120, 82))
        if humidity > .58:
            return 'Floresta'
        return 'Campo' if humidity > .27 else 'Campo rochoso'
