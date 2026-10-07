import math

import numpy as np
from panda3d.core import (BoundingBox, Point3, Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat,
                         GeomVertexData, GeomVertexFormat, GeomVertexWriter, NodePath)


class Mesh:
    """Batch de triangulos com normais por face para o estilo low-poly."""
    def __init__(self):
        self.vertices = []
        self.normals = []
        self.colors = []

    def triangle(self, a, b, c, color):
        a, b, c = np.asarray(a), np.asarray(b), np.asarray(c)
        normal = np.cross(b-a, c-a)
        length = np.linalg.norm(normal)
        if length < 1e-8:
            return
        normal /= length
        self.vertices.extend((a, b, c))
        self.normals.extend((normal, normal, normal))
        self.colors.extend((color, color, color))

    def ellipsoid(self, center, scale, color, segments=7, rings=4):
        def point(i, j):
            latitude = -math.pi/2 + math.pi*i/rings
            angle = math.tau*j/segments
            return np.array(center) + np.array(scale) * (
                math.cos(latitude)*math.cos(angle), math.cos(latitude)*math.sin(angle), math.sin(latitude))
        for i in range(rings):
            for j in range(segments):
                a, b, c, d = point(i,j), point(i,j+1), point(i+1,j), point(i+1,j+1)
                self.triangle(a,b,c,color)
                self.triangle(b,d,c,color)

    def cone(self, center, radius, height, color, segments=7, top_radius=0):
        x, y, z = center
        for i in range(segments):
            a, b = math.tau*i/segments, math.tau*(i+1)/segments
            p = (x+radius*math.cos(a), y+radius*math.sin(a), z)
            q = (x+radius*math.cos(b), y+radius*math.sin(b), z)
            r = (x+top_radius*math.cos(a), y+top_radius*math.sin(a), z+height)
            t = (x+top_radius*math.cos(b), y+top_radius*math.sin(b), z+height)
            self.triangle(p,q,r,color)
            if top_radius:
                self.triangle(q,t,r,color)

    def node(self, name):
        return buffer_node(name, mesh_buffer(self))

    def branch(self,start,end,radius,tip_radius,color,segments=6):
        start,end = np.asarray(start,dtype=float),np.asarray(end,dtype=float)
        axis = end-start
        axis /= np.linalg.norm(axis)
        reference = np.array((0,0,1)) if abs(axis[2]) < .9 else np.array((1,0,0))
        u = np.cross(axis,reference)
        u /= np.linalg.norm(u)
        v = np.cross(axis,u)
        for i in range(segments):
            a,b = math.tau*i/segments,math.tau*(i+1)/segments
            pa,pb = u*math.cos(a)+v*math.sin(a),u*math.cos(b)+v*math.sin(b)
            self.triangle(start+pa*radius,start+pb*radius,end+pa*tip_radius,color)
            self.triangle(start+pb*radius,end+pb*tip_radius,end+pa*tip_radius,color)


def mesh_buffer(mesh):
    count = len(mesh.vertices)
    buffer = np.ones((count,10),dtype=np.float32)
    if count:
        buffer[:,:3] = mesh.vertices
        buffer[:,3:6] = mesh.normals
        for i,color in enumerate(mesh.colors):
            buffer[i,6:6+len(color)] = color
    return buffer


_SOLID_FORMAT = None


def _solid_format():
    global _SOLID_FORMAT
    if _SOLID_FORMAT is None:
        array = GeomVertexArrayFormat()
        array.addColumn('vertex',3,Geom.NTFloat32,Geom.CPoint)
        array.addColumn('normal',3,Geom.NTFloat32,Geom.CNormal)
        array.addColumn('color',4,Geom.NTFloat32,Geom.CColor)
        fmt = GeomVertexFormat()
        fmt.addArray(array)
        _SOLID_FORMAT = GeomVertexFormat.registerFormat(fmt)
    return _SOLID_FORMAT


