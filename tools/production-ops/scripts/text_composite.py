#!/usr/bin/env python3
"""Controlled text texture and planar compositing with explicit occlusion.

Input quadrilaterals/masks/pen tracks must come from real tracking or a deliberately
constructed shot. No automatic tracker is implied. Curved/deforming paper is
rejected by this planar path, not approximated and labeled correct.
"""
from __future__ import annotations
import hashlib
import math
from pathlib import Path


def make_texture(text:str,font_path:Path,font_size:int,canvas:tuple[int,int],*,fill=(0,0,0,255),spacing:int=4):
    from PIL import Image,ImageDraw,ImageFont
    from fontTools.ttLib import TTFont
    if not isinstance(text,str) or not text or not font_path.is_file():raise ValueError('exact nonempty text and local licensed font required')
    if type(font_size) is not int or font_size<=0 or len(canvas)!=2 or any(type(v) is not int or v<=0 for v in canvas):raise ValueError('valid font size/canvas required')
    font=TTFont(font_path,fontNumber=0);cmap=font.getBestCmap();font.close()
    missing={ord(c) for c in text if not c.isspace() and ord(c) not in cmap}
    if missing:raise ValueError('font has missing glyphs: '+','.join(f'U+{c:04X}' for c in sorted(missing)))
    im=Image.new('RGBA',canvas,(0,0,0,0));draw=ImageDraw.Draw(im);f=ImageFont.truetype(str(font_path),font_size)
    box=draw.multiline_textbbox((0,0),text,font=f,spacing=spacing)
    if box[2]-box[0]>canvas[0] or box[3]-box[1]>canvas[1]:raise ValueError('exact text does not fit approved canvas; do not shrink silently')
    draw.multiline_text((-box[0],-box[1]),text,font=f,fill=fill,spacing=spacing)
    return im,{'exact_text':text,'font_sha256':hashlib.sha256(font_path.read_bytes()).hexdigest(),'canvas':list(canvas),'font_size':font_size,'glyphs_verified':True,'media_quality_verified':False}


def planar_overlay(base,texture,quad,occlusion_mask,*,surface_model:str):
    import numpy as np
    from PIL import Image
    if surface_model!='plane':raise ValueError('curved/deforming surface requires a tested mesh/flow route')
    q=np.asarray(quad,dtype=float)
    if q.shape!=(4,2) or not np.isfinite(q).all():raise ValueError('four finite target corners required')
    edges=np.roll(q,-1,axis=0)-q
    cross=edges[:,0]*np.roll(edges[:,1],-1)-edges[:,1]*np.roll(edges[:,0],-1)
    if not ((cross>1e-8).all() or (cross<-1e-8).all()):raise ValueError('target quadrilateral must be convex and nondegenerate')
    if occlusion_mask is None or occlusion_mask.size!=base.size:raise ValueError('explicit full-frame occlusion mask required, including all-clear')
    # Inverse mapping: target pixels -> source texture. Source rect corners use
    # image edges, not assumed real-world measurements.
    w,h=texture.size;src=np.asarray([[0,0],[w,0],[w,h],[0,h]],float);A=[];B=[]
    for (x,y),(u,v) in zip(q,src):
        A.append([x,y,1,0,0,0,-u*x,-u*y]);B.append(u)
        A.append([0,0,0,x,y,1,-v*x,-v*y]);B.append(v)
    coefficients=np.linalg.solve(np.asarray(A),np.asarray(B))
    warped=texture.convert('RGBA').transform(base.size,Image.Transform.PERSPECTIVE,coefficients,Image.Resampling.BICUBIC)
    alpha=np.asarray(warped.getchannel('A'),dtype=np.float64)
    occ=np.asarray(occlusion_mask.convert('L'),dtype=np.float64)/255
    warped.putalpha(Image.fromarray(np.rint(alpha*(1-occ)).astype('uint8')))
    return Image.alpha_composite(base.convert('RGBA'),warped)


def stroke_reveal(texture,points,pen_tip,*,width_px:float,tip_tolerance_px:float,previous_mask=None,complete:bool=False):
    from PIL import Image,ImageDraw
    import numpy as np
    if not points or any(len(p)!=2 or not all(type(x) in (float,int) and math.isfinite(x) for x in p) for p in points):raise ValueError('measured/authored finite pen path required')
    if not isinstance(pen_tip,(list,tuple)) or len(pen_tip)!=2 or any(type(v) not in (float,int) or not math.isfinite(v) for v in pen_tip):raise ValueError('actual finite pen tip required')
    if any(type(v) not in (float,int) or not math.isfinite(v) for v in (width_px,tip_tolerance_px)):raise ValueError('finite stroke width/tolerance required')
    if width_px<=0 or tip_tolerance_px<0:raise ValueError('approved positive stroke width and tolerance required')
    if math.dist(points[-1],pen_tip)>tip_tolerance_px:raise ValueError('new ink path detached from actual pen tip')
    mask=previous_mask.copy() if previous_mask is not None else Image.new('L',texture.size,0)
    if mask.size!=texture.size:raise ValueError('stroke history has wrong texture coordinates')
    draw=ImageDraw.Draw(mask)
    if len(points)==1:
        x,y=points[0];r=width_px/2;draw.ellipse((x-r,y-r,x+r,y+r),fill=255)
    else:draw.line([tuple(p) for p in points],fill=255,width=max(1,round(width_px)),joint='curve')
    original=np.asarray(texture.convert('RGBA').getchannel('A'))
    ink=np.minimum(original,np.asarray(mask))
    if complete and (ink<original).any():raise ValueError('writing not complete: glyph pixels still unrevealed; no final-text pop-in permitted')
    result=texture.convert('RGBA').copy();result.putalpha(Image.fromarray(ink.astype('uint8')))
    return result,mask
