"""Event Horizon: a procedural Spaceagon odyssey, rendered live on the badge."""
import app
import asyncio
import json
import time

from events.input import Buttons
from frontboards.common import FRONTBOARD_BUTTON_TYPES
from system.eventbus import eventbus
from system.patterndisplay.events import PatternDisable
from tildagonos import tildagonos

from . import fx_cosmos, fx_geometry, swarm_fx
from .swarm import Swarm
from .ble_link import NearbyRadio
from .chrome import title, text, overlay, iris_radius
from .show import Show, SCENES, light_frame, finite
from .expansions import ExpansionManager
from .lights import DemoMatrix, write_eeh
from .space_inputs import SpaceInputs

VERSION = "0.2.1"
DEFAULTS = {"ring_brightness":.15,"eeh_brightness":.03,"matrix_brightness":.12,
            "quality":.9,"adaptive_quality":True,"space_tilt":True,
            "space_touch":True,"space_joystick":True,"space_proximity":False,"swarm_enabled":True}


def load_config():
    result = dict(DEFAULTS)
    try:
        folder=__file__.replace("\\","/").rsplit("/",1)[0]
        with open(folder+"/config.json") as handle:
            value=json.load(handle)
        if isinstance(value,dict):
            result.update(value)
    except (OSError,ValueError):
        pass
    try:
        import settings
        for key in ("ring_brightness","eeh_brightness","matrix_brightness","quality"):
            fallback=result[key]
            if key in ("ring_brightness","eeh_brightness"):
                fallback=settings.get("threecx_monitor."+key,fallback)
            value=settings.get("event_horizon."+key,fallback)
            result[key]=max(0,min(1,float(value)))
        result["space_tilt"]=settings.get("event_horizon.space_tilt",result["space_tilt"]) is True
        result["swarm_enabled"]=settings.get("event_horizon.swarm_enabled",result["swarm_enabled"]) is True
    except (ImportError,OSError,ValueError,TypeError):
        pass
    for key in ("ring_brightness","eeh_brightness","matrix_brightness","quality"):
        value=result.get(key)
        result[key]=max(0,min(1,value)) if finite(value) else DEFAULTS[key]
    return result


