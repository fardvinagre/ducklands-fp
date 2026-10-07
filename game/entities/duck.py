import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto


class DuckState(Enum):
    IDLE = auto()
    WALKING = auto()
    SWIMMING = auto()
    FLEEING = auto()
    TAKING_OFF = auto()
    FLYING = auto()
    LANDING = auto()


AIR_STATES = {DuckState.TAKING_OFF, DuckState.FLYING, DuckState.LANDING}


@dataclass
class Duck:
    x: float
    y: float
    z: float
    seed: int
    state: DuckState = DuckState.IDLE
    heading: float = 0
    timer: float = 0
    accumulator: float = 0
    elapsed: float = 0
    target: tuple[float, float] = (0, 0)
    rng: random.Random = field(init=False, repr=False)
    fear_radius: float = field(init=False)
    alert: bool = False

    def __post_init__(self):
        self.rng = random.Random(self.seed)
        self.fear_radius = self.rng.uniform(5, 10)
        self.timer = self.rng.uniform(1, 4)
        self.heading = self.rng.uniform(0, math.tau)
        self.target = (self.x, self.y)

    def choose_activity(self, terrain):
        if self.rng.random() < .3:
            self.state = DuckState.IDLE
            self.timer = self.rng.uniform(1, 3)
        else:
            self.state = DuckState.SWIMMING if terrain.water(self.x, self.y) is not None else DuckState.WALKING
            angle, distance = self.rng.uniform(0, math.tau), self.rng.uniform(3, 10)
            self.target = (self.x + math.cos(angle)*distance, self.y + math.sin(angle)*distance)
            self.timer = self.rng.uniform(4, 8)

    def update(self, dt, player, terrain, neighbors=(), obstacles=()):
        self.elapsed += dt
        self.timer -= dt
        dx, dy = self.x-player[0], self.y-player[1]
        distance = math.hypot(dx, dy)
        self.alert = distance < 15
        if distance < self.fear_radius and self.state not in AIR_STATES and self.state != DuckState.FLEEING:
            roll = self.rng.random()
            if roll < .65:
                self.state = DuckState.TAKING_OFF
                lake = terrain.nearest_lake(self.x + dx*8, self.y + dy*8)
                self.target = (lake.x + self.rng.uniform(-.4,.4)*lake.radius,
                               lake.y + self.rng.uniform(-.4,.4)*lake.radius)
                self.timer = 1.5
            elif roll < .9:
                self.state = DuckState.FLEEING
                self.target = (self.x+dx/max(distance,.1)*20, self.y+dy/max(distance,.1)*20)
                self.timer = 4
            else:
                # Pequeno periodo de tolerancia evita sortear novamente todo frame.
                self.fear_radius = max(2, self.fear_radius*.8)

        airborne = self.state in AIR_STATES
        if self.state == DuckState.TAKING_OFF and self.timer <= 0:
            self.state, self.timer = DuckState.FLYING, 12
        elif self.state == DuckState.FLYING and ((self.timer < 10 and math.hypot(self.target[0]-self.x, self.target[1]-self.y) < 6) or self.timer <= 0):
            self.state, self.timer = DuckState.LANDING, 5
        if self.state not in AIR_STATES and self.timer <= 0:
            self.choose_activity(terrain)

        if self.state != DuckState.IDLE:
            tx, ty = self.target[0]-self.x, self.target[1]-self.y
            length = math.hypot(tx, ty)
            vx, vy = tx/max(length,.001), ty/max(length,.001)
            if not airborne:
                # Separacao, alinhamento e coesao locais via spatial hash.
                close = [n for n in neighbors if n is not self and math.hypot(n.x-self.x,n.y-self.y) < 5]
                for other in close:
                    ox, oy = self.x-other.x, self.y-other.y
                    d2 = ox*ox+oy*oy
                    if 0.001 < d2 < 2:
                        vx += ox/d2*.7
                        vy += oy/d2*.7
                    vx += math.cos(other.heading)*.025 + (other.x-self.x)*.006
                    vy += math.sin(other.heading)*.025 + (other.y-self.y)*.006
                for ox,oy,r in obstacles:
                    ax,ay = self.x-ox,self.y-oy
                    dist = math.hypot(ax,ay)
                    if dist < r+1.5:
                        vx += ax/max(dist,.01)*2
                        vy += ay/max(dist,.01)*2
            norm = math.hypot(vx,vy)
            vx,vy = vx/max(norm,.001),vy/max(norm,.001)
            self.heading = math.atan2(vy,vx)
            speed = 8 if airborne else (3.7 if self.state == DuckState.FLEEING else .8)
            move = min(speed*dt, length)
            self.x += vx*move
            self.y += vy*move

        bound = terrain.settings.world_half_size - 1
        self.x, self.y = max(-bound,min(bound,self.x)), max(-bound,min(bound,self.y))
        water = terrain.water(self.x,self.y)
        ground = max(float(terrain.height(self.x,self.y)), water if water is not None else -math.inf)
        if self.state == DuckState.TAKING_OFF:
            self.z = max(self.z + dt*4, ground+.15)
        elif self.state == DuckState.FLYING:
            self.z += (ground+8-self.z)*min(1,dt*1.5)
        elif self.state == DuckState.LANDING:
            self.z = max(ground, self.z-dt*3.5)
            if self.z <= ground+.08:
                self.state, self.timer = (DuckState.SWIMMING if water is not None else DuckState.IDLE), 3
        else:
            self.z = ground
            if self.state in (DuckState.WALKING,DuckState.SWIMMING):
                self.state = DuckState.SWIMMING if water is not None else DuckState.WALKING
