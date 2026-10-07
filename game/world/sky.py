"""Ceu: camadas de nuvens em cache de baixa resolucao e bandos de patos em V."""
import math
import random
from dataclasses import dataclass, field

import numpy as np
from panda3d.core import Shader, Texture, TransparencyAttrib, Vec3

from game.engine.geometry import Mesh, duck_model
from game.engine.renderer import SHADOW_MASK
from game.entities.duck import DuckState
from game.entities.duck_anim import DuckRig

CLOUD_TEXTURE_SIZE = 256
# (altitude, tamanho do tile em metros, vento em tiles/s). Duas camadas dao paralaxe.
CLOUD_LAYERS = ((170.0, 1500.0, (.0022, .0009)), (320.0, 2600.0, (.0014, .0006)))


def periodic_noise(size, rng, exponent, cutoff=None):
    """Ruido fBm que repete sem emenda: ruido branco filtrado no dominio da frequencia."""
    freq = np.fft.fftfreq(size)
    radius = np.hypot(*np.meshgrid(freq, freq))
    radius[0, 0] = 1
    amplitude = radius**-exponent
    amplitude[0, 0] = 0
    if cutoff:
        amplitude *= np.exp(-(radius/cutoff)**2)
    noise = np.fft.ifft2(np.fft.fft2(rng.standard_normal((size, size)))*amplitude).real
    return (noise-noise.mean())/noise.std()


def cloud_texture(seed):
    """RGBA8: R/G = forma das camadas 1/2, B/A = detalhe fino que corroi as bordas."""
    rng = np.random.default_rng(seed)
    size = CLOUD_TEXTURE_SIZE
    fields = [periodic_noise(size, rng, 1.35, .22), periodic_noise(size, rng, 1.35, .22),
              periodic_noise(size, rng, 1.1), periodic_noise(size, rng, 1.1)]
    pixels = np.stack([np.clip(f*.2+.5, 0, 1) for f in fields], axis=-1)
    rgba = (pixels*255).astype(np.uint8)
    texture = Texture('clouds')
    texture.setup2dTexture(size, size, Texture.TUnsignedByte, Texture.FRgba8)
    texture.setRamImage(np.ascontiguousarray(rgba[..., [2, 1, 0, 3]]).tobytes())   # Panda guarda BGRA
    texture.setWrapU(Texture.WMRepeat)
    texture.setWrapV(Texture.WMRepeat)
    texture.setMinfilter(Texture.FTLinear)
    texture.setMagfilter(Texture.FTLinear)
    return texture


def dome_mesh(radius=300.0, rings=14, segments=40):
    mesh = Mesh()
    elevations = [math.radians(-6+96*i/rings) for i in range(rings+1)]

    def point(i, j):
        a, e = math.tau*j/segments, elevations[i]
        return (radius*math.cos(e)*math.cos(a), radius*math.cos(e)*math.sin(a), radius*math.sin(e))
    for i in range(rings):
        for j in range(segments):
            a, b, c, d = point(i, j), point(i, j+1), point(i+1, j), point(i+1, j+1)
            mesh.triangle(a, b, c, (1, 1, 1))
            mesh.triangle(b, d, c, (1, 1, 1))
    return mesh.node('sky-dome')


class Sky:
    """Nuvens em duas camadas, amostradas de uma textura de densidade periodica."""

    def __init__(self, app, environment, shader_dir, seed):
        self.app = app
        self.node = dome_mesh()
        self.node.reparentTo(app.render)
        self.node.setShader(Shader.make(Shader.SL_GLSL, (shader_dir/'clouds.vert').read_text(),
                                        (shader_dir/'clouds.frag').read_text()))
        self.node.setTransparency(TransparencyAttrib.MAlpha)
        self.node.setBin('background', 0)
        self.node.setDepthWrite(False)
        self.node.setDepthTest(False)
        self.node.setTwoSided(True)
        self.node.setLightOff()
        self.node.hide(SHADOW_MASK)
        self.node.setShaderInput('clouds', cloud_texture(seed))
        toward_sun = -app.render.getRelativeVector(environment.sun_node, Vec3(0, 1, 0))
        toward_sun.normalize()
        self.node.setShaderInput('sunDir', toward_sun)
        self.node.setShaderInput('haze', Vec3(.57, .74, .82))
        layers = [(h, 1/tile, wx, wy) for h, tile, (wx, wy) in CLOUD_LAYERS]
        self.node.setShaderInput('layer0', Vec3(layers[0][0], layers[0][1], 0))
        self.node.setShaderInput('layer1', Vec3(layers[1][0], layers[1][1], 0))
        self.node.setShaderInput('wind0', (layers[0][2], layers[0][3]))
        self.node.setShaderInput('wind1', (layers[1][2], layers[1][3]))
        self.update(0, (0, 0, 0))

    def update(self, elapsed, camera_pos):
        self.node.setPos(*camera_pos)
        self.node.setShaderInput('camPos', Vec3(*camera_pos))
        self.node.setShaderInput('cloudTime', elapsed)
        self.node.setShaderInput('coverage', .5+.07*math.sin(elapsed*.011)+.04*math.sin(elapsed*.027+1.3))


@dataclass
class SkyDuck:
    """Estado minimo que o DuckRig precisa; o movimento vem do bando, nao da IA de solo."""
    x: float
    y: float
    z: float
    heading: float
    rank: int
    side: int
    drift_back: float = 0.0
    drift_side: float = 0.0
    drift_up: float = 0.0
    state: DuckState = DuckState.FLYING
    rig: DuckRig = field(default=None, repr=False)


