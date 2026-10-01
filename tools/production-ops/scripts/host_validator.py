#!/usr/bin/env python3
"""Registered video preflight: current compiler + actual gates + exact native map.

The resolver and native builder are installed trusted functions, not commands or
code supplied in a return capsule. This class does not authenticate observations;
the host must protect reviewer records and calibrate the actual media reviewers.
"""
from pathlib import Path
import sys
from brain_handoff import digest, request_snapshot
from production_gates import gate


class BoundProductionValidator:
    def __init__(self,root:Path,resolve_inputs,native_builder):
        self.root=Path(root).resolve(strict=True)
        self.resolve_inputs=resolve_inputs;self.native_builder=native_builder
    def __call__(self,task:dict,native:dict)->dict:
        # resolve_inputs reads CURRENT scene/shot/profile/spec/reports, not a prior PASS.
        inputs=self.resolve_inputs(task)
        if not isinstance(inputs,dict):raise ValueError('trusted project resolver returned no current inputs')
        scene,shot,profile=(inputs[k] for k in ('scene','shot','runtime_profile'))
        if shot.get('policy_version')!='4.2.0':raise ValueError('host refuses legacy generation contract')
        visual=Path(__file__).resolve().parents[2]/'visual-continuity-prompter/scripts'
        if str(visual) not in sys.path:sys.path.insert(0,str(visual))
        from continuity_tools import compile_package
        compiled=compile_package(scene,shot,profile,self.root,production=True)
        if compiled.get('status')!='READY':raise ValueError('current generation compiler not ready')
        if request_snapshot(scene,shot,profile,compiled['prompt'])!=task['request']:
            raise ValueError('resolved inputs do not match approved request')
        expected=self.native_builder(task,inputs)
        if digest(expected)!=digest(native):raise ValueError('native API payload differs from registered exact mapping')
        spec=inputs['gate_spec']
        if spec.get('policy_version')!='4.2.0':raise ValueError('current production gate must use 4.2')
        required_action={'video':'pre_video'}.get(task['request'].get('kind'))
        if required_action is None or spec.get('action')!=required_action:
            raise ValueError('this validator supports video/pre_video only; register and test an explicit input validator for other generation modes')
        result=gate(spec,inputs['gate_reports'],self.root)
        if result.get('status')!='ACCEPTED':raise ValueError('current media/capability gate did not accept')
        return {'status':'PASS','brain_request_sha256':task['request_sha256'],
                'native_request_sha256':digest(native),'gate_snapshot_sha256':result['snapshot_sha256'],
                'scope':'Bound current compiler, reports and native mapping; not independent semantic inference.'}
