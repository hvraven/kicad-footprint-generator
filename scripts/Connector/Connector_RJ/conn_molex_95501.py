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
from collections import defaultdict
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

def build_base_footprint(args, config):
    # expand the orientation based on the KLC config
    args['entry'] = config['entry_direction'][args['orientation']]
    args['orientation'] = config['orientation_options'][args['orientation']]

    name = config['fp_name_format_string']
    args['footprint_name'] = name.format(**defaultdict(str, args)).replace("__", '_')

    kicad_mod = Footprint(args['footprint_name'])
    kicad_mod.setDescription(config['descr_format_string'].format(**args))
    kicad_mod.setTags(config['keyword_fp_string'].format(**args))
    if args['variant'] == 'SMT':
        kicad_mod.setAttribute('smd')

    return kicad_mod

def add_keepout(kicad_mod, center, x, y):
    return addRectangularKeepout(kicad_mod, center, (x,y))


def generate_one_footprint(config, **kwargs):
    args = dict(man='Molex',
                series='{}P{}C'.format(kwargs['positions'], kwargs['connected']),
                mpn='95501',
                orientation='V',
                lib_name='Connector_RJ',
                )
    args.update(kwargs)
    if args['variant'] == 'THT':
        args['datasheet'] = 'http://www.molex.com/pdm_docs/sd/955012441_sd.pdf'
    elif args['variant'] == 'SMT':
        args['datasheet'] = 'http://www.molex.com/pdm_docs/sd/955016449_sd.pdf'
    else:
        raise Exception('Unknown variant')

    config['keyword_fp_string'] = 'connector {man} {series} {mpn} Cat.3 right angle side entry'
    config['fp_name_format_string'] = '{series}_{man}_{mpn}_{variant}'
    config['descr_format_string'] = "{series} Cat.3 modular connector, right angle, {datasheet}"

    origin = Point(0, 0)
    if args['variant'] == 'THT':
        pitch_x = 1.27
        pitch_y = 8.89 - 6.35
        center = origin + (config['B'] / 2, 8.89 + 7.88 - 18.1 / 2)
        if (args['connected'] / 2 % 2 == 0):
            center -= (0, pitch_y)
        pad_settings = dict(layers=Pad.LAYERS_THT,
                            drill=0.90,
                            size=(1.5, 1.5))
        pad_type=Pad.TYPE_THT
        pad_shape=Pad.SHAPE_CIRCLE
        pad_pos = origin
    else:
        center = origin + (0, (13.4 - (18.1 - 7.88)) / 2)
        pitch_x = 1.27
        pitch_y = 0
        pad_settings = dict(layers=Pad.LAYERS_SMT,
                            size=(0.76, 6.35))
        pad_type=Pad.TYPE_SMT
        pad_shape=Pad.SHAPE_RECT
        pad_pos = center + (config['B'] / -2, 18.1/2 - 7.88 - 13.4 + 6.35/2)

    housing_size = Point(config['A'], 18.10)

    kicad_mod = build_base_footprint(args, config)

    for i in range(1, args['connected']+1):
        if i == 1 and pad_shape == Pad.SHAPE_CIRCLE:
            shape = Pad.SHAPE_RECT
        else:
            shape = pad_shape

        y = 0
        if i % 2 == 0:
            if args['connected'] / 2 % 2 == 0:
                y = -pitch_y
            else:
                y = pitch_y
        position = pad_pos + ((i-1) * pitch_x, y)
        kicad_mod.append(Pad(number=i, at=position, shape=shape,
            type=pad_type, **pad_settings))

    mounting_hole_position = center + (config['C'] / -2, 18.1/2 - 7.88)
    kicad_mod.append(Pad(at=mounting_hole_position, shape=Pad.SHAPE_CIRCLE,
        type=Pad.TYPE_NPTH, drill=3.25, size=3.25, layers=Pad.LAYERS_NPTH))
    kicad_mod.append(Pad(at=mounting_hole_position + (config['C'], 0),
        shape=Pad.SHAPE_CIRCLE,
        type=Pad.TYPE_NPTH, drill=3.25, size=3.25, layers=Pad.LAYERS_NPTH))

    kicad_mod.append(RectLine(start=center - housing_size/2,
                              end=center + housing_size/2, layer='F.Fab',
                              width=config['fab_line_width']))
    if args['variant'] == 'THT':
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
    if args['variant'] == 'SMT':
        courtyard_edges['top'] = ceil((pad_pos.y - pad_settings['size'][1]/2) /
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
            courtyard=courtyard_edges, fp_name=args['footprint_name'])

    ##################### Output and 3d model ############################
    args['model3d_path_prefix'] = configuration.get('3d_model_prefix','${KISYS3DMOD}/')

    lib_name = configuration['lib_name_format_string'].format(**args)
    model_name = '{model3d_path_prefix:s}{lib_name:s}.3dshapes/{footprint_name:s}.wrl'.format(**args)
    kicad_mod.append(Model(filename=model_name))

    config['outdir'] = '{lib_name:s}.pretty/'.format(**args)
    if not os.path.isdir(config['outdir']):
        os.makedirs(config['outdir'])
    filename = '{outdir:s}{footprint_name:s}.kicad_mod'.format(**config, **args)

    file_handler = KicadFileHandler(kicad_mod)
    file_handler.writeFile(filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='use confing .yaml files to create footprints.')
    parser.add_argument('--global_config', type=str, nargs='?', help='the config file defining how the footprint will look like. (KLC)', default='../../tools/global_config_files/config_KLCv3.0.yaml')
    parser.add_argument('--series_config', type=str, nargs='?', help='the config file defining series parameters.', default='../conn_config_KLCv3.yaml')
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

    configuration['A'] = 11.18
    configuration['B'] = 3.81
    configuration['C'] = 7.62
    variants={
            (4,4): dict(A=11.18, B=3.81, C=7.62),
            (6,4): dict(A=13.21, B=3.81, C=10.16),
            (6,6): dict(A=13.21, B=6.35, C=10.16),
            (8,8): dict(A=15.24, B=8.89, C=11.43),
        }

    for (p, c), conf in variants.items():
        configuration.update(conf)
        generate_one_footprint(positions=p, connected=c, variant='THT', config=configuration)
        generate_one_footprint(positions=p, connected=c, variant='SMT', config=configuration)
