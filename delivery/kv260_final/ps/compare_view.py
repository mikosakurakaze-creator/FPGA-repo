import gi,math
gi.require_version('Gtk','3.0');gi.require_foreign('cairo')
from gi.repository import Gtk,Gdk,GdkPixbuf
class CompareView(Gtk.DrawingArea):
 def __init__(self):
  super().__init__();self.set_size_request(320,250);self.set_hexpand(True);self.set_vexpand(True);self.set_can_focus(True);self.ratio=.5;self.dragging=False;self.pix=[];self.paths=None;self.overlays=[];self.show_overlays=True;self.rect=(0,0,1,1)
  self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.KEY_PRESS_MASK)
  self.connect('draw',self.draw);self.connect('button-press-event',self.press);self.connect('button-release-event',self.release);self.connect('motion-notify-event',self.move);self.connect('key-press-event',self.key)
 def load(self,paths):
  if getattr(self,'live',False):self.queue_draw();return
  key=tuple(str(p) if p else '' for p in paths)
  if key!=self.paths:
   self.paths=key;self.pix=[GdkPixbuf.Pixbuf.new_from_file(p) if p else None for p in key]
   if self.pix[0] and self.pix[1] and (self.pix[0].get_width(),self.pix[0].get_height())!=(self.pix[1].get_width(),self.pix[1].get_height()):raise ValueError('对比图尺寸不一致')
  self.queue_draw()
 def position(self,x):
  left,top,w,h=self.rect;self.ratio=max(0.,min(1.,(x-left)/w));self.queue_draw()
 def press(self,w,e):
  if e.button!=1:return False
  self.grab_focus()
  if e.type==Gdk.EventType.DOUBLE_BUTTON_PRESS:self.ratio=.5;self.queue_draw();return True
  self.dragging=True;self.position(e.x);return True
 def release(self,w,e):
  if e.button==1:self.dragging=False;return True
  return False
 def move(self,w,e):
  if self.dragging:self.position(e.x)
  return True
 def key(self,w,e):
  if e.keyval==Gdk.KEY_Left:self.ratio=max(0,self.ratio-.02)
  elif e.keyval==Gdk.KEY_Right:self.ratio=min(1,self.ratio+.02)
  elif e.keyval==Gdk.KEY_Home:self.ratio=0
  elif e.keyval==Gdk.KEY_End:self.ratio=1
  else:return False
  self.queue_draw();return True
 def draw(self,widget,cr):
  width=self.get_allocated_width();height=self.get_allocated_height();cr.set_source_rgb(.08,.11,.15);cr.paint()
  if not self.pix or self.pix[0] is None:return False
  original=self.pix[0];result=self.pix[1] or original;iw,ih=original.get_width(),original.get_height();scale=min(width/iw,height/ih);w,h=iw*scale,ih*scale;x,y=(width-w)/2,(height-h)/2;self.rect=(x,y,w,h);split=x+w*self.ratio
  for image,left,right in [(original,x,split),(result,split,x+w)]:
   cr.save();cr.rectangle(left,y,max(0,right-left),h);cr.clip();cr.translate(x,y);cr.scale(scale,scale);Gdk.cairo_set_source_pixbuf(cr,image,0,0);cr.paint();cr.restore()
  if self.show_overlays and self.overlays:
   cr.save();cr.rectangle(split,y,x+w-split,h);cr.clip();cr.translate(x,y);cr.scale(scale,scale);cr.set_line_width(2/scale);cr.set_font_size(12/scale)
   for row in self.overlays:
    x0,y0,x1,y1=row['box'];cr.set_source_rgb(1,.62,.18);cr.rectangle(x0,y0,max(0,x1-x0),max(0,y1-y0));cr.stroke();cr.move_to(x0,max(14/scale,y0-3/scale));cr.show_text('vehicle %.2f'%row['score'])
   cr.restore()
  cr.set_source_rgba(0,0,0,.6);cr.set_line_width(5);cr.move_to(split,y);cr.line_to(split,y+h);cr.stroke();cr.set_source_rgb(1,1,1);cr.set_line_width(2);cr.move_to(split,y);cr.line_to(split,y+h);cr.stroke()
  cy=y+h/2;cr.arc(split,cy,17,0,2*math.pi);cr.set_source_rgb(.1,.32,.48);cr.fill_preserve();cr.set_source_rgb(1,1,1);cr.set_line_width(2);cr.stroke()
  for sign in [-1,1]:
   cr.move_to(split+sign*4,cy-5);cr.line_to(split+sign*9,cy);cr.line_to(split+sign*4,cy+5);cr.stroke()
  return False
