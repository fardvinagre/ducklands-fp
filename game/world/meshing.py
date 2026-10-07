"""Preparacao de buffers NumPy nos workers; nenhuma chamada Panda3D aqui."""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from game.engine.geometry import Mesh, GRASS_BLADES, GRASS_VERTICES, grass_buffer, grass_indices, mesh_buffer
from game.world.chunks import generate_chunk


@dataclass
class Buffer:
    name: str
    vertices: np.ndarray
    bounds: tuple
    kind: str = 'solid'
    cell: tuple | None = None
    indices: np.ndarray | None = None


@dataclass
class PreparedChunk:
    data: object
    buffers: list[Buffer]


@lru_cache(maxsize=12)
def tree_template(kind,low,variant=0):
    mesh = Mesh()
    rng = np.random.default_rng(1024+kind*73+variant*137)
    bark = (.29,.20,.115)
    if low:
        mesh.cone((0,0,0),.26,3.8,bark,5,.13)
        if kind == 0:
            mesh.cone((0,0,2),2.1,4.8,(.15,.34,.23),6)
            mesh.cone((0,0,4.1),1.35,3.0,(.20,.40,.26),5)
        else:
            mesh.ellipsoid((0,0,4.7),(2.8,2.35,2.6),(.29,.44,.20),7,4)
    else:
        for z,r,h,tip in ((-.10,.34,1.1,.26),(1,.26,1.4,.21),(2.4,.21,1.7,.11)):
            tint = rng.uniform(.88,1.10)
            mesh.cone((0,0,z),r,h,tuple(np.array(bark)*tint),9,tip)
        for j in range(5):
            angle = j*np.pi*2/5+variant*.7
            end = (np.cos(angle)*.85,np.sin(angle)*.85,-.03)
            mesh.branch((0,0,.30),end,.14,.025,bark,5)
        if kind == 0:
            for j in range(5):
                z = 1.75+j*.95
                radius = 2.05-j*.30
                color = (.13+j*.018,.31+j*.018,.20+j*.012)
                mesh.cone((rng.uniform(-.15,.15),rng.uniform(-.15,.15),z),radius,2.45-j*.16,color,9)
                if j < 3:
                    a = j*2.4+variant
                    mesh.branch((0,0,z+.35),(np.cos(a)*radius*.9,np.sin(a)*radius*.9,z+.15),.065,.015,bark,5)
        else:
            for j in range(6):
                a = j*np.pi*2/6+variant*.65
                reach = rng.uniform(1.15,2.05)
                center = (np.cos(a)*reach,np.sin(a)*reach,rng.uniform(3.8,5.2))
                mesh.branch((0,0,2.0+j*.16),center,.11,.035,bark,6)
                foliage_cluster(mesh,center,(rng.uniform(1.25,1.65),rng.uniform(1.25,1.65),rng.uniform(1.4,1.85)),
                                (.25+j*.011,.41+j*.011,.14+j*.009),rng)
            foliage_cluster(mesh,(.15,-.1,5.7),(1.55,1.5,1.8),(.35,.50,.20),rng)
    result = mesh_buffer(mesh)
    result.setflags(write=False)
    return result


def foliage_cluster(mesh,center,scale,color,rng):
    """Copas facetadas com contorno irregular e tons por face."""
    cluster = Mesh()
    cluster.ellipsoid(center,scale,color,8,5)
    center = np.asarray(center)
    for i in range(0,len(cluster.vertices),3):
        points = []
        for vertex in cluster.vertices[i:i+3]:
            local = vertex-center
            roughness = 1+.055*np.sin(local[0]*5.1+local[1]*3.7+local[2]*4.3)
            points.append(center+local*roughness)
        mesh.triangle(*points,tuple(np.array(color)*rng.uniform(.93,1.06)))


@lru_cache(maxsize=1)
def rock_template():
    mesh = Mesh()
    mesh.ellipsoid((0,0,.3),(.8,.6,.6),(.43,.44,.40),5,3)
    result = mesh_buffer(mesh)
    result.setflags(write=False)
    return result


def warm_templates():
    for low in (False,True):
        for kind in (0,1):
            for variant in range(3):
                tree_template(kind,low,variant)
    rock_template()


def transformed(template,points,rotate=False):
    if not len(points):
        return np.empty((0,10),dtype=np.float32)
    result = np.broadcast_to(template,(len(points),*template.shape)).copy()
    if rotate:
        angles = points[:,0]*.731+points[:,1]*1.317
        c,s = np.cos(angles)[:,None],np.sin(angles)[:,None]
        for column in (0,3):
            x,y = result[:,:,column].copy(),result[:,:,column+1].copy()
            result[:,:,column],result[:,:,column+1] = x*c-y*s,x*s+y*c
        tint = (.95+.10*np.sin(angles*.4))[:,None,None]
        result[:,:,6:9] *= tint
    result[:,:,:3] = result[:,:,:3]*points[:,None,3:4]+points[:,None,:3]
    return result.reshape(-1,10)


def pack(name,vertices,kind='solid',cell=None,indices=None):
    vertices = np.ascontiguousarray(vertices,dtype=np.float32)
    if not len(vertices):
        return None
    return Buffer(name,vertices,(vertices[:,:3].min(axis=0),vertices[:,:3].max(axis=0)),kind,cell,indices)


def prepare_geometry(data,settings):
    buffers = []
    tri = data.vertices[data.triangles]
    normals = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    normals /= np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-8)
    terrain = np.ones((len(tri),3,10),dtype=np.float32)
    terrain[:,:,:3] = tri
    terrain[:,:,3:6] = normals[:,None,:]
    terrain[:,:,6:9] = data.colors[data.triangles].mean(axis=1)[:,None,:]
    buffers.append(pack('terrain',terrain.reshape(-1,10)))
    pine = np.arange(len(data.trees))%3 == 0
    variants = np.arange(len(data.trees))//3%3
    for low in (False,True):
        pieces = [transformed(tree_template(kind,low,variant),data.trees[(pine if kind == 0 else ~pine)&(variants==variant)],rotate=True)
                  for kind in (0,1) for variant in range(3)]
        item = pack('trees-lod1' if low else 'trees-lod0',np.concatenate(pieces), 'low' if low else 'high')
        if item:
            buffers.append(item)
    rocks = pack('rocks',transformed(rock_template(),data.rocks))
    if rocks:
        buffers.append(rocks)
    # Celulas pequenas permitem frustum culling automatico da grama.
    cell_size = settings.grass_cell_size
    cells = np.floor(data.grass[:,:2]/cell_size).astype(np.int32)
    # Gera uma vez: LOD reutiliza as mesmas laminas e cores, sem mudar o visual proximo.
    grass = grass_buffer(data.grass,hash(data.key)&0xffffffff).reshape(-1,GRASS_BLADES,GRASS_VERTICES,10)
    for cell in np.unique(cells,axis=0):
        mask = np.all(cells == cell,axis=1)
        high = grass[mask]
        cell_key = tuple(int(v) for v in cell)
        buffers.append(pack('grass-high',high.reshape(-1,10),'grass-high',cell_key,grass_indices(len(high)*GRASS_BLADES)))
        buffers.append(pack('grass-low',high[:,:2][:,:,[0,1,4],:].reshape(-1,10),'grass-low',cell_key))
    return PreparedChunk(data,buffers)


def prepare_chunk(key,settings,terrain):
    return prepare_geometry(generate_chunk(key,settings,terrain),settings)
