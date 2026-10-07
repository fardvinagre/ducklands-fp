from panda3d.core import AmbientLight, BitMask32, DirectionalLight, Fog, Vec4

# Mascara da camera de sombras; a grama nao projeta sombras.
SHADOW_MASK = BitMask32.bit(1)


class Environment:
    def __init__(self,app):
        self.app = app
        app.disableMouse()
        app.setBackgroundColor(.57,.74,.82,1)
        app.camLens.setFov(78)
        app.camLens.setNearFar(.08,400)
        ambient = AmbientLight('sky-light')
        ambient.setColor(Vec4(.47,.51,.55,1))
        self.ambient = app.render.attachNewNode(ambient)
        app.render.setLight(self.ambient)
        self.sun = DirectionalLight('sun')
        self.sun.setColor(Vec4(.90,.83,.64,1))
        self.sun.getLens().setFilmSize(140,140)
        self.sun.getLens().setNearFar(1,260)
        self.sun_node = app.render.attachNewNode(self.sun)
        self.sun_node.setHpr(-35,-55,0)
        app.render.setLight(self.sun_node)
        app.cam.node().setCameraMask(BitMask32.bit(0))
        self.sun.setCameraMask(SHADOW_MASK)
        app.render.setShaderInput('shadowOn',0.0)
        app.render.setShaderAuto()
        fog = Fog('distance-haze')
        fog.setColor(.57,.74,.82)
        fog.setLinearRange(90,190)
        app.render.setFog(fog)
        self.shadow_index = 0
        self.shadow_names = ('OFF','LOW','MEDIUM','HIGH')

    @property
    def shadow_quality(self):
        return self.shadow_names[self.shadow_index]

    def cycle_shadows(self):
        self.shadow_index = (self.shadow_index+1)%4
        resolutions = (0,512,1024,2048)
        size = resolutions[self.shadow_index]
        self.sun.setShadowCaster(size>0,size or 512,size or 512)
        self.app.render.setShaderInput('shadowOn',1.0 if size else 0.0)

    def update(self,player):
        self.sun_node.setPos(player.x-45,player.y-55,player.z+100)
