"""Entrada: python -m game.main."""
import argparse
import json
import math
import time
from collections import deque
from pathlib import Path

from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, loadPrcFileData

from game.config import Settings
from game.engine.renderer import Environment
from game.entities.player import Player
from game.systems.benchmark import memory_mb, save_benchmark, scene_counts
from game.world.chunks import generate_chunk
from game.world.sky import FlockManager, Sky
from game.world.terrain import Terrain
from game.world.world import World


class Ducklands(ShowBase):
    def __init__(self,settings,args):
        loadPrcFileData('ducklands',f'window-title Ducklands FPS - Python Laboratory\n'
                        f'win-size {settings.width} {settings.height}\n'
                        'sync-video false\nshow-frame-rate-meter false\n'
                        'audio-library-name null\ntextures-power-2 none\nnotify-level warning\n')
        super().__init__(windowType='none' if args.headless else ('offscreen' if args.offscreen else None))
        self.settings,self.args = settings,args
        if args.headless:
            self.camera = self.render.attachNewNode('headless-camera')
        self.elapsed = 0.0
        self.frame = 0
        self.samples = deque(maxlen=36000)
        self.benchmark_samples = []
        self.benchmark_started = None
        self.last_clock = time.perf_counter()
        self.terrain = Terrain(settings)
        self.environment = Environment(self) if not args.headless else None
        if self.environment:
            for _ in range(('off','low','medium','high').index(args.shadows)):
                self.environment.cycle_shadows()
        self.world = World(self,settings,self.terrain,Path(__file__).parent/'shaders')
        self.sky = self.flocks = None
        if self.environment:
            self.sky = Sky(self,self.environment,Path(__file__).parent/'shaders',settings.seed)
            self.flocks = FlockManager(self,settings.seed,first_spawn=0 if args.smoke else 6)
        self.world.commit(generate_chunk((0,0),settings,self.terrain))
        self.world.add_ducks(12,(0,0))
        if args.smoke:
            # O smoke inclui os meshes e shaders da regiao inicial completa.
            for key in sorted(self.world.desired(0,0)-{(0,0)}):
                self.world.commit(generate_chunk(key,settings,self.terrain))
        self.player = Player(self,self.terrain)
        self.hud = None
        if not args.headless:
            from game.engine.hud import HUD
            self.hud = HUD(self)
        self.cached_scene = {}
        self.cached_ram = None
        self.hud_timer = 0
        self.accept('f5',self.stress,['trees'])
        self.accept('f6',self.stress,['grass'])
        self.accept('f7',self.stress,['ducks'])
        self.accept('f8',self.shadows)
        self.accept('f9',self.record)
        self.accept('f10',self.screenshot)
        self.taskMgr.add(self.update,'ducklands-update')

    def stress(self,kind):
        if kind == 'ducks':
            self.world.add_ducks(50,(self.player.x,self.player.y))
            message = '+50 patos no lago mais proximo'
        else:
            # Distribui incremento nominal pelos chunks do raio atual.
            chunks = max(1,len(self.world.desired(self.player.x,self.player.y)))
            if kind == 'trees':
                self.settings.trees_per_chunk += math.ceil(1000/chunks)
                message = '+1000 candidatos a arvores; regenerando chunks'
            else:
                self.settings.grass_per_chunk += math.ceil(10000/chunks)
                message = '+10000 candidatos a grama; regenerando chunks'
            self.world.refresh()
        if self.hud:
            self.hud.message(message)

    def shadows(self):
        if self.environment:
            self.environment.cycle_shadows()
            if self.hud:
                self.hud.message('Sombras: '+self.environment.shadow_quality)

    def record(self):
        if not self.samples:
            return
        counts = {**self.world.counts(),**scene_counts(self.world.root)}
        mode = 'headless-cpu' if self.args.headless else ('offscreen' if self.args.offscreen else 'window')
        mode += '/'+(self.args.benchmark_route if self.args.benchmark else 'manual')
        result = save_benchmark(list(self.samples),self.settings,counts,
                                self.environment.shadow_quality if self.environment else 'OFF',
                                mode)
        print(json.dumps(result,indent=2))
        if self.hud:
            self.hud.message('Benchmark salvo em benchmarks/history-v0.5.csv')

    def screenshot(self):
        if self.args.headless:
            return
        folder = Path('screenshots')
        folder.mkdir(exist_ok=True)
        self.win.saveScreenshot(Filename.fromOsSpecific(str(folder/f'ducklands-{time.time_ns()}.png')))
        if self.hud:
            self.hud.message('Captura salva em screenshots/')

    def update(self,task):
        now = time.perf_counter()
        frame_time = now-self.last_clock
        self.last_clock = now
        dt = 1/60 if self.args.smoke else min(.05,frame_time)
        self.elapsed += dt
        self.frame += 1
        if self.args.benchmark and self.benchmark_started is not None:
            self.benchmark_samples.append(frame_time)
        if self.frame > 10:
            self.samples.append(frame_time)
        self.player.update(dt,self.world,mouse=not (self.args.headless or self.args.offscreen or self.args.benchmark))
        if self.args.benchmark or self.args.smoke:
            t = self.elapsed*.08
            self.player.x,self.player.y = 26+math.sin(t)*31,40-math.cos(t)*31
            if self.args.benchmark and self.args.benchmark_route == 'streaming':
                self.player.x,self.player.y = math.sin(self.elapsed*.15)*220,10
            if self.args.benchmark_route == 'water':
                t = self.elapsed*.22
                self.player.x,self.player.y = 26+math.sin(t)*14,40-math.cos(t)*14
            self.player.z = self.terrain.surface(self.player.x,self.player.y)
            water = self.terrain.water(self.player.x,self.player.y)
            if water is not None:
                self.player.z = max(self.player.z,water-.75)
            self.player.heading = -math.degrees(math.atan2(26-self.player.x,40-self.player.y))
            self.player.pitch = -22 if self.args.benchmark_route == 'water' else -8
            self.player.sync_camera()
        self.world.update_streaming(self.player.x,self.player.y)
        self.world.water.update(dt,self.player,self.world.ducks,self.player.paused)
        if not self.player.paused:
            self.world.update_wildlife(dt,(self.player.x,self.player.y))
        self.world.root.setShaderInput('elapsed',self.elapsed)
        if self.environment:
            self.environment.update(self.player)
            eye = self.camera.getPos()
            self.sky.update(self.elapsed,(eye.x,eye.y,eye.z))
            if not self.player.paused:
                self.flocks.update(dt,(self.player.x,self.player.y,self.player.z))
        self.hud_timer += frame_time
        if self.hud_timer > .4:
            self.hud_timer = 0
            self.cached_scene,self.cached_ram = scene_counts(self.world.root),memory_mb()
            if self.hud:
                recent = list(self.samples)[-120:]
                self.hud.update(sum(recent)/len(recent) if recent else frame_time,
                                self.world.counts(),self.cached_scene,self.cached_ram)
        if self.hud:
            self.hud.pause.show() if self.player.paused else self.hud.pause.hide()
        if self.args.benchmark and self.benchmark_started is None:
            if not self.world.pending and self.world.building is None and len(self.world.chunks) == len(self.world.wanted):
                self.benchmark_started = now
                self.samples.clear()
        if self.args.smoke and self.frame >= self.args.frames:
            if not self.args.headless:
                self.screenshot()
            print('SMOKE_OK '+json.dumps({**self.world.counts(),**scene_counts(self.world.root)}))
            self.userExit()
        if self.args.benchmark and self.benchmark_started is not None and now-self.benchmark_started >= self.args.benchmark:
            self.samples = deque(self.benchmark_samples,maxlen=36000)
            self.record()
            self.userExit()
        return task.cont