def buffer_node(name,buffer,grass=False,bounds=None,indices=None):
    """Thread principal: copia em bloco, sem chamadas Python por vertice."""
    count = len(buffer)
    data = GeomVertexData(name,_grass_format() if grass else _solid_format(),Geom.UHStatic)
    data.uncleanSetNumRows(count)
    data.modifyArray(0).modifyHandle().copyDataFrom(buffer.tobytes())
    prim = GeomTriangles(Geom.UHStatic)
    prim.setIndexType(Geom.NTUint32)
    if indices is None:
        prim.addConsecutiveVertices(0,count)
    else:
        array = prim.modifyVertices()
        array.setNumRows(len(indices))
        array.modifyHandle().copyDataFrom(np.asarray(indices,dtype=np.uint32).tobytes())
    prim.closePrimitive()
    geom = Geom(data)
    geom.addPrimitive(prim)
    node = GeomNode(name)
    node.addGeom(geom)
    if count:
        if bounds is None:
            bounds = (buffer[:,:3].min(axis=0),buffer[:,:3].max(axis=0))
        margin = .2 if grass else 0
        box = BoundingBox(Point3(*(bounds[0]-margin)),Point3(*(bounds[1]+margin)))
        geom.setBounds(box)
        node.setBounds(box)
        node.setFinal(True)
    path = NodePath(node)
    if grass:
        path.setTwoSided(True)
    return path


def terrain_mesh(data):
    mesh = Mesh()
    for triangle in data.triangles:
        mesh.triangle(*data.vertices[triangle], data.colors[triangle].mean(axis=0))
    return mesh.node('terrain')


def trees_mesh(points, low=False):
    mesh = Mesh()
    for i, (x,y,z,s) in enumerate(points):
        mesh.cone((x,y,z), .25*s, 3.6*s, (.29,.18,.09), 5, .16*s)
        if low or i % 3 == 0:
            mesh.cone((x,y,z+2*s), 2.0*s, 4.6*s, (.13,.32,.19), 5 if low else 8)
            if not low:
                mesh.cone((x,y,z+4*s), 1.5*s, 3.5*s, (.19,.40,.23), 7)
        else:
            mesh.ellipsoid((x,y,z+4.5*s), (2.6*s,2.1*s,2.8*s), (.24,.43,.18), 7, 3)
            mesh.ellipsoid((x+1.2*s,y-.4*s,z+4*s), (1.7*s,1.6*s,1.9*s), (.32,.49,.19), 6, 3)
    return mesh.node('trees-lod1' if low else 'trees-lod0')


def rocks_mesh(points):
    mesh = Mesh()
    for x,y,z,s in points:
        mesh.ellipsoid((x,y,z+.3*s), (.8*s,.6*s,.6*s), (.43,.44,.40), 5, 3)
    return mesh.node('rocks')


GRASS_BLADES = 5
GRASS_VERTICES = 5
_GRASS_FORMAT = None


def _grass_format():
    global _GRASS_FORMAT
    if _GRASS_FORMAT is None:
        array = GeomVertexArrayFormat()
        array.addColumn('vertex', 3, Geom.NTFloat32, Geom.CPoint)
        array.addColumn('color', 4, Geom.NTFloat32, Geom.CColor)
        array.addColumn('texcoord', 3, Geom.NTFloat32, Geom.CTexcoord)
        fmt = GeomVertexFormat()
        fmt.addArray(array)
        _GRASS_FORMAT = GeomVertexFormat.registerFormat(fmt)
    return _GRASS_FORMAT


