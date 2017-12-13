#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# KicadModTree is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# KicadModTree is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with kicad-footprint-generator. If not, see < http://www.gnu.org/licenses/ >.
#
# (C) 2016 by Thomas Pointhuber, <thomas.pointhuber@gmx.at>

import attr
import sys
import os
import collections
from numbers import Number
import copy
#sys.path.append(os.path.join(sys.path[0],"..","..","kicad_mod")) # load kicad_mod path

# export PYTHONPATH="${PYTHONPATH}<path to kicad-footprint-generator directory>"
sys.path.append(os.path.join(sys.path[0], "..", "..", ".."))  # load parent path of KicadModTree
from math import sqrt, ceil
import argparse
import yaml
from KicadModTree import *

sys.path.append(os.path.join(sys.path[0], "..", "..", "tools"))  # load parent path of tools
from footprint_text_fields import addTextFields
from drawing_tools import bevelRectTL

global_config = {
        'series': '{positions}P{connected}C',
        'lib_name': 'Connector_RJ',
        'datasheet': 'http://www.molex.com/pdm_docs/sd/{mpn}{variant}_sd.pdf',
        'descr_format_string': '{series} Cat.{category} modular connector, right angle, {datasheet}',
        'fp_name_format_string': '{series}_{man}_{mpn}-{variant}',
        'keyword_fp_string': 'modular connector {man} {series} {mpn} Cat.{category} right angle {entry}',
    }

configs = [
        {
            'man': 'Molex',
            'mpn': '85502',
            'orientation': 'V',
            'category': 3,
            'pad': {
                'type': 'SMT',
                'pitch': [1.27, 0],
                'size': [.76, 6.35],
                'shape': 'rectangle',
                'position': [0, -21.38 + 6.35/2],
                },
            'mount': {
                'type': 'SMT',
                'size': [5.15, 2.80],
                'shape': 'rectangle',
                'position': ['pad_sep/2+5.15/2', -6.4-2.8/2],
            },
            'depth': 18.1,
            'center': [0, 8.5],
            'variants': [
                {
                    'number': 5005,
                    'positions': 4,
                    'connected': 4,
                    'width': 11.18,
                    'pad_sep': 6.94,
                },
                {
                    'number': 5006,
                    'positions': 6,
                    'connected': 4,
                    'width': 13.21,
                    'pad_sep': 8.97,
                },
                {
                    'number': 5007,
                    'positions': 6,
                    'connected': 6,
                    'width': 13.21,
                    'pad_sep': 8.97,
                },
                {
                    'number': 5008,
                    'positions': 8,
                    'connected': 8,
                    'width': 15.24,
                    'pad_sep': 8.89,
                },
            ],
        },
    ]

precision = 3

def recursive_dict_update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            d[k] = recursive_dict_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def process_yaml(v, base):
    if v.isdecimal():
        return int(v)
    if v.isnumeric():
        return round(float(v), precision)
    ns = v.format(**base)
    try:
        return round(eval(ns, None, base), precision)
    except Exception as e:
        return ns


def instantiate_strings(it, base=None):
    if not base:
        base = it

    if isinstance(it, dict):
        for k, v in it.items():
            if isinstance(v, str) and 'string' not in k:
                it[k] = process_yaml(v, base)
            else:
                instantiate_strings(v, base)
    elif isinstance(it, list):
        for i, v in enumerate(it):
            if isinstance(v, str):
                it[i] = process_yaml(v, base)
            else:
                instantiate_strings(v, base)
    elif isinstance(it, tuple):
        raise Exception('no tuples allowed (use list)')


def expand_config(series):
    if not 'variants' in series:
        series.update(global_config)
        instantiate_strings(series)
        return [series]
    out = []
    for name, variant in series['variants'].items():
        config = copy.deepcopy(series)
        config['variant'] = name
        config.update(global_config)
        recursive_dict_update(config, variant)
        instantiate_strings(config)
        out.append(config)
    return out


