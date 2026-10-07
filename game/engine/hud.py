from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.DirectObject import DirectObject
from panda3d.core import TextNode


class HUD(DirectObject):
    """Interface em pixels, com leitura e layout atualizados ao redimensionar."""
    def __init__(self,app):
        self.app = app
        self.debug = True
        self.size = (0,0)
        self.root = app.pixel2d.attachNewNode('responsive-hud')
        self.top_panel = DirectFrame(parent=self.root,frameColor=(.025,.06,.045,.80))
        self.bottom_panel = DirectFrame(parent=self.root,frameColor=(.025,.06,.045,.80))
        def label(text='',parent=None,align=TextNode.ALeft,color=(.95,.97,.91,1)):
            return OnscreenText(text=text,parent=parent if parent is not None else self.root,align=align,scale=18,
                                fg=color,shadow=(0,0,0,.8),mayChange=True)
        self.title = label('DUCKLANDS / 0.5',color=(1,.94,.76,1))
        self.stats = label()
        self.location = label()
        self.controls = label(color=(.87,.93,.89,1))
        self.crosshair = label('+',align=TextNode.ACenter,color=(1,1,1,.65))
        self.notice_panel = DirectFrame(parent=self.root,frameColor=(.04,.09,.06,.9))
        self.notice = label(align=TextNode.ACenter,color=(1,.94,.72,1))
        self.notice_until = 0
        self.pause = DirectFrame(parent=self.root,frameColor=(.04,.09,.08,.96))
        self.pause_title = label('EXPLORACAO PAUSADA',parent=self.pause,align=TextNode.ACenter,color=(1,.94,.76,1))
        self.resume_button = DirectButton(parent=self.pause,text='Continuar',command=app.player.resume,
                                         frameColor=(.23,.4,.28,1),text_fg=(1,1,1,1))
        self.exit_button = DirectButton(parent=self.pause,text='Sair',command=app.userExit,
                                       frameColor=(.22,.28,.26,1),text_fg=(1,1,1,1))
        self.pause.hide()
        self.notice_panel.hide()
        self.accept('f1',self.toggle_debug)
        self.accept('window-event',self.window_event)
        self.layout(app.win.getXSize(),app.win.getYSize())

    def window_event(self,window):
        if window == self.app.win:
            self.layout(window.getXSize(),window.getYSize())

    def layout(self,width,height):
        if width <= 0 or height <= 0 or (width,height) == self.size:
            return
        self.size = (width,height)
        self.app.settings.width,self.app.settings.height = width,height
        ui_scale = self.app.args.ui_scale
        self.compact = height < 480*ui_scale or width < 700*ui_scale
        self.font = (16 if height < 500 else (17 if height < 800 else min(24,round(height/54))))*ui_scale
        self.font = min(self.font,max(14,height/20))
        margin = 12
        self.panel_width = min(width-2*margin,680*ui_scale)
        for node in (self.stats,self.location,self.controls):
            node.setScale(self.font)
            node.setWordwrap((self.panel_width-20)/self.font)
        self.title.setScale(self.font*1.2)
        self.title.setPos(margin+10,-margin-self.font*1.3)
        self.stats.setPos(margin+10,-margin-self.font*2.8)
        self.crosshair.setScale(20)
        self.crosshair.setPos(width/2,-height/2-5)
        self.notice.setScale(self.font)
        self.notice.setWordwrap(min(width-48,630)/self.font)
        self.notice.setPos(width/2,-height*.45)
        self.pause.setPos(width/2,0,-height/2)
        menu_width = min(400,width-32)
        menu_height = min(210,height-24)
        self.pause['frameSize'] = (-menu_width/2,menu_width/2,-menu_height/2,menu_height/2)
        self.pause_title.setScale(min(self.font*1.1,(menu_width-24)/15))
        self.pause_title.setPos(0,menu_height/2-40)
        for button,y in ((self.resume_button,5),(self.exit_button,-53)):
            button.setPos(0,0,y)
            button['frameSize'] = (-menu_width*.36,menu_width*.36,-19,23)
            button['text_scale'] = self.font*1.05
            button['text_pos'] = (0,-5)
        self.controls.setText('WASD mover | Mouse olhar | Shift correr\nEsc pausa | F1 painel' if self.compact else
                              'WASD mover | Mouse olhar | Shift correr | Espaco pular | Ctrl agachar\n'
                              'F1 painel | F5 arvores | F6 grama | F7 patos | F8 sombras | F9 registrar | Esc pausa')
        if hasattr(self,'last_update'):
            self.update(*self.last_update)
        self.refresh_panels()

    def refresh_panels(self):
        width,height = self.size
        margin = 12
        control_height = self.controls.textNode.getHeight()*self.font
        self.controls.setPos(margin+10,-height+margin+control_height)
        location_height = self.location.textNode.getHeight()*self.font
        self.location.setPos(margin+10,-height+margin+control_height+location_height+8)
        self.bottom_panel.setPos(margin,0,-height+margin)
        self.bottom_panel['frameSize'] = (0,self.panel_width,0,control_height+location_height+28)
        stats_height = self.stats.textNode.getHeight()*self.font
        self.top_panel.setPos(margin,0,-margin)
        self.top_panel['frameSize'] = (0,self.panel_width,-self.font*2.8-stats_height-6,0)
        notice_height = self.notice.textNode.getHeight()*self.font
        self.notice_panel.setPos(width/2,0,-height*.45)
        self.notice_panel['frameSize'] = (-min(width-24,650)/2,min(width-24,650)/2,-notice_height-8,self.font+8)

    def toggle_debug(self):
        self.debug = not self.debug
        for node in (self.stats,self.title,self.top_panel):
            node.show() if self.debug else node.hide()

    def destroy(self):
        self.ignoreAll()
        for text in (self.title,self.stats,self.location,self.controls,self.crosshair,self.notice,self.pause_title):
            text.destroy()
        for widget in (self.top_panel,self.bottom_panel,self.notice_panel,self.resume_button,self.exit_button,self.pause):
            widget.destroy()
        self.root.removeNode()

    def message(self,text):
        self.notice.setText(text)
        self.notice_until = self.app.elapsed+4
        self.notice_panel.show()
        self.refresh_panels()

    def update(self,frame_time,counts,scene,ram):
        self.last_update = (frame_time,counts,scene,ram)
        player,env = self.app.player,self.app.environment
        self.pause.show() if player.paused else self.pause.hide()
        self.crosshair.hide() if player.paused else self.crosshair.show()
        ram_text = f'{ram:.0f} MB' if ram is not None else 'indisponivel'
        if self.compact:
            text = (f'{1/max(frame_time,.00001):.0f} FPS | {frame_time*1000:.1f} ms\n'
                    f'Grama {counts["grass"]:,}\n'
                    f'Arvores {counts["trees"]:,} | Patos {counts["ducks"]}\n'
                    f'Chunks {counts["chunks"]} | Sombras {env.shadow_quality}')
        else:
            text = (f'{1/max(frame_time,.00001):.0f} FPS | {frame_time*1000:.1f} ms\n'
                    f'Chunks {counts["chunks"]} | ativos {counts["active_chunks"]} | gerando {counts["loading"]}\n'
                    f'Cache {counts["cached_chunks"]} | reutilizados {counts["cache_hits"]} | streaming {counts["stream_ms"]:.1f} ms\n'
                    f'Arvores {counts["trees"]:,} | grama {counts["grass"]:,} | pedras {counts["rocks"]:,}\n'
                    f'Patos {counts["active_ducks"]} ativos / {counts["ducks"]} total\n'
                    f'Geoms {scene.get("scene_geoms",0):,} | triangulos {scene.get("scene_triangles",0):,}\n'
                    f'RAM {ram_text} | sombras {env.shadow_quality}')
        self.stats.setText(text)
        self.location.setText(f'{self.app.terrain.biome(player.x,player.y).upper()} | {player.x:.0f}, {player.y:.0f} m' if self.compact else
                              f'SEED {self.app.settings.seed} | {self.app.terrain.biome(player.x,player.y).upper()} | {player.x:.0f}, {player.y:.0f} m')
        if self.app.elapsed > self.notice_until:
            self.notice.setText('')
            self.notice_panel.hide()
        self.refresh_panels()
