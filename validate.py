#!/usr/bin/env python3
"""Validation suite for pcb2goo (Tests A-E of the project brief). Run:  python validate.py
Inputs come from this repo (samples/, reference .goo files); tool paths (UVtools, Inkscape, kicad-cli)
default to the author's machine and can be overridden with env vars. Missing tools are skipped.
Prints markdown tables (copied into VALIDATION.md)."""
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

import pcb2goo as g

HERE = Path(__file__).parent
SVG_DIR = Path(os.environ.get('SVG_DIR', HERE / 'samples'))  # KiCad SVGs + the Inkscape PNGs made from them
REF = {'front': HERE / 'Rayhaan_Lab2.goo', 'back': HERE / 'Back.goo'}
SVG = {'front': SVG_DIR / 'Dark_Sensor-F_Cu.svg', 'back': SVG_DIR / 'Dark_Sensor-B_Cu.svg'}
UVTOOLS = Path(os.environ.get('UVTOOLS_CMD', r'C:\Users\rayha\Downloads\UVtools_win-x64_v7.0.0\UVtoolsCmd.exe'))
INKSCAPE = Path(os.environ.get('INKSCAPE', shutil.which('inkscape') or r'C:\Program Files\Inkscape\bin\inkscape.com'))
KICAD_CLI = Path(os.environ.get('KICAD_CLI', shutil.which('kicad-cli') or r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'))
DEMOS = KICAD_CLI.parent.parent / 'share' / 'kicad' / 'demos'
DEMO_BOARDS = ['ecc83/ecc83-pp', 'stickhub/StickHub', 'royalblue54L_feather/RoyalBlue54L-Feather',  # fit
               'pic_programmer/pic_programmer', 'interf_u/interf_u', 'tiny_tapeout/tinytapeout-demo']  # too big
# Same options as the user's KiCad Plot dialog (negative, mirrored, B&W, no drill marks, no sheet).
KICAD_ARGS = ['pcb', 'export', 'svg', '--mode-multi', '--layers', 'F.Cu,B.Cu', '--common-layers', 'Edge.Cuts',
              '--mirror', '--negative', '--black-and-white', '--exclude-drawing-sheet', '--drill-shape-opt', '0']
FAIL = []


def check(ok, what):
    print(f'- {"PASS" if ok else "**FAIL**"}: {what}')
    if not ok:
        FAIL.append(what)


def stats(a, b, mask=None):
    a, b = a.astype(int), b.astype(int)
    if mask is not None:
        a, b = a[mask], b[mask]
    d = np.abs(a - b)
    return (f'exact {np.mean(d == 0) * 100:.3f}% | within 16/255 {np.mean(d <= 16) * 100:.3f}% | '
            f'mean |diff| {d.mean():.4f} | max {d.max()} | coverage ratio {a.sum() / max(b.sum(), 1):.5f}')


def crop(a):
    ys, xs = np.nonzero(a)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def bbox(a):
    ys, xs = np.nonzero(a)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def dilate(m, r):
    """Square binary dilation by r px (separable shifts; PIL's MaxFilter is too slow at this size)."""
    out = m.copy()
    for s in range(1, r + 1):
        out[s:] |= m[:-s]
        out[:-s] |= m[s:]
    rows = out.copy()
    for s in range(1, r + 1):
        out[:, s:] |= rows[:, :-s]
        out[:, :-s] |= rows[:, s:]
    return out


def inkscape_png(svg):
    """Grey levels of the Inkscape PNG export (R channel, as UVtools imports it)."""
    return np.asarray(Image.open(svg).convert('RGBA'))[..., 0]


def test_codec():
    print('\n## Self-check: GOO RLE codec')
    rng = np.random.default_rng(1)
    frame = np.zeros((g.RES_Y, g.RES_X), np.uint8)
    frame[100:900, 200:5000] = rng.integers(0, 256, (800, 4800), dtype=np.uint8)  # every chunk type
    frame[2000:2100, :] = 255
    frame[3000, 7000:7010] = np.arange(100, 110)  # small diffs -> 0b10 chunks
    check(np.array_equal(g.decode_rle(g.encode_rle(frame)), frame), 'encode -> decode round trip (noise, runs, gradients)')
    for side, path in REF.items():
        if path.exists():
            header, [(layer, img)] = g.read_goo(path)
            data = path.read_bytes()
            off = header['LayerDefAddress'] + 70
            check(g.encode_rle(img) == data[off:off + layer['DataLength']],
                  f'{path.name}: re-encoding its decoded layer reproduces the UVtools RLE byte-for-byte')


def test_a():
    print('\n## Test A: SVG rasterization vs Inkscape PNG (same export window)')
    for side, svg in SVG.items():
        png = svg.with_suffix('.png')
        if not (svg.exists() and png.exists()):
            print(f'- skipped {side}: {svg} / {png} not found')
            continue
        ink = inkscape_png(png)
        mine = g.render_svg(svg, size=ink.shape[::-1])
        print(f'- {side} {ink.shape[1]}x{ink.shape[0]} px: {stats(mine, ink)}')
        check(np.mean(np.abs(mine.astype(int) - ink) <= 16) > 0.995, f'{side}: >99.5% of pixels within 16/255 of Inkscape')
        # The exposed area after cropping must be the same size as Inkscape's (before UVtools placement).
        cm, ci = crop(g.render_svg(svg)), crop(ink)
        print(f'  - cropped exposed area: mine {cm.shape[1]}x{cm.shape[0]} px, Inkscape {ci.shape[1]}x{ci.shape[0]} px')
        check(abs(cm.shape[0] - ci.shape[0]) <= 1 and abs(cm.shape[1] - ci.shape[1]) <= 1, f'{side}: cropped size within 1 px')


def test_bc(frames):
    for side, letter in (('front', 'B'), ('back', 'C')):
        print(f'\n## Test {letter}: {side} GOO vs reference {REF[side].name}')
        if not (REF[side].exists() and side in frames):
            print('- skipped (reference or SVG missing)')
            continue
        rh, [(rl, ref)] = g.read_goo(REF[side])
        mh, [(ml, mine)] = g.read_goo(frames[side])
        mask = None
        png = SVG[side].with_suffix('.png')
        if png.exists():  # what UVtools' import + flip + move produced from the Inkscape PNG
            ideal = g.place(crop(inkscape_png(png)), side)
            # Strokes added by hand in UVtools' pixel editor: thick blobs of difference (opening removes
            # the 1-2 px anti-aliasing seams), grown by 25 px to cover their soft edges.
            hand = dilate(~dilate(~(np.abs(ideal.astype(int) - ref) > 32), 2), 2)
            mask = ~dilate(hand, 25)
            print(f'- hand-edited pixels in the reference (pixel-editor marks): {int(hand.sum())} px')
            print(f'- placement logic, fed the Inkscape PNG, vs reference (outside hand edits): {stats(ideal, ref, mask)}')
        print(f'- reference non-zero bbox (x0,y0,x1,y1): {bbox(ref)}  generated: {bbox(mine)}')
        board = ref  # ignore stray hand-drawn dots away from the board:
        if png.exists():
            board = ref * dilate(ideal > 0, 3)
        check(bbox(board) == bbox(mine), f'{side}: board lands on exactly the same pixels as the reference')
        print(f'- generated vs reference, whole frame: {stats(mine, ref)}')
        if mask is not None:
            print(f'- generated vs reference, excluding hand edits: {stats(mine, ref, mask)}')
            d = np.abs(mine.astype(int) - ref)[mask]
            coverage = mine[mask].sum(dtype=np.int64) / ref[mask].sum(dtype=np.int64)
            check(np.mean(d <= 16) > 0.998 and abs(coverage - 1) < 0.002,
                  f'{side}: >99.8% of pixels within 16/255 and total exposure within 0.2% of the reference')
        skip = {'FileCreateTime', 'SmallPreview565', 'BigPreview565', 'Volume', 'MaterialGrams', 'MaterialCost', 'PrintTime'}
        diff = {k: (rh[k], mh[k]) for k in rh if k not in skip and rh[k] != mh[k]}
        print(f'- header fields that differ (reference -> generated): {diff or "none"}')
        ldiff = {k: (rl[k], ml[k]) for k in rl if k != 'DataLength' and rl[k] != ml[k]}
        print(f'- layer-definition fields that differ: {ldiff or "none"}')
        print(f'- informational: PrintTime {rh["PrintTime"]} -> {mh["PrintTime"]} s, Volume {rh["Volume"]:.3f} -> {mh["Volume"]:.3f} mm3')


def test_registration(frames):
    print('\n## Double-sided registration')
    if len(frames) < 2:
        return print('- skipped (needs both sides)')
    front = g.read_goo(frames['front'])[1][0][1] > 128
    back = g.read_goo(frames['back'])[1][0][1][:, ::-1] > 128  # back mirrored about the LCD's vertical centre line
    overlap = {(dx, dy): int((front & np.roll(back, (dy, dx), (0, 1))).sum()) for dx in range(-3, 4) for dy in range(-3, 4)}
    best = max(overlap, key=overlap.get)
    print(f'- copper shared by front and mirrored back (pads/vias): {overlap[(0, 0)]} px at offset 0,0; best offset {best}')
    check(best == (0, 0), 'pads and vias register exactly when the board is flipped left-right into the opposite corner')


def test_d(frames):
    print('\n## Test D: file validity')
    for side, path in frames.items():
        h, layers = g.read_goo(path)
        (layer, img), = layers
        check(h['LayerDefAddress'] == g.HEADER_SIZE == 195477 and h['Version'] == b'V3.0', f'{path.name}: header layout (V3.0, 195477-byte header)')
        check((h['ResolutionX'], h['ResolutionY'], h['LayerCount'], h['BottomLayerCount']) == (8520, 4320, 1, 10),
              f'{path.name}: 8520x4320, 1 layer, bottom layer count 10')
        check((h['BottomExposureTime'], layer['ExposureTime'], h['ExposureTime']) == (10, 10, 3),
              f'{path.name}: bottom exposure 10 s (header and layer), normal exposure 3 s')
        check(img.shape == (4320, 8520) and img.any(), f'{path.name}: layer decodes (checksum OK) to a non-empty 8520x4320 image')
        if UVTOOLS.exists():
            out = Path(tempfile.mkdtemp())
            r = subprocess.run([str(UVTOOLS), 'extract', str(path), str(out)], capture_output=True, text=True)
            ok = r.returncode == 0 and (out / 'layer0.png').exists()
            check(ok and np.array_equal(np.asarray(Image.open(out / 'layer0.png')), img),
                  f'{path.name}: UVtools 7.0.0 opens it and decodes the identical layer image')
            props = subprocess.run([str(UVTOOLS), 'print-properties', str(path)], capture_output=True, text=True).stdout
            keep = ('Resolution:', 'Display:', 'PixelSizeMicrons:', 'BoundingRectangle:', 'BoundingRectangleMillimeters:', 'ExposureRepresentation:')
            print('  - UVtools: ' + '; '.join(l.strip() for l in props.splitlines() if l.startswith(keep)))
        else:
            print(f'- UVtools not found at {UVTOOLS}; skipped')


def synthetic_svg(path, w, h, x0=50.0, y0=40.0):
    """A w x h mm board in KiCad's negative-plot SVG format: black background, white pads, an arc
    track, a straight track, a zone with a hole (even-odd) and the 0.05 mm Edge.Cuts outline."""
    zone = (f'M {x0 + 10},{y0 + 10} {x0 + 30},{y0 + 10} {x0 + 30},{y0 + 30} {x0 + 10},{y0 + 30} Z '
            f'M {x0 + 15},{y0 + 15} {x0 + 20},{y0 + 15} {x0 + 20},{y0 + 20} {x0 + 15},{y0 + 20} Z')
    path.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="297mm" height="210mm" viewBox="0 0 297 210">
<g style="fill:#000000; fill-opacity:1.0000; stroke:none;"><rect x="{x0 - 5}" y="{y0 - 5}" width="{w + 10}" height="{h + 10}" rx="0"/>
<path style="fill:#FFFFFF; stroke:none; fill-rule:evenodd;" d="{zone}"/></g>
<g style="fill:#FFFFFF; stroke:none;"><circle cx="{x0 + 5}" cy="{y0 + 5}" r="1.175"/><circle cx="{x0 + w - 5}" cy="{y0 + h - 5}" r="0.525"/></g>
<g style="fill:none; stroke:#FFFFFF; stroke-width:0.4000; stroke-linecap:round; stroke-linejoin:round;">
<path d="M{x0 + 5} {y0 + h / 2} A {h / 4} {h / 4} 0 0 1 {x0 + 5 + h / 2} {y0 + h / 2}"/><path d="M{x0 + 5} {y0 + 5} L{x0 + w - 5} {y0 + h - 5}"/>
<path style="stroke-width:0.0500;" d="M {x0},{y0} {x0 + w},{y0} {x0 + w},{y0 + h} {x0},{y0 + h} Z"/></g></svg>''')


def test_e():
    print('\n## Test E: other boards')
    tmp = Path(tempfile.mkdtemp())
    cases = []  # (label, side, svg, expected exposed size in mm or None)
    for b in DEMO_BOARDS if KICAD_CLI.exists() else []:  # KiCad demos, exported with the user's plot settings
        out = tmp / Path(b).name.replace(' ', '_')
        subprocess.run([str(KICAD_CLI), *KICAD_ARGS, '-o', str(out), str(DEMOS / f'{b}.kicad_pcb')], capture_output=True)
        for svg in sorted(out.glob('*.svg')):
            top = svg.stem.lower().endswith(('f_cu', 'top_cu', 'top_copper', 'top_layer'))
            cases.append((f'KiCad demo {Path(b).name}', 'front' if top else 'back', svg, None))
    for w, h in ((150, 75), (154, 50), (60, 100)):
        svg = tmp / f'synthetic-{w}x{h}-F_Cu.svg'
        synthetic_svg(svg, w, h)
        cases.append((f'synthetic {w} x {h} mm', 'front', svg, (w + 0.05, h + 0.05)))  # + outline stroke

    print('\n| Board | Side | Plot area (mm) | Result | Exposed size (mm) | vs Inkscape CLI (same SVG) |\n|---|---|---|---|---|---|')
    for label, side, svg, expect in cases:
        x, y, w, h = g._negative_plot_rect(ET.parse(svg).getroot())
        ref = None
        if INKSCAPE.exists():  # independent judge: Inkscape's own render of the same SVG
            png = tmp / (svg.stem + '_ink.png')
            subprocess.run([str(INKSCAPE), str(svg), '--export-type=png', '--export-area-drawing',
                            '--export-dpi=1411.11', f'--export-filename={png}'], capture_output=True)
            ref = inkscape_png(png)
            ch, cw = crop(ref).shape  # exposed-area size according to Inkscape
        size_mm = expect or ((cw * g.PIXEL_MM, ch * g.PIXEL_MM) if ref is not None else None)
        fits = size_mm is None or (size_mm[0] <= g.MAX_MM[0] and size_mm[1] <= g.MAX_MM[1])
        try:
            path, frame = g.convert(**{f'{side}_svg': svg}, out_dir=tmp)[side]
            hd, [(_, img)] = g.read_goo(path)
            x0, y0, x1, y1 = bbox(frame)
            ok = np.array_equal(img, frame) and y1 == g.RES_Y - 1 and (x0 == 0 if side == 'front' else x1 == g.RES_X - 1)
            res = 'GOO OK, in corner' if ok else '**GOO wrong (decode/placement)**'
            size = f'{(x1 - x0 + 1) * g.PIXEL_MM:.3f} x {(y1 - y0 + 1) * g.PIXEL_MM:.3f}'
            if expect:  # exposed span must be the drawn size at 18 um/px (+ up to one partly covered pixel)
                ok &= all(abs(n - e / g.PIXEL_MM) <= 1.5 for n, e in ((x1 - x0 + 1, expect[0]), (y1 - y0 + 1, expect[1])))
                size += f' (drawn {expect[0]:.2f} x {expect[1]:.2f})'
            ink = ''
            if ref is not None:
                d = np.abs(g.render_svg(svg, size=ref.shape[::-1]).astype(int) - ref)
                dw, dh = (x1 - x0 + 1) - cw, (y1 - y0 + 1) - ch
                ink = f'{np.mean(d == 0) * 100:.2f}% exact, {np.mean(d <= 16) * 100:.3f}% within 16/255, size diff {dw:+d}/{dh:+d} px'
                ok &= np.mean(d <= 16) > 0.995 and abs(dw) <= 1 and abs(dh) <= 1
            ok &= fits
        except ValueError as e:
            res, size, ok = f'rejected: {e}'.replace('|', '/'), '', not fits
            ink = f'Inkscape: exposed area {size_mm[0]:.1f} x {size_mm[1]:.1f} mm (too large)' if size_mm and not fits else ''
        if not ok:
            FAIL.append(f'Test E {label} {side}')
        print(f'| {label} | {side} | {w:.1f} x {h:.1f} | {res}{"" if ok else " **FAIL**"} | {size} | {ink} |')

    print('\nError handling:')
    svg = SVG['front']
    if svg.exists():
        pos = tmp / 'positive.svg'  # same board without KiCad's negative-plot background
        pos.write_text(svg.read_text().replace('style="fill:#000000; fill-opacity:1.0000; stroke:none;"', 'style="fill:#FFFFFF;"', 1))
        for name, f in [('positive (non-negative) plot', pos), ('not an SVG', HERE / 'pcb2goo.py')]:
            try:
                g.render_svg(f)
                check(False, f'{name} is rejected')
            except ValueError as e:
                check(True, f'{name} is rejected with: "{e}"')


if __name__ == '__main__':
    test_codec()
    test_a()
    out = Path(tempfile.mkdtemp())
    frames = {s: path for s, (path, _) in g.convert(*(str(SVG[s]) if SVG[s].exists() else None
                                                       for s in ('front', 'back')), out_dir=out).items()}
    test_bc(frames)
    test_registration(frames)
    test_d(frames)
    test_e()
    print(f'\n**{len(FAIL)} failure(s)**' + (': ' + '; '.join(FAIL) if FAIL else ''))
    raise SystemExit(bool(FAIL))
