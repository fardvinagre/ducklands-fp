"""Ondas de superficie. Referencia: Wang et al. (2024), DOI 10.1007/s41095-023-0368-y."""
import math
import time
from dataclasses import dataclass

import numpy as np
from panda3d.core import Shader, Texture, TransparencyAttrib

from game.engine.geometry import buffer_node
from game.engine.renderer import SHADOW_MASK


def lake_depth(terrain, lake, size):
    """Profundidade sobre os triangulos renderizados do terreno."""
    axis = np.linspace(-lake.extent, lake.extent, size)
    x, y = np.meshgrid(axis + lake.x, axis + lake.y)
    bed = terrain.surface(x,y)
    inside = lake.distance(x,y) < 1.10
    return np.where(inside, np.maximum(lake.level - bed, 0), 0).astype(np.float32)


class SurfaceWaves:
    """h_tt = div(g * depth * grad(h)) - damping * h_t.

    Fluxos simetricos bloqueiam celulas secas. O passo respeita o limite CFL;
    frames longos descartam atraso para limitar o custo de atualizacao.
    """
    step = 1 / 60
    max_steps = 4

    def __init__(self, depth, radius):
        self.depth = np.asarray(depth, dtype=np.float32).copy()
        self.size = len(depth)
        self.radius = radius
        self.spacing = 2 * radius / (self.size - 1)
        self.wet = self.depth > .025
        self.height = np.zeros_like(self.depth)
        self.velocity = np.zeros_like(self.depth)
        c2 = 9.81 * np.clip(self.depth, .08, 1.5)
        self.horizontal = .5 * (c2[:, 1:] + c2[:, :-1]) * (self.wet[:, 1:] & self.wet[:, :-1])
        self.vertical = .5 * (c2[1:] + c2[:-1]) * (self.wet[1:] & self.wet[:-1])
        self.fixed_dt = min(self.step, .45 * self.spacing / math.sqrt(2 * float(c2.max())))
        self.accumulator = 0.0
        self.steps = 0

    def impulse(self, x, y, strength=.22, width=.65):
        """Impulso de velocidade com media zero para conservar o volume."""
        ix = (x / self.radius + 1) * .5 * (self.size - 1)
        iy = (y / self.radius + 1) * .5 * (self.size - 1)
        extent = max(2, math.ceil(3 * width / self.spacing))
        x0, x1 = max(0, math.floor(ix)-extent), min(self.size, math.ceil(ix)+extent+1)
        y0, y1 = max(0, math.floor(iy)-extent), min(self.size, math.ceil(iy)+extent+1)
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        mask = self.wet[y0:y1, x0:x1]
        if not mask.any():
            return
        gaussian = np.exp(-((xx-ix)**2 + (yy-iy)**2) * self.spacing**2 / (2*width**2)) * mask
        gaussian -= (gaussian.sum() / mask.sum()) * mask
        self.velocity[y0:y1, x0:x1] += np.asarray(gaussian * strength, dtype=np.float32)

    def advance(self, dt):
        self.accumulator = min(self.accumulator + max(0, dt), self.fixed_dt * self.max_steps)
        steps = 0
        while self.accumulator + 1e-9 >= self.fixed_dt and steps < self.max_steps:
            h = self.height
            flux_x = (h[:, 1:] - h[:, :-1]) * self.horizontal / self.spacing**2
            flux_y = (h[1:] - h[:-1]) * self.vertical / self.spacing**2
            acceleration = np.zeros_like(h)
            acceleration[:, :-1] += flux_x
            acceleration[:, 1:] -= flux_x
            acceleration[:-1] += flux_y
            acceleration[1:] -= flux_y
            self.velocity += acceleration * self.fixed_dt
            self.velocity *= math.exp(-1.35 * self.fixed_dt)
            self.height += self.velocity * self.fixed_dt
            clipped = np.abs(self.height) > .12
            np.clip(self.height, -.12, .12, out=self.height)
            self.velocity[clipped | ~self.wet] = 0
            self.height[~self.wet] = 0
            self.accumulator -= self.fixed_dt
            steps += 1
        self.steps = steps
        return steps

    def sample(self, x, y):
        u = np.clip((x/self.radius+1)*.5*(self.size-1), 0, self.size-1)
        v = np.clip((y/self.radius+1)*.5*(self.size-1), 0, self.size-1)
        i, j = min(int(u), self.size-2), min(int(v), self.size-2)
        fx, fy = u-i, v-j
        return float((self.height[j,i]*(1-fx)+self.height[j,i+1]*fx)*(1-fy)
                     + (self.height[j+1,i]*(1-fx)+self.height[j+1,i+1]*fx)*fy)

    def pixels(self):
        dy, dx = np.gradient(self.height, self.spacing)
        return np.stack((self.height, dx, dy, self.depth), axis=-1).astype(np.float32)


def water_texture(name, pixels):
    texture = Texture(name)
    texture.setup2dTexture(len(pixels), len(pixels), Texture.TFloat, Texture.FRgba32)
    texture.setMinfilter(Texture.FTLinear)
    texture.setMagfilter(Texture.FTLinear)
    texture.setWrapU(Texture.WMClamp)
    texture.setWrapV(Texture.WMClamp)
    texture.setRamImageAs(pixels.tobytes(), 'RGBA')
    return texture