def grass_buffer(points, seed=0):
    """Buffer vetorizado dos tufos de grama.

    Alpha da cor = peso do vento (0 na base, 1 na ponta). O texcoord guarda o ponto
    de raiz da lamina: o shader usa para sombra e fade por lamina inteira, nao por vertice.
    """
    points = np.asarray(points, dtype=np.float32).reshape(-1, 4)
    count = len(points) * GRASS_BLADES
    rng = np.random.default_rng(seed)
    base = np.repeat(points, GRASS_BLADES, axis=0)
    x, y, z, s = base.T
    spread = rng.uniform(0, .27, count)
    place = rng.uniform(0, np.pi*2, count)
    cx, cy = x + np.cos(place)*spread, y + np.sin(place)*spread
    height = (.13 + rng.random(count)**1.5*.34) * s
    half = rng.uniform(.015, .029, count) * (.7 + .3*s)
    facing = rng.uniform(0, np.pi*2, count)
    lean = rng.uniform(.16, .48, count) * height
    lean_dir = rng.uniform(0, np.pi*2, count)
    ux, uy = np.cos(facing)*half, np.sin(facing)*half
    zb = z - .02
    tip = np.stack((cx + np.cos(lean_dir)*lean, cy + np.sin(lean_dir)*lean, z + height), axis=1)
    patch = .5+.5*np.sin(x*.12 + np.sin(y*.17)*1.6)
    shade = (rng.uniform(.86,1.10,count)*(.90+.16*patch))[:,None]
    root_color = np.column_stack((.17+.03*patch,.31+.055*patch,.075+.025*patch))
    tip_color = np.column_stack((.40+.10*patch,.61+.085*patch,.14+.065*patch))
    verts = np.empty((count, GRASS_VERTICES, 10), dtype=np.float32)
    verts[:, 0, :3] = np.stack((cx-ux, cy-uy, zb), axis=1)
    verts[:, 1, :3] = np.stack((cx+ux, cy+uy, zb), axis=1)
    mid = np.stack((cx+np.cos(lean_dir)*lean*.32,cy+np.sin(lean_dir)*lean*.32,z+height*.57),axis=1)
    verts[:,2,:3] = mid-np.stack((ux,uy,np.zeros(count)),axis=1)*.55
    verts[:,3,:3] = mid+np.stack((ux,uy,np.zeros(count)),axis=1)*.55
    verts[:,4,:3] = tip
    verts[:, :2, 3:6] = (root_color*shade)[:, None, :]
    verts[:,2:4,3:6] = ((root_color*.43+tip_color*.57)*shade)[:,None,:]
    verts[:,4,3:6] = tip_color*shade
    verts[:, :2, 6] = 0
    verts[:,2:4,6] = .57
    verts[:,4,6] = 1
    verts[:, :, 7:10] = np.stack((cx, cy, z + .15), axis=1)[:, None, :]
    return verts.reshape(-1,10)


def grass_mesh(points,seed=0):
    vertices = grass_buffer(points,seed)
    return buffer_node('grass-batch',vertices,grass=True,indices=grass_indices(len(vertices)//GRASS_VERTICES))


def grass_indices(blades):
    offsets = np.arange(blades,dtype=np.uint32)[:,None]*GRASS_VERTICES
    return (offsets+np.array((0,1,2,1,3,2,2,3,4),dtype=np.uint32)).ravel()


def duck_model():
    """Rig do pato: body > (neck > head, tail, wings, feet). Pivos nomeados para o DuckRig."""
    root = NodePath('duck')
    body = root.attachNewNode('body_pivot')
    body.setPos(0, 0, .30)
    mesh = Mesh()
    mesh.ellipsoid((0,0,0), (.30,.49,.25), (.62,.53,.37))
    mesh.node('torso').reparentTo(body)

    neck = body.attachNewNode('neck')
    neck.setPos(0, .30, .15)
    mesh = Mesh()
    mesh.ellipsoid((0,.02,.05), (.10,.10,.13), (.10,.34,.23), 5, 3)
    mesh.ellipsoid((0,.08,.11), (.18,.20,.22), (.10,.34,.23))
    mesh.ellipsoid((0,.29,.08), (.13,.19,.055), (.94,.67,.15), 5, 3)
    for x in (-.155,.155):
        mesh.ellipsoid((x,.16,.17), (.03,.025,.03), (.025,.025,.02), 5, 3)
    mesh.node('head').reparentTo(neck)

    tail = body.attachNewNode('tail')
    tail.setPos(0, -.32, .05)
    mesh = Mesh()
    mesh.ellipsoid((0,-.10,-.03), (.17,.24,.12), (.23,.24,.19), 5, 3)
    mesh.node('tail-mesh').reparentTo(tail)

    for side in (-1,1):
        pivot = body.attachNewNode('wing')
        pivot.setPos(side*.20, 0, .10)
        wing = Mesh()
        wing.ellipsoid((side*.17,-.02,0), (.25,.34,.075), (.38,.40,.34), 5, 3)
        wing.node('feathers').reparentTo(pivot)

        foot = body.attachNewNode('foot')
        foot.setPos(side*.10, 0, -.10)
        leg = Mesh()
        leg.ellipsoid((0,0,-.09), (.018,.018,.10), (.90,.55,.12), 4, 2)
        leg.ellipsoid((0,.05,-.18), (.045,.09,.012), (.90,.55,.12), 4, 2)
        leg.node('foot-mesh').reparentTo(foot)
    return root
