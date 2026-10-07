import math
import random

from game.entities.duck import AIR_STATES, DuckState

# Angulos das poses em graus; 55 recolhe a asa junto ao corpo.
FOLDED = 55
_REST = dict(pitch=0, neck_out=0, neck_p=0, wing_base=FOLDED, wing_amp=0, feet_p=0, feet_amp=0,
             dz=0, feet_show=1, tail_p=0)
_POSES = {
    DuckState.IDLE: {},
    DuckState.WALKING: dict(feet_amp=38),
    DuckState.SWIMMING: dict(dz=-.08, feet_show=0, tail_p=8),
    DuckState.FLEEING: dict(pitch=10, neck_out=.08, neck_p=-8, wing_base=-30, wing_amp=14, feet_amp=45),
    DuckState.TAKING_OFF: dict(pitch=28, neck_out=.12, wing_base=-5, wing_amp=62, feet_p=-45, tail_p=-10),
    DuckState.FLYING: dict(neck_out=.14, wing_base=-4, wing_amp=48, feet_p=-80, tail_p=-6),
    DuckState.LANDING: dict(pitch=32, neck_out=.06, wing_base=-22, wing_amp=22, feet_p=40, tail_p=-25),
}
_FLAP_RATE = {DuckState.TAKING_OFF: 38, DuckState.FLYING: 30, DuckState.LANDING: 15, DuckState.FLEEING: 32}


def _ease(rate, dt):
    return 1 - math.exp(-rate*dt)


class DuckRig:
    """Anima um pato a cada frame a partir do estado simulado (que pode rodar em taxa menor)."""

    def __init__(self, node, x, y, z, heading_deg):
        self.node = node
        find = node.find
        self.body, self.neck, self.tail = find('**/body_pivot'), find('**/neck'), find('**/tail')
        self.wings = list(node.findAllMatches('**/wing'))    # [esquerda, direita]
        self.feet = list(node.findAllMatches('**/foot'))
        self.pos = [x, y, z]
        self.heading = heading_deg
        self.bank = 0.0
        self.pitch_air = 0.0
        self.pose = dict(_REST)
        rng = random.Random(int(x*131 + y*17))
        self.phase_offset = rng.uniform(0, math.tau)
        self.look_rate = rng.uniform(.35, .7)
        self.t = rng.uniform(0, 100)
        self.step = 0.0
        self.flap = 0.0

    def animate(self, duck, dt):
        if dt <= 0:
            return
        self.t += dt
        t = self.t + self.phase_offset
        state = duck.state
        air = state in AIR_STATES

        # Interpola a posicao entre passos da IA, que pode rodar a 10 Hz.
        k = _ease(18 if not air else 10, dt)
        old = self.pos[:]
        self.pos[0] += (duck.x-self.pos[0])*k
        self.pos[1] += (duck.y-self.pos[1])*k
        self.pos[2] += (duck.z-self.pos[2])*k
        speed = math.hypot(self.pos[0]-old[0], self.pos[1]-old[1])/dt
        vz = (self.pos[2]-old[2])/dt

        target_h = math.degrees(duck.heading)-90
        diff = (target_h-self.heading+180) % 360-180
        turn = diff*_ease(5 if air else 9, dt)
        self.heading += turn
        bank_target = max(-35, min(35, -turn/dt*.35)) if air else 0
        self.bank += (bank_target-self.bank)*_ease(4, dt)

        target = {**_REST, **_POSES.get(state, {})}
        blend = _ease(7, dt)
        pose = self.pose
        for key, value in target.items():
            pose[key] += (value-pose[key])*blend

        self.step += speed*dt*(11 if state != DuckState.SWIMMING else 5)
        self.flap += _FLAP_RATE.get(state, 30)*dt
        walk = math.sin(self.step)
        moving = min(1, speed/.5)

        roll = self.bank
        bob = 0.0
        head_h = 0.0
        head_p = pose['neck_p']
        pitch = pose['pitch']
        if state in (DuckState.WALKING, DuckState.FLEEING):
            roll += walk*(6 if state == DuckState.WALKING else 4)*moving
            bob += abs(walk)*.025*moving
            head_p += math.sin(self.step*2)*5*moving
        elif state == DuckState.SWIMMING:
            bob += math.sin(t*2.2)*.012
            roll += math.sin(t*1.3)*2.5
            head_p += math.sin(self.step)*6*moving
        elif state == DuckState.IDLE:
            bob += math.sin(t*1.6)*.004
            head_h = math.sin(t*self.look_rate)*38
            head_p += math.sin(t*.9)*6
            if math.sin(t*.21) > .93:                      # de vez em quando bica o chao
                head_p -= 38
        elif air:
            pitch += max(-18, min(22, vz*4))*(1 if state == DuckState.FLYING else 0)
            bob += math.cos(self.flap)*.03

        self.node.setPos(self.pos[0], self.pos[1], self.pos[2])
        self.node.setH(self.heading)
        self.body.setPos(0, 0, .30+pose['dz']+bob)
        self.body.setHpr(math.sin(self.step)*3*moving if state == DuckState.WALKING else 0, pitch, roll)
        self.neck.setPos(0, .30+pose['neck_out'], .15+pose['neck_out']*.3)
        self.neck.setHpr(head_h, head_p, 0)
        self.tail.setP(pose['tail_p']+math.sin(t*3.1)*3)

        amp, base = pose['wing_amp'], pose['wing_base']
        flap = math.sin(self.flap)
        stroke = flap if flap > 0 else flap*.7
        for i, wing in enumerate(self.wings):
            # As asas espelhadas exigem sinais opostos para o roll.
            wing.setR((base+amp*stroke)*(-1 if i else 1))

        show = pose['feet_show'] > .5
        for i, foot in enumerate(self.feet):
            if show:
                foot.show()
            else:
                foot.hide()
            sign = 1 if i else -1
            foot.setP(pose['feet_p']+sign*walk*pose['feet_amp']*moving)