def surface_mesh(lake, size=65):
    axis = np.linspace(0, 1, size, dtype=np.float32)
    u, v = np.meshgrid(axis, axis)
    vertices = np.ones((size*size, 10), dtype=np.float32)
    vertices[:, 0] = (lake.x + (u*2-1)*lake.extent).ravel()
    vertices[:, 1] = (lake.y + (v*2-1)*lake.extent).ravel()
    vertices[:, 2] = lake.level + .025
    vertices[:, 3:6] = (0, 0, 1)
    vertices[:, 6], vertices[:, 7] = u.ravel(), v.ravel()
    j, i = np.mgrid[:size-1, :size-1]
    a = (j*size+i).ravel()
    indices = np.stack((a, a+1, a+size, a+1, a+size+1, a+size), axis=1).astype(np.uint32).ravel()
    lower, upper = vertices[:,:3].min(axis=0), vertices[:,:3].max(axis=0)
    lower[2] -= .12
    upper[2] += .12
    return buffer_node('water-surface', vertices, bounds=(lower,upper), indices=indices)


@dataclass
class LakeSurface:
    lake: object
    node: object
    texture: object
    waves: SurfaceWaves
    active: bool = False
    upload_time: float = 0.0


class WaterSystem:
    """Carrega lagos por distancia e limita a simulacao aos mais proximos."""
    max_active = 4
    visible_distance = 200
    active_distance = 110

    def __init__(self, root, terrain, shader_dir):
        self.root = root.attachNewNode('water')
        self.root.hide(SHADOW_MASK)
        self.terrain = terrain
        self.shader = Shader.make(Shader.SL_GLSL, (shader_dir/'water.vert').read_text(),
                                  (shader_dir/'water.frag').read_text())
        self.surfaces = {}
        self.emitters = {}
        self.time = 0.0
        self.cpu_ms = 0.0

    def create(self, lake):
        waves = SurfaceWaves(lake_depth(self.terrain, lake, 65), lake.extent)
        texture = water_texture('wave-field', waves.pixels())
        node = surface_mesh(lake)
        node.reparentTo(self.root)
        node.setShader(self.shader)
        node.setShaderInput('waveField', texture)
        node.setShaderInput('fieldSize', float(waves.size))
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setDepthWrite(False)
        node.setTwoSided(True)
        return LakeSurface(lake, node, texture, waves)

    def update(self, dt, player, ducks, paused=False):
        started = time.perf_counter()
        x, y = player.x, player.y
        nearby = sorted(((max(0, math.hypot(l.x-x,l.y-y)-l.extent), l)
                         for l in self.terrain.lakes), key=lambda item: item[0])
        wanted = {l for distance,l in nearby if distance < self.visible_distance}
        for lake in set(self.surfaces)-wanted:
            self.surfaces.pop(lake).node.removeNode()
        missing = [l for _,l in nearby if l in wanted and l not in self.surfaces]
        if missing:
            lake = missing[0]
            self.surfaces[lake] = self.create(lake)
        active = set([l for distance,l in nearby if distance < self.active_distance][:self.max_active])
        for lake, surface in self.surfaces.items():
            if surface.active != (lake in active):
                surface.waves.height.fill(0)
                surface.waves.velocity.fill(0)
                surface.active = lake in active
                surface.texture.setRamImageAs(surface.waves.pixels().tobytes(), 'RGBA')
        if not paused:
            self.time += dt
            emitters = [('player', player, 1.0, .9)]
            emitters += [(id(d), d, .45, .65) for d in ducks if getattr(d.state, 'name', '') == 'SWIMMING']
            current = {}
            for key, entity, strength, width in emitters:
                current[key] = (entity.x, entity.y)
                old = self.emitters.get(key)
                if old is None or math.hypot(entity.x-old[0],entity.y-old[1]) < .3:
                    if old is not None:
                        current[key] = old
                    continue
                distance = math.hypot(entity.x-old[0],entity.y-old[1])
                if distance > 3:
                    continue
                for lake in active:
                    surface = self.surfaces.get(lake)
                    if surface is None:
                        continue
                    if abs(entity.x-lake.x) < lake.extent and abs(entity.y-lake.y) < lake.extent:
                        if lake.distance(entity.x,entity.y) >= 1.10:
                            continue
                        if key == 'player' and entity.z > lake.level + .15:
                            continue
                        surface.waves.impulse(entity.x-lake.x,entity.y-lake.y, strength, width)
                        surface.waves.impulse(old[0]-lake.x,old[1]-lake.y, -strength*.7, width)
                        break
            self.emitters = current
            for surface in self.surfaces.values():
                if surface.active:
                    surface.waves.advance(dt)
                    surface.upload_time += dt
                    if surface.upload_time >= 1/30:
                        surface.upload_time %= 1/30
                        surface.texture.setRamImageAs(surface.waves.pixels().tobytes(), 'RGBA')
        self.root.setShaderInput('waterTime', self.time)
        eye_height = 1.05 if getattr(player,'keys',{}).get('control') else 1.75
        self.root.setShaderInput('waterEye', (float(x),float(y),float(player.z+eye_height)))
        self.cpu_ms = (time.perf_counter()-started)*1000

    def offset(self, x, y):
        for surface in self.surfaces.values():
            lake = surface.lake
            if surface.active and abs(x-lake.x) < lake.extent and abs(y-lake.y) < lake.extent:
                return surface.waves.sample(x-lake.x,y-lake.y)
        return 0.0

    def close(self):
        self.emitters.clear()
        self.surfaces.clear()
        self.root.removeNode()
