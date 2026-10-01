#!/usr/bin/env python3
"""Declared geometry, approved tolerances and time adapters, NOT inferred 3-D.

All frame ranges returned by this module are left-closed/right-open. Historical
closed sampling ranges MUST be converted, not silently reinterpreted.
"""
from __future__ import annotations
import math
from typing import Any


def finite(x: Any) -> bool:
    return type(x) in (float, int) and math.isfinite(x)


def equal_value(expected: Any, observed: Any, tolerance: dict | None = None) -> bool:
    if tolerance is not None:
        if (not isinstance(tolerance, dict) or tolerance.get('mode') != 'absolute'
            or not finite(tolerance.get('max_error')) or tolerance['max_error'] < 0
            or not isinstance(tolerance.get('unit'), str) or not tolerance['unit'].strip()
            or not isinstance(tolerance.get('reference_frame'), str) or not tolerance['reference_frame'].strip()):
            raise ValueError('explicit approved absolute tolerance/unit/reference frame required')
        if not finite(expected) or not finite(observed): raise ValueError('tolerance only applies to finite measured numbers')
        return abs(expected-observed) <= tolerance['max_error']
    if type(expected) is not type(observed): return False
    if isinstance(expected, dict):
        return expected.keys() == observed.keys() and all(equal_value(v, observed[k]) for k,v in expected.items())
    if isinstance(expected, list): return len(expected) == len(observed) and all(equal_value(a,b) for a,b in zip(expected,observed))
    if isinstance(expected, float) and not finite(expected): return False
    return expected == observed


def half_open(start: int, end: int, convention: str, total_frames: int | None = None) -> tuple[int,int]:
    if type(start) is not int or type(end) is not int or start < 0: raise ValueError('integer frame indices required')
    if convention == 'closed': end += 1
    elif convention != 'half_open': raise ValueError('source interval convention required')
    if end <= start or (total_frames is not None and (type(total_frames) is not int or end > total_frames)):
        raise ValueError('frame interval empty or outside media')
    return start, end


def frame_from_time(seconds_num: int, seconds_den: int, fps_num: int, fps_den: int, rounding: str = 'floor') -> int:
    """Exact rational CFR arithmetic; not a VFR/retime mapping."""
    if any(type(v) is not int for v in (seconds_num,seconds_den,fps_num,fps_den)) or seconds_num < 0 or min(seconds_den,fps_num,fps_den) <= 0:
        raise ValueError('nonnegative rational time and positive rational CFR required')
    n,d = seconds_num*fps_num, seconds_den*fps_den
    if rounding == 'floor': return n//d
    if rounding == 'ceil': return (n+d-1)//d
    raise ValueError('explicit floor/ceil required')


def _v3(v):
    if not isinstance(v,(list,tuple)) or len(v)!=3 or not all(finite(x) for x in v): raise ValueError('finite xyz required')
    return tuple(float(x) for x in v)


def _sub(a,b): return tuple(x-y for x,y in zip(a,b))
def _dot(a,b): return sum(x*y for x,y in zip(a,b))
def _cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _unit(v):
    n=math.sqrt(_dot(v,v))
    if n<1e-10: raise ValueError('degenerate camera axes')
    return tuple(x/n for x in v)


def project_point(point, camera: dict) -> dict:
    """Pinhole projection of AUTHORED geometry; does not infer occlusion/lens distortion."""
    p=_v3(point);eye=_v3(camera['position']);target=_v3(camera['target']);up=_unit(_v3(camera.get('up',[0,0,1])))
    w,h=camera['width'],camera['height'];fov=camera['vertical_fov_deg']
    if type(w) is not int or type(h) is not int or min(w,h)<=0 or not finite(fov) or not 0<fov<179:
        raise ValueError('positive integer raster and valid vertical field of view required')
    fwd=_unit(_sub(target,eye));right=_unit(_cross(fwd,up));vertical=_cross(right,fwd)
    delta=_sub(p,eye);depth=_dot(delta,fwd)
    if depth <= 0: return {'projectable':False,'reason':'behind camera','occlusion_checked':False}
    focal=h/(2*math.tan(math.radians(fov)/2))
    x=w/2+focal*_dot(delta,right)/depth;y=h/2-focal*_dot(delta,vertical)/depth
    return {'projectable':True,'x':x,'y':y,'depth':depth,'within_frame':0<=x<w and 0<=y<h,'occlusion_checked':False}


def projected_heading(tail, nose, camera: dict, edge_on_threshold_px: float) -> str:
    if not finite(edge_on_threshold_px) or edge_on_threshold_px<0: raise ValueError('explicit finite projection tolerance required')
    a,b=project_point(tail,camera),project_point(nose,camera)
    if not a['projectable'] or not b['projectable']: return 'unobservable'
    dx=b['x']-a['x']
    return 'edge_on' if abs(dx)<=edge_on_threshold_px else ('right' if dx>0 else 'left')