class EventHorizon(app.App):
    def __init__(self):
        super().__init__()
        self.config=load_config()
        self.buttons=Buttons(self)
        self.show=Show()
        self.clock_ms=0
        self._ticks=time.ticks_ms()
        self._held=set()
        self._physical_ready=False
        self._suppressed_physical=set()
        self._hold_a=None
        self._stopping=False
        self._settings=False
        self._setting_row=0
        self._dirty=False
        self._hud=False
        self._quality=max(0,min(1,float(self.config.get("quality",.9))))
        self._slow=0
        self._last_lights=-1000
        self._last_ring=None
        self._frame_count=0
        self._fps_at=0
        self.metrics={"fps":0,"draw_ms":0}
        self.expansions=ExpansionManager(self,self.config)
        self.space=SpaceInputs(self,self.config,clock=lambda:self.clock_ms)
        matrix_config={"matrix":{"brightness":self.config["matrix_brightness"]}}
        self.matrix=DemoMatrix(matrix_config,backend=self.expansions.backend)
        self.swarm=Swarm()
        self.radio=NearbyRadio(self,enabled=self.config.get("swarm_enabled") is True)
        self._last_beacon=-1000
        self._next_radio_open=0
        self._link_live=False
        self._swarm_view=self.swarm.view(self._local_frame(),0)
        eventbus.emit(PatternDisable())
        tildagonos.set_led_power(True)

    def _now(self):
        now=time.ticks_ms()
        delta=max(0,time.ticks_diff(now,self._ticks))
        self._ticks=now
        self.clock_ms+=delta
        self.show.advance(delta)
        return self.clock_ms

    def _save(self):
        if not self._dirty:
            return
        try:
            import settings
            for key in ("ring_brightness","eeh_brightness","matrix_brightness","quality","space_tilt","swarm_enabled"):
                settings.set("event_horizon."+key,self.config[key])
            settings.save()
        except (ImportError,OSError,ValueError):
            pass
        self._dirty=False

    def _local_frame(self):
        frame=self.show.frame()
        frame["paused"]=self.show.paused
        return frame

    def _frame(self):
        frame=self._local_frame()
        view=self._swarm_view
        if view.get("count",0):
            frame["pulse"]=view["pulse"]
            frame["beat"]=view["phase"]
            frame["swarm_colour"]=view["colour"]
            frame["swarm_count"]=view["count"]
        return frame

    def _burst(self):
        self.show.burst()
        self.swarm.burst(self.clock_ms)

    def _link_tick(self,now):
        enabled=(self.config.get("swarm_enabled") is True and getattr(self,"_focused",True) and not self._stopping)
        if not enabled:
            if self.radio.enabled:
                self.radio.set_enabled(False)
            if self._link_live:
                self.swarm.clear()
            self._link_live=False
            self._swarm_view=self.swarm.view(self._local_frame(),now)
            return now
        if not self.radio.running and now>=self._next_radio_open:
            self.radio.set_enabled(True)
            self._next_radio_open=now+2000
        self._link_live=self.radio.running
        if self._link_live:
            if now-self._last_beacon>=500:
                self.radio.send(self.swarm.packet(self._local_frame(),now),now)
                self._last_beacon=now
            packets=self.radio.poll()
            # Include time spent in the transport before accepting peers,
            # rendering or writing the light layers.
            now=self._now()
            for payload,rssi in packets[:16]:
                self.swarm.receive(payload,now,rssi)
            if self.swarm.consume_burst(now):
                # Echo visually without advancing the outbound event counter.
                self.show.burst()
        self._swarm_view=self.swarm.view(self._local_frame(),now)
        return now

    def _setting_key(self,key):
        if key in ("C","F","ENTER","SPACE","S","ESCAPE"):
            self._settings=False
            self._save()
            return
        if key in ("A","UP"):
            self._setting_row=(self._setting_row-1)%6
        elif key in ("D","DOWN"):
            self._setting_row=(self._setting_row+1)%6
        elif key in ("B","E","LEFT","RIGHT"):
            direction=1 if key in ("B","RIGHT") else -1
            field=("ring_brightness","eeh_brightness","matrix_brightness","quality","space_tilt","swarm_enabled")[self._setting_row]
            if field in ("space_tilt","swarm_enabled"):
                self.config[field]=not self.config[field]
                if field=="space_tilt":self.space.config[field]=self.config[field]
                else:
                    self.radio.set_enabled(self.config[field])
                    self.swarm.clear()
                    self._last_beacon=-1000
            else:
                self.config[field]=round(max(0,min(1,self.config[field]+direction*.01)),2)
                if field=="quality":self._quality=self.config[field]
            self._dirty=True

    def _key(self,key):
        if self._settings:
            self._setting_key(key)
            return
        if key in ("F","ESCAPE"):
            self._stop()
        elif key in ("B","RIGHT"):
            self.show.next(1)
        elif key in ("E","LEFT"):
            self.show.next(-1)
        elif key in ("C","ENTER","SPACE"):
            self.show.toggle()
        elif key in ("A","UP"):
            self._burst()
        elif key in ("D","DOWN","H"):
            self._hud=not self._hud
        elif key=="S":
            self._settings=True
        elif key=="T":
            self.config["space_tilt"]=not self.config["space_tilt"]
            self.space.config["space_tilt"]=self.config["space_tilt"]
            self._dirty=True

    def update(self,delta):
        if self._stopping:return False
        now=self._now()
        self.expansions.refresh(now)
        self.space.update()
        down={key for key,button in FRONTBOARD_BUTTON_TYPES.items() if self.buttons.get(button)}
        if not self._physical_ready:
            self._suppressed_physical=set(down)
            self._physical_ready=True
        self._suppressed_physical.intersection_update(down)
        edges=[key for key in "ABCDEF" if key in down and key not in self._held and key not in self._suppressed_physical]
        released_a="A" in self._held and "A" not in down
        self._held=down
        if self._settings:
            for key in edges+self.expansions.pop_keys():self._setting_key(key)
        else:
            if "A" in edges:self._hold_a=now
            if self._hold_a is not None:
                if "A" in down and now-self._hold_a>=850:
                    self._settings=True
                    self._hold_a=None
                elif released_a:
                    self._burst()
                    self._hold_a=None
            for key in edges:
                if key!="A":self._key(key)
            for key in self.expansions.pop_keys():self._key(key)
        for event in self.space.pop():
            kind,action=event.get("kind"),event.get("action")
            if kind=="joystick":
                key={"up":"UP","down":"DOWN","left":"LEFT","right":"RIGHT","confirm":"ENTER"}.get(action)
                if key:self._key(key)
            elif kind=="touch" and not self._settings:
                if action=="rotate":self.show.next(event.get("delta",1))
                elif action=="select":self.show.select((max(1,event.get("pad",1))-1)*len(SCENES)//12)
            elif kind=="proximity" and not self._settings:self._burst()
        if self._stopping:return False
        now=self._link_tick(now)
        if now-self._last_lights>=40:
            self._write_lights()
            self._last_lights=now
        return not self._stopping

    def _write_lights(self,dark=False):
        frame=self._frame()
        ring=[(0,0,0)]*12 if dark else light_frame(frame,self.config["ring_brightness"])
        if ring!=self._last_ring:
            for index,colour in enumerate(ring):tildagonos.leds[index+1]=colour
            tildagonos.leds.write()
            self._last_ring=ring
        write_eeh(self.expansions,frame,self.config["eeh_brightness"],dark)
        self.matrix.queue(frame,self.config["matrix_brightness"],dark)

    async def background_task(self):
        try:
            while not self._stopping:
                if not getattr(self,"_focused",True) and self.radio.enabled:
                    self.radio.set_enabled(False)
                    self.swarm.clear()
                    self._link_live=False
                await self.matrix.flush()
                await asyncio.sleep(.04)
        finally:
            self.radio.close()
            if not self._stopping:
                self._stopping=True
                self.matrix.close()
                self.space.close()
                self.expansions.close()
                self._dark_ring()
                self.terminate(restore_pattern=True)

    def _dark_ring(self):
        try:
            for index in range(1,13):tildagonos.leds[index]=(0,0,0)
            tildagonos.leds.write()
            self._last_ring=[(0,0,0)]*12
        except Exception:
            pass

    def _stop(self):
        if self._stopping:return
        self._stopping=True
        for operation in (self.radio.close,self._save,self.space.close):
            try:operation()
            except Exception:pass
        self._dark_ring()
        frame=self._frame()
        for operation in (lambda:write_eeh(self.expansions,frame,self.config["eeh_brightness"],True),
                          lambda:self.matrix.queue(frame,self.config["matrix_brightness"],True)):
            try:operation()
            except Exception:pass
        try:self.expansions.close()
        except Exception:pass
        asyncio.create_task(self._finish_stop())

    async def _finish_stop(self):
        # Give a healthy matrix a short opportunity to display the queued
        # blank frame. Each write still uses the bounded, ownership-checked
        # driver; shutdown never waits indefinitely for an absent board.
        try:
            started=time.ticks_ms()
            while self.matrix.pending and time.ticks_diff(time.ticks_ms(),started)<900:
                if not await self.matrix.flush():break
                await asyncio.sleep(0)
        finally:
            try:self.matrix.close()
            finally:self.terminate(restore_pattern=True)

    def _draw_settings(self,ctx):
        ctx.rgb(.005,.012,.03).rectangle(-120,-120,240,240).fill()
        text(ctx,"MISSION SETTINGS",-78,19,185)
        rows=(("RING",self.config["ring_brightness"]),("EEH",self.config["eeh_brightness"]),
              ("MATRIX",self.config["matrix_brightness"]),("DETAIL",self.config["quality"]),
              ("TILT",self.config["space_tilt"]),("NEARBY",self.config["swarm_enabled"]))
        start=max(0,self._setting_row-1)
        for index in range(start,min(6,start+2)):
            y=-25+(index-start)*61
            colour=(.2,.88,1) if index==self._setting_row else (.30,.45,.59)
            ctx.rgb(.018,.05,.09).round_rectangle(-98,y-24,196,54,10).fill()
            if index==self._setting_row:
                ctx.line_width=1
                ctx.rgb(*colour).round_rectangle(-98,y-24,196,54,10).stroke()
            label,value=rows[index]
            text(ctx,label,y-8,13,90,colour,x=-42)
            text(ctx,("ON" if value else "OFF") if index>=4 else "%d%%"%round(value*100),y+2,31,100,colour,x=43)
        text(ctx,"UP/DOWN / LEFT/RIGHT",84,11,180,(.5,.67,.78))
        text(ctx,"C / ENTER: DONE",101,10,160,(.5,.67,.78))

    def draw(self,ctx):
        started=time.ticks_us()
        frame=self._frame()
        ctx.save()
        try:
            ctx.text_align=ctx.CENTER
            ctx.text_baseline=ctx.MIDDLE
            if self._settings:
                self._draw_settings(ctx)
            elif frame["scene"] in ("intro","finale"):
                title(ctx,frame,frame["scene"]=="finale")
                swarm_fx.draw(ctx,frame,self._swarm_view,self.clock_ms,self._quality)
                overlay(ctx,frame,self._hud,self.show.paused,self.metrics)
            else:
                ctx.save()
                try:
                    radius=iris_radius(frame)
                    if radius is not None:
                        ctx.rgb(.002,.004,.014).rectangle(-120,-120,240,240).fill()
                        ctx.arc(0,0,radius,0,6.283185307,False).clip()
                    tilt=self.space.tilt if self.config.get("space_tilt") else (0,0)
                    ctx.translate(tilt[0]*14,tilt[1]*14)
                    fx_cosmos.set_view(tilt[0], tilt[1])
                    # Scene time continues while its progress drives score energy.
                    energy=.25+frame["phase"]*.5+frame["pulse"]*.18+frame["burst"]*.07
                    if frame["scene"]=="swarm":
                        swarm_fx.draw(ctx,frame,self._swarm_view,self.clock_ms,self._quality)
                    elif not fx_cosmos.render(ctx,frame["scene"],frame["time_ms"],energy,self._quality):
                        fx_geometry.render(ctx,frame["scene"],frame["time_ms"],energy,self._quality)
                    if frame["scene"]!="swarm":
                        swarm_fx.draw(ctx,frame,self._swarm_view,self.clock_ms,self._quality)
                finally:
                    ctx.restore()
                overlay(ctx,frame,self._hud,self.show.paused,self.metrics)
            if not self._settings and (self._hud or frame["scene"]=="swarm"):
                channel=getattr(self.radio,"channel",None)
                band="CH %d"%channel if type(channel) is int else "CH ?"
                label=("%d NEARBY / %s"%(self._swarm_view["count"],band)
                       if self._swarm_view["count"] else "SEARCHING / "+band if self.radio.running else self.radio.status)
                if frame["scene"]=="swarm":
                    ctx.rgb(.003,.010,.024).round_rectangle(-70,76,140,17,7).fill()
                text(ctx,label,frame["scene"]=="swarm" and 84 or -73,10,160,(.4,.8,.92))
                if frame["scene"]=="swarm":
                    text(ctx,self._swarm_view["role"].upper(),97,8,120,(.3,.56,.67),minimum=8)
        finally:
            ctx.restore()
        elapsed=max(0,time.ticks_diff(time.ticks_us(),started))/1000
        self.metrics["draw_ms"]=round(elapsed)
        self._frame_count+=1
        if self.clock_ms-self._fps_at>=1000:
            self.metrics["fps"]=round(self._frame_count*1000/max(1,self.clock_ms-self._fps_at))
            self._frame_count=0
            self._fps_at=self.clock_ms
            if self.config.get("adaptive_quality",True) and not self._settings:
                ceiling=self.config["quality"]
                if elapsed>65:self._quality=max(min(.25,ceiling),min(ceiling,self._quality)-.15)
                elif elapsed<35:self._quality=min(ceiling,self._quality+.05)


__app_export__=EventHorizon
