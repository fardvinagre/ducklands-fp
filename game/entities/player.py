import math

from panda3d.core import WindowProperties

from game.engine.physics import resolve_horizontal


class Player:
    def __init__(self,app,terrain):
        self.app,self.terrain = app,terrain
        self.x,self.y = 0.0,0.0
        self.z = terrain.surface(0,0)
        self.vertical_speed = 0
        self.grounded = True
        self.heading,self.pitch = -28.0,0.0
        self.keys = {}
        self.paused = False
        for key in ('w','a','s','d','shift','control'):
            app.accept(key,self.set_key,[key,True])
            app.accept(key+'-up',self.set_key,[key,False])
        app.accept('space',self.jump)
        app.accept('escape',self.toggle_pause)
        app.accept('mouse1',self.resume)
        if hasattr(app.win,'requestProperties'):
            self.capture(True)
        self.sync_camera()

    def set_key(self,key,value):
        self.keys[key] = value

    def capture(self,enabled):
        props = WindowProperties()
        props.setCursorHidden(enabled)
        props.setMouseMode(WindowProperties.M_confined if enabled else WindowProperties.M_absolute)
        self.app.win.requestProperties(props)
        if enabled:
            self.center_mouse()

    def center_mouse(self):
        self.app.win.movePointer(0,self.app.win.getXSize()//2,self.app.win.getYSize()//2)

    def toggle_pause(self):
        self.paused = not self.paused
        self.keys.clear()
        if hasattr(self.app.win,'requestProperties'):
            self.capture(not self.paused)

    def resume(self):
        if self.paused:
            self.toggle_pause()

    def jump(self):
        if self.grounded and not self.paused:
            self.vertical_speed,self.grounded = 6.5,False

    def update(self,dt,world,mouse=True):
        if self.paused:
            return
        if mouse and hasattr(self.app.win,'getPointer'):
            if not self.app.win.getProperties().getForeground():
                self.toggle_pause()
                return
            pointer = self.app.win.getPointer(0)
            dx = pointer.getX()-self.app.win.getXSize()//2
            dy = pointer.getY()-self.app.win.getYSize()//2
            self.heading -= dx*.12
            self.pitch = max(-85,min(85,self.pitch-dy*.12))
            self.center_mouse()
        forward = int(self.keys.get('w',False))-int(self.keys.get('s',False))
        strafe = int(self.keys.get('d',False))-int(self.keys.get('a',False))
        speed = 10 if self.keys.get('shift') else 5
        if self.keys.get('control'):
            speed = 2.5
        if self.terrain.water(self.x,self.y) is not None:
            speed *= .55
        heading = math.radians(self.heading)
        dx = -math.sin(heading)*forward+math.cos(heading)*strafe
        dy = math.cos(heading)*forward+math.sin(heading)*strafe
        norm = max(1,math.hypot(dx,dy))
        # Subpassos impedem atravessar troncos/rochas em frames lentos.
        steps = max(1,math.ceil(speed*dt/.20))
        for _ in range(steps):
            nx,ny = self.x+dx/norm*speed*dt/steps,self.y+dy/norm*speed*dt/steps
            bound = self.terrain.settings.world_half_size-.5
            nx,ny = max(-bound,min(bound,nx)),max(-bound,min(bound,ny))
            key = (math.floor(nx/world.settings.chunk_size),math.floor(ny/world.settings.chunk_size))
            if key in world.chunks:
                self.x,self.y = resolve_horizontal(nx,ny,world.obstacles(nx,ny))
                self.x,self.y = max(-bound,min(bound,self.x)),max(-bound,min(bound,self.y))
        ground = self.terrain.surface(self.x,self.y)
        water = self.terrain.water(self.x,self.y)
        if water is not None:
            ground = max(ground,water-.75)
        self.vertical_speed -= 18*dt
        self.z += self.vertical_speed*dt
        if self.z <= ground:
            self.z,self.vertical_speed,self.grounded = ground,0,True
        else:
            self.grounded = False
        self.sync_camera()

    def sync_camera(self):
        self.app.camera.setPos(self.x,self.y,self.z+(1.05 if self.keys.get('control') else 1.75))
        self.app.camera.setHpr(self.heading,self.pitch,0)