def set_pad_defaults(pad):
    if 'shape' not in pad:
        if pad['type'] == 'SMT':
            pad['shape'] = 'rectangular'
        else:
            pad['shape'] = 'circle'

    if 'size' not in pad:
        if pad['type'] == 'NPTH':
            pad['size'] = pad['drill']
        elif pad['type'] == 'THT':
            pad['size'] = pad['drill'] + 0.7 # IPC-2221 Level A


def mirror(point, ref):
    shifted = point - ref
    return ref + (-shifted.x, shifted.y)

def add_pad(kicad_mod, pos, args, **kwargs):
    myargs = {}
    myargs.update(args)
    myargs.update(kwargs)
    set_pad_defaults(myargs)

    opt_args = {}
    if 'number' in myargs:
        opt_args['number'] = myargs['number']
    if 'drill' in args:
        opt_args['drill'] = myargs['drill']

    kicad_mod.append(Pad(at=pos, type=types[myargs['type']],
        size=myargs['size'], shape=shapes[myargs['shape']],
        layers=layers[myargs['type']], **opt_args))
        

def add_pad_symmetric(kicad_mod, pos, ref, args):
    add_pad(kicad_mod, pos, args)
    add_pad(kicad_mod, mirror(pos, ref), args)

def build_base_footprint(config):
    # expand the orientation based on the KLC config
    config['entry'] = config['entry_direction'][config['orientation']]
    config['orientation'] = config['orientation_options'][config['orientation']]

    name = config['fp_name_format_string']
    config['footprint_name'] = name.format(**config)

    kicad_mod = Footprint(config['footprint_name'])
    kicad_mod.setDescription(config['descr_format_string'].format(**config))
    kicad_mod.setTags(config['keyword_fp_string'].format(**config))
    if config['pad']['type'] == 'SMT':
        kicad_mod.setAttribute('smd')

    return kicad_mod


def add_keepout(kicad_mod, center, x, y):
    return addRectangularKeepout(kicad_mod, center, (x,y))


shapes = dict(
        circle=Pad.SHAPE_CIRCLE,
        rectangle=Pad.SHAPE_RECT,
        rect=Pad.SHAPE_RECT,
        rectangular=Pad.SHAPE_RECT,
        oval=Pad.SHAPE_OVAL,
    )
types = dict(
        SMT=Pad.TYPE_SMT,
        THT=Pad.TYPE_THT,
        NPTH=Pad.TYPE_NPTH,
    )

layers = dict(
        SMT=Pad.LAYERS_SMT,
        THT=Pad.LAYERS_THT,
        NPTH=Pad.LAYERS_NPTH,
    )