class Flock:
    """Formacao em V com posicoes suavizadas e deriva Ornstein-Uhlenbeck."""
    SPACING_BACK, SPACING_SIDE = 3.8, 2.4
    SCALE = 1.6

    def __init__(self, root, template, rng, start, heading, altitude, count):
        self.rng = rng
        self.heading = heading
        self.speed = rng.uniform(10, 13)
        self.turn_rate = 0.0
        self.base_altitude = altitude
        self.age = 0.0
        self.swap_timer = rng.uniform(3, 8)
        self.node = root.attachNewNode('flock')
        self.lead = [start[0], start[1], altitude]
        self.ducks = []
        for i in range(count):
            rank, side = (0, 0) if i == 0 else ((i+1)//2, 1 if i % 2 else -1)
            duck = SkyDuck(start[0], start[1], altitude, heading, rank, side)
            node = template.copyTo(self.node)
            node.setScale(self.SCALE)
            duck.x, duck.y, duck.z = self.slot(duck)
            duck.rig = DuckRig(node, duck.x, duck.y, duck.z, math.degrees(heading)-90)
            duck.rig.flap = rng.uniform(0, math.tau)   # batidas fora de fase
            duck.rig.t = rng.uniform(0, 50)
            self.ducks.append(duck)

    def slot(self, duck):
        fx, fy = math.cos(self.heading), math.sin(self.heading)
        back = duck.rank*self.SPACING_BACK+duck.drift_back
        side = duck.side*duck.rank*self.SPACING_SIDE+duck.drift_side
        return (self.lead[0]-fx*back+fy*side, self.lead[1]-fy*back-fx*side,
                self.lead[2]+duck.drift_up-duck.rank*.15)

    def update(self, dt):
        rng = self.rng
        self.age += dt
        self.turn_rate += (-self.turn_rate*.25*dt)+rng.gauss(0, .012)*math.sqrt(dt)
        self.heading += self.turn_rate*dt
        self.lead[0] += math.cos(self.heading)*self.speed*dt
        self.lead[1] += math.sin(self.heading)*self.speed*dt
        self.lead[2] = self.base_altitude+math.sin(self.age*.13)*4
        # A deriva OU limita o afastamento dos patos da formacao.
        decay = math.exp(-dt/3.5)
        noise = math.sqrt(1-decay*decay)
        for duck in self.ducks[1:]:
            duck.drift_back = duck.drift_back*decay+rng.gauss(0, 1.9)*noise
            duck.drift_side = duck.drift_side*decay+rng.gauss(0, .5)*noise
            duck.drift_up = duck.drift_up*decay+rng.gauss(0, .5)*noise
        self.swap_timer -= dt
        if self.swap_timer <= 0:
            self.swap_timer = rng.uniform(4, 12)
            self.swap_neighbours()
        follow = 1-math.exp(-1.6*dt)
        for duck in self.ducks:
            sx, sy, sz = self.slot(duck)
            ox, oy = duck.x, duck.y
            duck.x += (sx-duck.x)*follow
            duck.y += (sy-duck.y)*follow
            duck.z += (sz-duck.z)*follow
            if math.hypot(duck.x-ox, duck.y-oy) > 1e-4:
                duck.heading = math.atan2(duck.y-oy, duck.x-ox)
            duck.rig.animate(duck, dt)

    def swap_neighbours(self):
        """Dois patos vizinhos no mesmo braco trocam de posicao: um avanca, o outro recua."""
        arm = [d for d in self.ducks if d.side == self.rng.choice((-1, 1))]
        arm.sort(key=lambda d: d.rank)
        if len(arm) < 2:
            return
        i = self.rng.randrange(len(arm)-1)
        a, b = arm[i], arm[i+1]
        a.rank, b.rank = b.rank, a.rank

    def close(self):
        self.node.removeNode()


class FlockManager:
    """Sorteia bandos que cruzam o ceu de vez em quando, entrando e saindo na neblina."""
    SPAWN_RADIUS, DESPAWN_RADIUS = 240.0, 330.0

    def __init__(self, app, seed, first_spawn=6.0):
        self.root = app.render.attachNewNode('sky-flocks')
        self.root.hide(SHADOW_MASK)
        self.template = duck_model()
        self.rng = random.Random(seed+4242)
        self.flocks = []
        self.timer = first_spawn

    def spawn(self, player):
        rng = self.rng
        angle = rng.uniform(0, math.tau)
        start = (player[0]+math.cos(angle)*self.SPAWN_RADIUS, player[1]+math.sin(angle)*self.SPAWN_RADIUS)
        aim = (player[0]+rng.uniform(-80, 80), player[1]+rng.uniform(-80, 80))
        heading = math.atan2(aim[1]-start[1], aim[0]-start[0])
        altitude = player[2]+rng.uniform(55, 95)
        self.flocks.append(Flock(self.root, self.template, rng, start, heading, altitude, rng.randint(5, 13)))

    def update(self, dt, player):
        """player = (x, y, z)."""
        self.timer -= dt
        if self.timer <= 0:
            self.timer = self.rng.uniform(35, 90)
            if len(self.flocks) < 2:
                self.spawn(player)
        for flock in list(self.flocks):
            flock.update(dt)
            far = math.hypot(flock.lead[0]-player[0], flock.lead[1]-player[1]) > self.DESPAWN_RADIUS
            if (far and flock.age > 10) or flock.age > 180:
                flock.close()
                self.flocks.remove(flock)
