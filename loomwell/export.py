#!/usr/bin/env python3
"""Export Loomwell's original editable vector templates through VectorCraft.

Python standard library only. No network, model API, or Atlas import is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)


def read_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(str(path) + ' must contain a JSON object')
    return value


def find_cli(explicit):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError('VectorCraft CLI not found: ' + str(path))
        return str(path)
    candidates = [REPO / 'target' / 'release' / 'vectorcraft-cli']
    # This is a convenience for the maintained local Loomwell checkout, not a dependency.
    for ancestor in REPO.parents:
        candidates.append(ancestor / 'build' / 'vectorcraft' / 'release' / 'vectorcraft-cli')
    for path in candidates:
        if path.is_file():
            return str(path)
    installed = shutil.which('vectorcraft-cli')
    if installed:
        return installed
    raise ValueError('Pass --cli /path/to/vectorcraft-cli or build target/release/vectorcraft-cli first.')


def node(parent, tag, attrs=None, text=None):
    result = ET.SubElement(parent, '{' + NS + '}' + tag, {k: str(v) for k, v in (attrs or {}).items()})
    if text is not None:
        result.text = text
    return result


def rect(svg, x, y, width, height, fill, radius=0):
    return node(svg, 'rect', dict(x=x, y=y, width=width, height=height, fill=fill, rx=radius))


def text(svg, x, y, value, size, fill, font, leading=None):
    lines = value.splitlines()
    element = node(svg, 'text', {'x': x, 'y': y, 'font-size': size, 'fill': fill,
                                'font-family': font, 'xml:space': 'preserve'})
    for index, line in enumerate(lines):
        node(element, 'tspan', {'x': x, 'dy': 0 if index == 0 else (leading or size * 1.16)}, line)
    return element


def mix(a, b, amount):
    a, b = a.lstrip('#'), b.lstrip('#')
    return '#' + ''.join(f'{round(int(a[i:i+2], 16)*(1-amount)+int(b[i:i+2], 16)*amount):02x}'
                          for i in (0, 2, 4))


def weave(svg, cx, cy, radius, colors, count=9):
    """Original Loomwell over/under band geometry, kept as editable SVG paths."""
    pitch, angle = radius * 2 / (count + .75), math.radians(-28)
    width = pitch * .66
    group = node(svg, 'g', {'id': 'loomwell-weave'})
    green = mix(colors['forest'], colors['sage'], .2)
    offsets = [(i-(count-1)/2)*pitch for i in range(count)]

    def ribbon(x, y, w, h, fill, rounded=True):
        r = min(width*.45, w/2, h/2) if rounded else 0
        k = .55228475
        segments = [('M', [(x+r, y)]), ('L', [(x+w-r, y)]),
                    ('C', [(x+w-r+k*r, y), (x+w, y+r-k*r), (x+w, y+r)]),
                    ('L', [(x+w, y+h-r)]),
                    ('C', [(x+w, y+h-r+k*r), (x+w-r+k*r, y+h), (x+w-r, y+h)]),
                    ('L', [(x+r, y+h)]),
                    ('C', [(x+r-k*r, y+h), (x, y+h-r+k*r), (x, y+h-r)]),
                    ('L', [(x, y+r)]),
                    ('C', [(x, y+r-k*r), (x+r-k*r, y), (x+r, y)])]
        commands = []
        for command, points in segments:
            values = []
            for px, py in points:
                values.extend([cx+px*math.cos(angle)-py*math.sin(angle),
                               cy+px*math.sin(angle)+py*math.cos(angle)])
            commands.append(command + ' '.join(f'{v:.3f}' for v in values))
        node(group, 'path', {'d': ' '.join(commands)+' Z', 'fill': fill})

    for x in offsets:
        extent = math.sqrt(max(0, radius*radius-x*x))
        ribbon(x-width/2, -extent, width, extent*2, green)
    for j, y in enumerate(offsets):
        extent = math.sqrt(max(0, radius*radius-y*y))
        ribbon(-extent, y-width/2, extent*2, width,
               colors['terracotta'] if j == count//2 else colors['sage'])
    for i, x in enumerate(offsets):
        for j, y in enumerate(offsets):
            if (i+j) % 2 == 0 and x*x+y*y < (radius-width/2)**2:
                ribbon(x-width/2, y-width/2-1, width, width+2, green, False)


def validate_content(content):
    limits = {'headline': (2, 24), 'subheadline': (2, 55), 'eyebrow': (1, 38),
              'call_to_action': (1, 27), 'status': (1, 28), 'footer': (1, 42), 'site': (1, 28)}
    for key, (lines, length) in limits.items():
        value = content.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.splitlines()) > lines:
            raise ValueError(f'{key} must be nonempty text with at most {lines} line(s)')
        if any(len(line) > length for line in value.splitlines()):
            raise ValueError(f'{key}: each line must be at most {length} characters; add a line break or shorten it')


def validate_brand(brand):
    colors = brand.get('colors', {})
    for key in ('forest', 'paper', 'sage', 'terracotta'):
        if not isinstance(colors.get(key), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', colors[key]):
            raise ValueError('brand.json colors.' + key + ' must be a six-digit hex color')
    for key in ('display', 'body'):
        if not isinstance(brand.get('fonts', {}).get(key), str) or not brand['fonts'][key].strip():
            raise ValueError('brand.json fonts.' + key + ' must name an installed or bundled font')


def artwork(template, brand, content):
    c, fonts = brand['colors'], brand['fonts']
    w, h = template['width'], template['height']
    svg = ET.Element('{' + NS + '}svg', {'width': str(w), 'height': str(h), 'viewBox': f'0 0 {w} {h}'})
    node(svg, 'title', text='Loomwell — ' + template['title'])
    website = template['id'] == 'website'
    bg, ink, accent = (c['paper'], c['forest'], c['forest']) if website else (c['forest'], c['paper'], c['sage'])
    rect(svg, 0, 0, w, h, bg)
    display, body = fonts['display'], fonts['body']
    if website:
        text(svg, 80, 87, content['site'], 42, ink, display)
        text(svg, 1190, 80, content['status'], 17, ink, body)
        rect(svg, 80, 118, 1440, 1, mix(ink, bg, .75))
        text(svg, 80, 230, content['eyebrow'], 17, ink, body)
        text(svg, 76, 350, content['headline'], 76, ink, display, 91)
        text(svg, 80, 540, content['subheadline'], 27, mix(ink, bg, .2), body, 39)
        rect(svg, 80, 645, 296, 65, c['forest'], 4)
        text(svg, 106, 686, content['call_to_action']+' →', 22, c['paper'], body)
        weave(svg, 1200, 455, 260, c)
        rect(svg, 80, 800, 1440, 1, mix(ink, bg, .75))
        text(svg, 80, 846, content['footer'], 15, ink, body)
        text(svg, 1200, 846, 'LOOMWELL / EXPERIENCE', 15, ink, body)
    elif template['id'] == 'social':
        text(svg, 60, 85, content['site'], 39, ink, display)
        text(svg, 60, 145, content['eyebrow'], 14, accent, body)
        text(svg, 56, 256, content['headline'], 59, ink, display, 74)
        text(svg, 60, 414, content['subheadline'], 22, ink, body, 33)
        weave(svg, 965, 299, 184, c)
        rect(svg, 60, 523, 1080, 1, mix(ink, bg, .7))
        text(svg, 60, 570, content['footer'], 13, accent, body)
        text(svg, 962, 570, content['status'], 13, accent, body)
    else:
        text(svg, 68, 94, content['site'], 42, ink, display)
        text(svg, 68, 157, content['eyebrow'], 17, accent, body)
        text(svg, 64, 267, content['headline'], 70, ink, display, 84)
        text(svg, 68, 443, content['subheadline'], 26, ink, body, 37)
        weave(svg, 795, 742, 185, c)
        text(svg, 68, 706, 'EXPERIENCE', 17, accent, body)
        text(svg, 68, 756, 'Context.', 42, ink, display)
        text(svg, 68, 810, 'Correction.', 42, ink, display)
        text(svg, 68, 864, 'Outcome.', 42, ink, display)
        rect(svg, 68, 967, 944, 1, mix(ink, bg, .7))
        text(svg, 68, 1020, content['footer'], 15, accent, body)
        text(svg, 864, 1020, content['status'], 15, accent, body)
    return ET.ElementTree(svg)


def call_cli(cli, *args):
    env = os.environ.copy()
    # Headless work never needs to import or save a designer's personal preferences.
    env['VECTORCRAFT_NO_PREFS'] = '1'
    result = subprocess.run([cli, *map(str, args)], env=env, check=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.strip().startswith('{'):
            item = json.loads(line)
            result_item = item.get('result', item)
            if result_item.get('warnings'):
                raise ValueError('VectorCraft export warnings: ' + json.dumps(result_item['warnings']))
    return result


def export_template(cli, template, brand, content, output):
    name = template['id']
    source = output / (name + '.source.svg')
    artwork(template, brand, content).write(source, encoding='utf-8', xml_declaration=True)
    native = output / (name + '.vectorcraft')
    args = ['run', '--in', source]
    for key, color in brand['colors'].items():
        args += ['--cmd', 'swatch.new', '--params', json.dumps({'name': 'Loomwell ' + key.title(),
                                                              'color': color, 'global': True})]
    args += ['--cmd', 'swatch.newGroup', '--params', json.dumps({'name': 'Loomwell', 'swatches': [
        'Loomwell ' + key.title() for key in brand['colors']]})]
    args += ['--cmd', 'document.save', '--params', json.dumps({'path': str(native)})]
    palette_files = []
    for extension in ('vcswatches', 'gpl'):
        palette = output / ('loomwell.' + extension)
        palette_files.append(palette)
        args += ['--cmd', 'swatch.library.save', '--params', json.dumps({
            'path': str(palette), 'names': ['Loomwell'], 'name': 'Loomwell'})]
    for extension in ('svg', 'png', 'pdf'):
        args += ['--export', output / (name + '.' + extension)]
    call_cli(cli, *args)
    inspection = subprocess.run([cli, 'info', str(native)], check=True, capture_output=True, text=True,
                                env={**os.environ, 'VECTORCRAFT_NO_PREFS': '1'})
    info = json.loads(inspection.stdout)
    unresolved = [font.get('family', 'unknown') for font in info.get('fonts', [])
                  if font.get('status') != 'exact' or font.get('missingGlyphs')]
    if unresolved:
        raise ValueError(name + ': unresolved font or unsupported glyphs in ' + ', '.join(unresolved))
    inspected = call_cli(cli, 'run', '--in', native, '--cmd', 'document.inspect', '--params', '{"kind":"Type"}')
    rows = [json.loads(line) for line in inspected.stdout.splitlines() if line.strip()]
    types = next(row['result']['nodes'] for row in rows if row.get('command') == 'document.inspect')
    for item in types:
        bounds = item['bounds']
        right, bottom = bounds['x'] + bounds['width'], bounds['y'] + bounds['height']
        if bounds['x'] < 20 or bounds['y'] < 20 or right > template['width'] - 20 or bottom > template['height'] - 20:
            raise ValueError(name + ': rendered text exceeds the canvas safe area; shorten ' + repr(item['text']))
        if item['text'] in (content['headline'], content['subheadline'], content['eyebrow']):
            safe_right = {'website': 880, 'social': 730, 'square': 1012}[name]
            if right > safe_right:
                raise ValueError(name + ': rendered text exceeds its column safe area; shorten ' + repr(item['text']))
        if name == 'website' and item['text'] == content['call_to_action'] + ' →' and right > 355:
            raise ValueError('website: call_to_action exceeds the button safe area; shorten it')
    png = (output / (name + '.png')).read_bytes()
    if png[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', png[16:24]) != (template['width'], template['height']):
        raise ValueError(name + ': unexpected rendered PNG dimensions')
    if not (output / (name + '.pdf')).read_bytes().startswith(b'%PDF-'):
        raise ValueError(name + ': invalid PDF output')
    return [source, native] + [output / (name + '.' + ext) for ext in ('svg', 'png', 'pdf')] + palette_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('list')
    export = actions.add_parser('export')
    export.add_argument('template', choices=['all', 'website', 'social', 'square'])
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--cli')
    export.add_argument('--content', type=Path)
    args = parser.parse_args()
    pack = read_json(HERE / 'pack.json')
    if args.action == 'list':
        for template in pack['templates']:
            print(f"{template['id']:10} {template['width']}x{template['height']}  {template['title']}")
        return
    content = read_json(HERE / 'content.json')
    if args.content:
        overrides = read_json(args.content)
        unknown = set(overrides) - set(content)
        if unknown:
            raise ValueError('Unknown content keys: ' + ', '.join(sorted(unknown)))
        content.update(overrides)
    validate_content(content)
    brand = read_json(HERE / 'brand.json')
    validate_brand(brand)
    output = args.output.expanduser().resolve()
    protected = {HERE.resolve(), REPO.resolve()}
    if output in protected:
        raise ValueError('Choose an output subdirectory, not the pack or repository root.')
    if output.exists() and not output.is_dir():
        raise ValueError('Output must be a directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    cli = find_cli(args.cli)
    templates = [t for t in pack['templates'] if args.template in ('all', t['id'])]
    with tempfile.TemporaryDirectory(prefix='.loomwell-vector-export-', dir=output.parent) as temporary:
        staging = Path(temporary)
        files = []
        for template in templates:
            files.extend(export_template(cli, template, brand, content, staging))
        files = sorted(set(files))
        version = subprocess.check_output([cli, '--version'], text=True).strip()
        manifest = {'tool': 'vectorcraft', 'renderer': version, 'templates': templates,
                    'brand': brand, 'content': content, 'contains_customer_data': False,
                    'status': 'Original reusable Loomwell design templates',
                    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
        staged_manifest = staging / 'manifest.json'
        staged_manifest.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        output.mkdir(parents=True, exist_ok=True)
        for path in files:
            os.replace(path, output / path.name)
        os.replace(staged_manifest, output / 'manifest.json')
    for template in templates:
        print(f"Exported {template['id']}: {template['width']}x{template['height']}")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
