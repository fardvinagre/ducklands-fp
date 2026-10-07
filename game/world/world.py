import math
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

from panda3d.core import NodePath, Shader

from game.engine.geometry import buffer_node, duck_model
from game.entities.duck import Duck, DuckState
from game.entities.duck_anim import DuckRig
from game.engine.renderer import SHADOW_MASK
from game.systems.spatial import SpatialGrid
from game.world.chunks import ChunkState
from game.world.meshing import prepare_chunk, prepare_geometry, warm_templates
from game.world.water import WaterSystem


@dataclass
class LiveChunk:
    data: object
    node: NodePath
    high: NodePath
    low: NodePath
    grass: NodePath
    state: ChunkState = ChunkState.ACTIVE
    grass_cells: list = field(default_factory=list)
    geometry_bytes: int = 0


class World:
    def __init__(self, app, settings, terrain, shader_dir):
        self.app, self.settings, self.terrain = app, settings, terrain
        self.root = app.render.attachNewNode('world')
        self.chunks = {}
        self.pending = {}
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.cache_hits = 0
        self.building = None
        self.stream_ms = 0.0
        self.stream_peak_ms = 0.0
        warm_templates()
        self.wanted = set()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='chunk-data')
        self.revision = 0
        self.ducks = []
        self.duck_nodes = {}
        self.grid = SpatialGrid()
        self.duck_template = duck_model()
        self.duck_rigs = {}
        self.spawn_tokens = {}
        self.duck_spawns = {}
        self.serial = 0
        self.grass_shader = Shader.make(Shader.SL_GLSL, (shader_dir/'grass.vert').read_text(), (shader_dir/'grass.frag').read_text())
        self.water = WaterSystem(self.root, terrain, shader_dir)
        self.root.setShaderInput('elapsed',0.0)

    def desired(self,x,y):
        size,r = self.settings.chunk_size,self.settings.render_radius
        cx,cy = math.floor(x/size),math.floor(y/size)
        limit = self.settings.world_half_size//size
        return {(a,b) for a in range(cx-r,cx+r+1) for b in range(cy-r,cy+r+1)
                if -limit <= a < limit and -limit <= b < limit}

    def refresh(self):
        """Invalida resultados antigos sem permitir filas de workers ilimitadas."""
        self.revision += 1
        for key,(future,_) in list(self.pending.items()):
            if future.cancel():
                del self.pending[key]
        for chunk in self.chunks.values():
            chunk.node.removeNode()
        self.chunks.clear()
        self.cancel_build()
        for chunk in self.cache.values():
            chunk.node.removeNode()
        self.cache.clear()
        self.cache_bytes = 0
        for node in self.duck_nodes.values():
            node.removeNode()
        self.ducks.clear()
        self.duck_nodes.clear()
        self.duck_rigs.clear()
        self.spawn_tokens.clear()
        self.duck_spawns.clear()

    def build_steps(self,prepared,spawn=True):
        """Um buffer por passo; publica o chunk completo apenas no final."""
        data = prepared.data
        root = NodePath(f'chunk-{data.key}')
        high,low = root.attachNewNode('trees-high'),root.attachNewNode('trees-low')
        grass = root.attachNewNode('grass-group')
        grass.hide(SHADOW_MASK)
        grass.setShader(self.grass_shader)
        grass.setShaderInput('grassLod',0.0)
        cells = {}
        published = False
        try:
            for item in prepared.buffers:
                node = buffer_node(item.name,item.vertices,item.kind.startswith('grass'),item.bounds,item.indices)
                if item.kind.startswith('grass'):
                    if item.cell not in cells:
                        cells[item.cell] = [grass.attachNewNode(f'cell-{item.cell}'),None,None]
                    entry = cells[item.cell]
                    node.reparentTo(entry[0])
                    entry[1 if item.kind == 'grass-high' else 2] = node
                else:
                    node.reparentTo(high if item.kind == 'high' else (low if item.kind == 'low' else root))
                yield
            cell_list = []
            size = self.settings.grass_cell_size
            for key,(group,detail,simple) in cells.items():
                simple.setShaderInput('grassLod',1.0)
                simple.hide()
                cell_list.append(((key[0]+.5)*size,(key[1]+.5)*size,group,detail,simple))
            low.hide()
            chunk = LiveChunk(data,root,high,low,grass,grass_cells=cell_list,
                              geometry_bytes=sum(b.vertices.nbytes+(b.indices.nbytes if b.indices is not None else len(b.vertices)*4) for b in prepared.buffers))
            root.reparentTo(self.root)
            self.chunks[data.key] = chunk
            published = True
            if spawn:
                self.spawn_chunk_ducks(data)
        finally:
            if not published:
                root.removeNode()

    def commit(self,data,spawn=True):
        """Carregamento sincronico reservado ao startup e testes."""
        prepared = prepare_geometry(data,self.settings)
        for _ in self.build_steps(prepared,spawn):
            pass

    def cancel_build(self):
        if self.building is not None:
            self.building[1].close()
            self.building = None

    def cache_chunk(self,key):
        chunk = self.chunks.pop(key)
        chunk.node.detachNode()
        chunk.state = ChunkState.UNLOADED
        self.cache[key] = chunk
        self.cache_bytes += chunk.geometry_bytes
        limit = self.settings.chunk_cache_mb*1024*1024
        while len(self.cache) > self.settings.chunk_cache_count or self.cache_bytes > limit:
            _,old = self.cache.popitem(last=False)
            self.cache_bytes -= old.geometry_bytes
            old.node.removeNode()

    def restore_chunk(self,key):
        chunk = self.cache.pop(key)
        self.cache_bytes -= chunk.geometry_bytes
        self.cache_hits += 1
        chunk.node.reparentTo(self.root)
        self.chunks[key] = chunk
        # O cache guarda geometria. A fauna que saiu do raio e recriada.
        self.spawn_chunk_ducks(chunk.data)

    def spawn_chunk_ducks(self,data):
        for i,(x,y,z,_) in enumerate(data.ducks):
            token = (data.key,i)
            if token not in self.duck_spawns:
                self.add_duck(float(x),float(y),float(z),token)

    def add_duck(self,x,y,z,token=None):
        self.serial += 1
        duck = Duck(x,y,z,self.settings.seed+self.serial*7919)
        duck.z = max(z,self.terrain.water(x,y) if self.terrain.water(x,y) is not None else z)
        self.ducks.append(duck)
        node = self.duck_template.copyTo(self.root)
        node.setPos(x,y,duck.z)
        self.duck_nodes[id(duck)] = node
        self.duck_rigs[id(duck)] = DuckRig(node,x,y,duck.z,math.degrees(duck.heading)-90)
        if token is not None:
            self.spawn_tokens[id(duck)] = token
            self.duck_spawns[token] = id(duck)

    def add_ducks(self,count,player):
        import random
        rng = random.Random(self.settings.seed+self.serial)
        lake = self.terrain.nearest_lake(*player)
        for _ in range(count):
            x,y = lake.x+rng.uniform(-12,12),lake.y+rng.uniform(-12,12)
            self.add_duck(x,y,float(self.terrain.height(x,y)))

    def update_streaming(self,x,y):
        started = time.perf_counter()
        self.wanted = self.desired(x,y)
        # Restaura o cache antes de inserir chunks antigos e provocar despejos.
        for key in self.wanted & self.cache.keys():
            self.restore_chunk(key)
        for key in set(self.chunks)-self.wanted:
            self.cache_chunk(key)
        if self.building is not None and self.building[0] not in self.wanted:
            self.cancel_build()
        for key,(future,_) in list(self.pending.items()):
            if key not in self.wanted and future.cancel():
                del self.pending[key]
        # Limite de tempo e de passos. Um passo individual nao e preemptivo.
        deadline = started+self.settings.upload_budget_ms/1000
        steps = 0
        while time.perf_counter() < deadline and steps < self.settings.upload_steps_per_frame:
            if self.building is None:
                ready = [key for key,(future,_) in self.pending.items() if future.done()]
                if not ready:
                    break
                key = min(ready,key=lambda k: ((k[0]+.5)*self.settings.chunk_size-x)**2+((k[1]+.5)*self.settings.chunk_size-y)**2)
                future,revision = self.pending.pop(key)
                prepared = future.result()
                if key not in self.wanted or revision != self.revision:
                    continue
                self.building = (key,self.build_steps(prepared))
            try:
                next(self.building[1])
            except StopIteration:
                self.building = None
            steps += 1
        missing = self.wanted-set(self.chunks)-set(self.pending)
        if self.building is not None:
            missing.discard(self.building[0])
        size = self.settings.chunk_size
        for key in sorted(missing,key=lambda k: ((k[0]+.5)*size-x)**2+((k[1]+.5)*size-y)**2):
            if len(self.pending)+(self.building is not None) >= 4:
                break
            self.pending[key] = (self.executor.submit(prepare_chunk,key,replace(self.settings),self.terrain),self.revision)
        cx,cy = math.floor(x/size),math.floor(y/size)
        for (a,b),chunk in self.chunks.items():
            active = max(abs(a-cx),abs(b-cy)) <= self.settings.active_radius
            state = ChunkState.ACTIVE if active else ChunkState.SLEEPING
            if chunk.state != state:
                if active:
                    chunk.high.show(); chunk.low.hide()
                else:
                    chunk.high.hide(); chunk.low.show()
                chunk.state = state
            for gx,gy,group,detail,simple in chunk.grass_cells:
                distance2 = (gx-x)**2+(gy-y)**2
                if distance2 > 105**2:
                    if not group.isHidden():
                        group.hide()
                else:
                    if group.isHidden():
                        group.show()
                    near = distance2 < 36**2
                    if near and detail.isHidden():
                        detail.show(); simple.hide()
                    elif not near and simple.isHidden():
                        detail.hide(); simple.show()
        # Animais pertencem a posicoes, nao ao chunk de origem.
        kept = []
        for duck in self.ducks:
            if (math.floor(duck.x/size),math.floor(duck.y/size)) in self.wanted:
                kept.append(duck)
            else:
                self.duck_nodes.pop(id(duck)).removeNode()
                self.duck_rigs.pop(id(duck))
                token = self.spawn_tokens.pop(id(duck),None)
                if token is not None:
                    self.duck_spawns.pop(token)
        self.ducks = kept
        self.stream_ms = (time.perf_counter()-started)*1000
        self.stream_peak_ms = max(self.stream_peak_ms,self.stream_ms)

    def obstacles(self,x,y,radius=3):
        size = self.settings.chunk_size
        for cx in range(math.floor((x-radius)/size),math.floor((x+radius)/size)+1):
            for cy in range(math.floor((y-radius)/size),math.floor((y+radius)/size)+1):
                chunk = self.chunks.get((cx,cy))
                if chunk is None:
                    continue
                for points,scale in ((chunk.data.trees,.28),(chunk.data.rocks,.8)):
                    for ox,oy,_,s in points:
                        if abs(ox-x) < radius+1 and abs(oy-y) < radius+1:
                            yield float(ox),float(oy),float(s*scale)

    def update_wildlife(self,dt,player):
        self.grid.rebuild(self.ducks)
        self.active_ducks = 0
        for duck in self.ducks:
            distance = math.hypot(duck.x-player[0],duck.y-player[1])
            interval = 1/60 if distance < 30 else (.1 if distance < 100 else (1 if distance < 180 else math.inf))
            duck.accumulator += dt
            if math.isfinite(interval):
                self.active_ducks += 1
            if duck.accumulator >= interval:
                step = min(duck.accumulator,1)
                duck.accumulator = 0
                duck.update(step,player,self.terrain,self.grid.nearby(duck.x,duck.y,5),self.obstacles(duck.x,duck.y))
                if duck.state == DuckState.SWIMMING:
                    level = self.terrain.water(duck.x,duck.y)
                    if level is not None:
                        duck.z = level + self.water.offset(duck.x,duck.y)
                self.duck_rigs[id(duck)].animate(duck,step if distance >= 100 else dt)
            elif distance < 100:
                if duck.state == DuckState.SWIMMING:
                    level = self.terrain.water(duck.x,duck.y)
                    if level is not None:
                        duck.z = level + self.water.offset(duck.x,duck.y)
                self.duck_rigs[id(duck)].animate(duck,dt)

    def counts(self):
        return dict(chunks=len(self.chunks), loading=len(self.pending)+(self.building is not None),
                    cached_chunks=len(self.cache),cache_hits=self.cache_hits,
                    stream_ms=round(self.stream_ms,3),stream_peak_ms=round(self.stream_peak_ms,3),
                    active_chunks=sum(c.state == ChunkState.ACTIVE for c in self.chunks.values()),
                    trees=sum(len(c.data.trees) for c in self.chunks.values()),
                    grass=sum(len(c.data.grass) for c in self.chunks.values()),
                    rocks=sum(len(c.data.rocks) for c in self.chunks.values()),
                    ducks=len(self.ducks),active_ducks=getattr(self,'active_ducks',0),
                    water_lakes=len(self.water.surfaces),
                    water_active=sum(s.active for s in self.water.surfaces.values()),
                    water_cpu_ms=round(self.water.cpu_ms,3))

    def close(self):
        self.water.close()
        self.cancel_build()
        for future,_ in self.pending.values():
            future.cancel()
        self.executor.shutdown(wait=True,cancel_futures=True)
        for chunk in self.cache.values():
            chunk.node.removeNode()
        self.cache.clear()
        self.cache_bytes = 0