def main():
    parser = argparse.ArgumentParser(description='Ducklands: FPS exploratorio procedural')
    parser.add_argument('--seed',type=int,default=938472)
    parser.add_argument('--radius',type=int,default=2,help='Raio de chunks: 1 a 5')
    parser.add_argument('--resolution',default='1280x720')
    parser.add_argument('--ui-scale',type=float,default=1.0,help='Escala de leitura da interface: 0.75 a 2')
    parser.add_argument('--grass-density',type=int,default=Settings().grass_per_chunk,help='Candidatos a tufos de grama por chunk')
    parser.add_argument('--shadows',choices=('off','low','medium','high'),default='off')
    parser.add_argument('--headless',action='store_true',help='Sem janela/render; valida simulacao CPU')
    parser.add_argument('--offscreen',action='store_true',help='Render em buffer sem janela interativa')
    parser.add_argument('--smoke',action='store_true',help='Cena carregada e execucao finita')
    parser.add_argument('--frames',type=int,default=180)
    parser.add_argument('--benchmark',type=float,default=0,metavar='SECONDS')
    parser.add_argument('--benchmark-route',choices=('lake','streaming','water'),default='lake')
    args = parser.parse_args()
    if args.frames <= 0 or args.benchmark < 0 or args.seed < 0:
        parser.error('Frames devem ser positivos; benchmark e seed devem ser nao negativos.')
    if not .75 <= args.ui_scale <= 2 or args.grass_density < 0:
        parser.error('UI scale deve estar entre 0.75 e 2; densidade deve ser nao negativa.')
    if args.headless and not (args.smoke or args.benchmark):
        parser.error('--headless requer --smoke ou --benchmark para encerrar automaticamente.')
    try:
        width,height = map(int,args.resolution.lower().split('x'))
        if width < 320 or height < 240:
            raise ValueError('Resolucao minima: 320x240.')
        settings = Settings(seed=args.seed,render_radius=args.radius,width=width,height=height,grass_per_chunk=args.grass_density)
    except ValueError as error:
        parser.error(str(error))
    app = Ducklands(settings,args)
    try:
        app.run()
    finally:
        if app.hud:
            app.hud.destroy()
        app.world.close()
        app.destroy()


if __name__ == '__main__':
    main()