def build_footprint(config):
    origin = Point(0, 0)
    pitch_x = config['pad']['pitch'][0]
    pitch_y = config['pad']['pitch'][1]

    if config['pad']['type'] == 'THT':
        ref = origin + (pitch_x * (config['connected'] - 1)/2,
                        config['pad']['position'])
        if (config['connected'] / 2 % 2 == 0):
            ref -= (0, pitch_y)
        pad_pos = origin
    else:
        if 'center' in config:
            ref = origin - config['center']
        else:
            ref = origin
        pad_pos = ref + (-pitch_x * (config['connected'] - 1) / 2,
                         -config['pad']['position'])
    front = ref + (0, config['mount']['position'])
    center = front - (0, config['depth'] / 2)

    housing_size = Point(config['width'], config['depth'])

    kicad_mod = build_base_footprint(config)

    # add pads
    for i in range(1, config['connected']+1):
        y = 0
        if i % 2 == 0:
            if config['connected'] / 2 % 2 == 0:
                y = -pitch_y
            else:
                y = pitch_y
        position = pad_pos + ((i-1) * pitch_x, y)
        if i == 1 and config['pad']['type'] == 'THT':
            add_pad(kicad_mod, position, config['pad'], number=str(i),
                    shape='rect')
        else:
            add_pad(kicad_mod, position, config['pad'], number=str(i))

    # add mounting positions
    mount_pos = ref - (config['mount']['separation']/2, 0)
    add_pad_symmetric(kicad_mod, mount_pos, center, config['mount'])

    # draw additional side markes (relative to left mounting hole position)
    if 'side' in config:
        for extra in config['side']:
            position = mount_pos + extra['position']
            if extra['type'] in types:
                add_pad_symmetric(kicad_mod, position, center, extra)
            else:
                raise Exception('type not implemented: {}'.format(extra['type']))

    kicad_mod.append(RectLine(start=center - housing_size/2,
                              end=center + housing_size/2, layer='F.Fab',
                              width=config['fab_line_width']))
    if config['pad']['type'] == 'THT':
        kicad_mod.append(RectLine(start=center - housing_size/2,
                                  end=center + housing_size/2, layer='F.SilkS',
                                  width=config['silk_line_width']))
    else:
        silk_pad_stop_x = pad_pos.x - 0.76/2 - config['silk_pad_clearance'] 
        points = [
                (silk_pad_stop_x, (center -housing_size / 2).y),
                center - housing_size / 2,
                center - housing_size / 2 + (0, housing_size.y),
                center + housing_size / 2,
                center + housing_size / 2 - (0, housing_size.y),
                (-silk_pad_stop_x, (center -housing_size / 2).y),
                ]
        kicad_mod.append(PolygoneLine(polygone=points, layer='F.SilkS',
                                      width=config['silk_line_width']))

    body_edges = dict(top=(center - housing_size/2).y,
                      left=(center - housing_size/2).x,
                      bottom=(center + housing_size/2).y,
                      right=(center + housing_size/2).x)

    courtyard_edges = {k: ceil(v / config['courtyard_grid']) * config['courtyard_grid']
                       for k, v in body_edges.items()}
    if config['pad']['type'] == 'SMT':
        courtyard_edges['top'] = ceil((pad_pos.y - config['pad']['size'][1]/2) /
                config['courtyard_grid']) * config['courtyard_grid']
    for k, v in courtyard_edges.items():
        if v > 0:
            courtyard_edges[k] += config['courtyard_offset']['connector']
        else:
            courtyard_edges[k] -= config['courtyard_offset']['connector']
    kicad_mod.append(RectLine(start=(courtyard_edges['left'],
                                     courtyard_edges['top']),
                              end=(courtyard_edges['right'],
                                   courtyard_edges['bottom']),
                              layer='F.CrtYd',
                              width=config['courtyard_line_width']))

    ######################### Text Fields ###############################
    addTextFields(kicad_mod, config, body_edges=body_edges,
            courtyard=courtyard_edges, fp_name=config['footprint_name'])

    ##################### Output and 3d model ############################
    config['model3d_path_prefix'] = configuration.get('3d_model_prefix','${KISYS3DMOD}/')

    lib_name = configuration['lib_name_format_string'].format(**config)
    model_name = '{model3d_path_prefix}{lib_name}.3dshapes/{footprint_name}.wrl'.format(**config)
    kicad_mod.append(Model(filename=model_name))

    config['outdir'] = '{lib_name:s}.pretty/'.format(**config)
    if not os.path.isdir(config['outdir']):
        os.makedirs(config['outdir'])
    filename = '{outdir:s}{footprint_name:s}.kicad_mod'.format(**config)

    file_handler = KicadFileHandler(kicad_mod)
    file_handler.writeFile(filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='use confing .yaml files to create footprints.')
    parser.add_argument('--global_config', type=str, nargs='?', help='the config file defining how the footprint will look like. (KLC)', default='../../tools/global_config_files/config_KLCv3.0.yaml')
    parser.add_argument('--series_config', type=str, nargs='?', help='the config file defining series parameters.', default='../conn_config_KLCv3.yaml')
    parser.add_argument('configuration', type=str, nargs='*')
    args = parser.parse_args()

    with open(args.global_config, 'r') as config_stream:
        try:
            configuration = yaml.load(config_stream)
        except yaml.YAMLError as exc:
            print(exc)

    with open(args.series_config, 'r') as config_stream:
        try:
            configuration.update(yaml.load(config_stream))
        except yaml.YAMLError as exc:
            print(exc)

    for path in args.configuration:
        with open(path, 'r') as f:
            try:
                configs = yaml.load(f)
            except yaml.YAMLError as exc:
                print(exc)
        for config in expand_config(configs):
            c = configuration.copy()
            c.update(config)
            print('building {man} {mpn}-{variant}'.format(**c))
            build_footprint(c)
