#!/usr/bin/env python3
"""KiCad copper-layer SVG -> Elegoo Mars 4 Ultra .goo converter (engine + command line).

Pipeline (replaces Inkscape + UVtools):
  KiCad negative-plot SVG
  -> 8-bit grayscale raster at the LCD pitch (18 um/px = 1411.11 DPI), anti-aliased
  -> crop to the exposed (non-black) area
  -> flip + anchor in the 8520x4320 frame exactly like the reference files
  -> GOO file (format per UVtools.Core/FileFormats/GooFile.cs, big-endian).
"""
import argparse
import io
import struct
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import resvg_py
from PIL import Image

RES_X, RES_Y = 8520, 4320  # Mars 4 Ultra LCD, pixels
PIXEL_MM = 0.018           # 18 um pitch (25.4 / 0.018 = 1411.11 DPI)
MAX_MM = (RES_X * PIXEL_MM, RES_Y * PIXEL_MM)  # 153.36 x 77.76 mm
# resvg anti-aliases with only 16 coverage levels; averaging SUPERSAMPLE^2 sub-pixels approaches
# the exact-area coverage Inkscape (cairo) produces (see VALIDATION.md, Test A).
SUPERSAMPLE = 4  # ~12 s per side for a 75 x 25 mm board; 2 is ~4x faster and nearly as close

MAGIC = bytes([0x07, 0x00, 0x00, 0x00, 0x44, 0x4C, 0x50, 0x00])
DELIM = b'\r\n'
FOOTER = b'\x00\x00\x00' + MAGIC

HEADER_FIELDS = [  # (name, struct code), file order
    ('Version', '4s'), ('Magic', '8s'), ('SoftwareName', '32s'), ('SoftwareVersion', '24s'),
    ('FileCreateTime', '24s'), ('MachineName', '32s'), ('MachineType', '32s'), ('ProfileName', '32s'),
    ('AntiAliasingLevel', 'H'), ('GreyLevel', 'H'), ('BlurLevel', 'H'),
    ('SmallPreview565', f'{116 * 116 * 2}s'), ('SmallPreviewDelimiter', '2s'),
    ('BigPreview565', f'{290 * 290 * 2}s'), ('BigPreviewDelimiter', '2s'),
    ('LayerCount', 'I'), ('ResolutionX', 'H'), ('ResolutionY', 'H'), ('MirrorX', '?'), ('MirrorY', '?'),
    ('DisplayWidth', 'f'), ('DisplayHeight', 'f'), ('MachineZ', 'f'), ('LayerHeight', 'f'),
    ('ExposureTime', 'f'), ('DelayMode', 'B'), ('LightOffDelay', 'f'),
    ('BottomWaitTimeAfterCure', 'f'), ('BottomWaitTimeAfterLift', 'f'), ('BottomWaitTimeBeforeCure', 'f'),
    ('WaitTimeAfterCure', 'f'), ('WaitTimeAfterLift', 'f'), ('WaitTimeBeforeCure', 'f'),
    ('BottomExposureTime', 'f'), ('BottomLayerCount', 'I'),
    ('BottomLiftHeight', 'f'), ('BottomLiftSpeed', 'f'), ('LiftHeight', 'f'), ('LiftSpeed', 'f'),
    ('BottomRetractHeight', 'f'), ('BottomRetractSpeed', 'f'), ('RetractHeight', 'f'), ('RetractSpeed', 'f'),
    ('BottomLiftHeight2', 'f'), ('BottomLiftSpeed2', 'f'), ('LiftHeight2', 'f'), ('LiftSpeed2', 'f'),
    ('BottomRetractHeight2', 'f'), ('BottomRetractSpeed2', 'f'), ('RetractHeight2', 'f'), ('RetractSpeed2', 'f'),
    ('BottomLightPWM', 'H'), ('LightPWM', 'H'), ('PerLayerSettings', '?'), ('PrintTime', 'I'),
    ('Volume', 'f'), ('MaterialGrams', 'f'), ('MaterialCost', 'f'), ('PriceCurrencySymbol', '8s'),
    ('LayerDefAddress', 'I'), ('GrayScaleLevel', 'B'), ('TransitionLayerCount', 'H'),
]
LAYER_FIELDS = [
    ('Pause', 'H'), ('PausePositionZ', 'f'), ('PositionZ', 'f'), ('ExposureTime', 'f'), ('LightOffDelay', 'f'),
    ('WaitTimeAfterCure', 'f'), ('WaitTimeAfterLift', 'f'), ('WaitTimeBeforeCure', 'f'),
    ('LiftHeight', 'f'), ('LiftSpeed', 'f'), ('LiftHeight2', 'f'), ('LiftSpeed2', 'f'),
    ('RetractHeight', 'f'), ('RetractSpeed', 'f'), ('RetractHeight2', 'f'), ('RetractSpeed2', 'f'),
    ('LightPWM', 'H'), ('Delimiter', '2s'), ('DataLength', 'I'),
]
HEADER_FMT = '>' + ''.join(c for _, c in HEADER_FIELDS)
LAYER_FMT = '>' + ''.join(c for _, c in LAYER_FIELDS)
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 195477, matches LayerDefAddress in the references

# Printer settings copied from the user's known-working references (Rayhaan_Lab2.goo / Back.goo).
# Per-file values (previews, time stamp, volume, bottom exposure) are filled in by write_goo().
# DisplayWidth/Height use Back.goo's correct Mars 4 Ultra size; Rayhaan_Lab2.goo had stale
# 81 x 128 mm values left over from the UVtools SL1S demo file.
HEADER = {
    'Version': b'V3.0', 'Magic': MAGIC, 'SoftwareName': b'UVtools', 'SoftwareVersion': b'7.0.0',
    'MachineName': b'UVtools Prusa SL1S SPEED', 'MachineType': b'DLP', 'ProfileName': b'UVtools',
    'AntiAliasingLevel': 8, 'GreyLevel': 1, 'BlurLevel': 0,
    'SmallPreviewDelimiter': DELIM, 'BigPreviewDelimiter': DELIM,
    'LayerCount': 1, 'ResolutionX': RES_X, 'ResolutionY': RES_Y, 'MirrorX': True, 'MirrorY': False,
    'DisplayWidth': 153.36, 'DisplayHeight': 77.76, 'MachineZ': 150.0, 'LayerHeight': 0.1,
    'ExposureTime': 3.0, 'DelayMode': 1, 'LightOffDelay': 0.0,
    'BottomWaitTimeAfterCure': 0.0, 'BottomWaitTimeAfterLift': 0.0, 'BottomWaitTimeBeforeCure': 0.0,
    'WaitTimeAfterCure': 0.0, 'WaitTimeAfterLift': 0.0, 'WaitTimeBeforeCure': 0.0,
    'BottomExposureTime': 10.0, 'BottomLayerCount': 10,
    'BottomLiftHeight': 6.0, 'BottomLiftSpeed': 100.0, 'LiftHeight': 6.0, 'LiftSpeed': 100.0,
    'BottomRetractHeight': 6.0, 'BottomRetractSpeed': 100.0, 'RetractHeight': 6.0, 'RetractSpeed': 100.0,
    'BottomLiftHeight2': 0.0, 'BottomLiftSpeed2': 300.0, 'LiftHeight2': 0.0, 'LiftSpeed2': 300.0,
    'BottomRetractHeight2': 0.0, 'BottomRetractSpeed2': 80.0, 'RetractHeight2': 0.0, 'RetractSpeed2': 80.0,
    'BottomLightPWM': 255, 'LightPWM': 255, 'PerLayerSettings': False,
    'PriceCurrencySymbol': b'$', 'LayerDefAddress': HEADER_SIZE, 'GrayScaleLevel': 1, 'TransitionLayerCount': 0,
}
LAYER = {  # the single (bottom) layer, as in the references
    'Pause': 0, 'PausePositionZ': 150.0, 'PositionZ': 0.1, 'LightOffDelay': 0.0,
    'WaitTimeAfterCure': 0.0, 'WaitTimeAfterLift': 0.0, 'WaitTimeBeforeCure': 0.0,
    'LiftHeight': 6.0, 'LiftSpeed': 100.0, 'LiftHeight2': 0.0, 'LiftSpeed2': 300.0,
    'RetractHeight': 6.0, 'RetractSpeed': 100.0, 'RetractHeight2': 0.0, 'RetractSpeed2': 80.0,
    'LightPWM': 255, 'Delimiter': DELIM,
}

SVG_NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG_NS)
_MM_PER_UNIT = {'mm': 1.0, 'cm': 10.0, 'in': 25.4, 'pt': 25.4 / 72, 'pc': 25.4 / 6, 'px': 25.4 / 96, '': 25.4 / 96}


# ---------------------------------------------------------------- SVG -> raster

def _style_fill(el):
    s = el.get('style', '').replace(' ', '').lower()
    for part in s.split(';'):
        if part.startswith('fill:'):
            return part[5:]
    return el.get('fill', '').lower() or None


def _negative_plot_rect(root):
    """KiCad's negative plot starts with a black <rect> covering the board area; it is the
    'selection' Inkscape exports and the only area worth rendering (drawing sheet etc. lie outside)."""
    for g in root.iter():
        for r in g.findall(f'{{{SVG_NS}}}rect'):
            if (_style_fill(r) or _style_fill(g)) in ('#000000', '#000', 'black'):
                return [float(r.get(k, 0)) for k in ('x', 'y', 'width', 'height')]
    raise ValueError("No negative-plot background found. In KiCad's Plot dialog enable "
                     "'Negative plot' (and 'Black and white') and export the SVG again.")


def _mm_per_user_unit(root):
    w = root.get('width', '')
    num = w.rstrip('abcdefghijklmnopqrstuvwxyz%')
    vb = root.get('viewBox')
    if not vb or not num:
        return 25.4 / 96
    return float(num) * _MM_PER_UNIT[w[len(num):]] / float(vb.replace(',', ' ').split()[2])


def _rasterize(root, x, y, W, H, sx, sy, ss=SUPERSAMPLE, strip=128):
    """Render the SVG window (x, y, W*sx, H*sy) in user units to a W x H uint8 image, white over
    black, averaging ss x ss sub-pixels. Rendered in horizontal strips to bound memory."""
    root.set('preserveAspectRatio', 'none')
    out = np.empty((H, W), np.uint8)
    for r0 in range(0, H, strip):
        n = min(strip, H - r0)
        root.set('viewBox', ' '.join(repr(float(v)) for v in (x, y + r0 * sy, W * sx, n * sy)))
        root.set('width', str(W * ss))
        root.set('height', str(n * ss))
        png = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding='unicode'))
        rgba = Image.open(io.BytesIO(bytes(png))).convert('RGBA')
        gray = Image.alpha_composite(Image.new('RGBA', rgba.size, (0, 0, 0, 255)), rgba).convert('L')
        out[r0:r0 + n] = np.rint(np.asarray(gray, np.float32).reshape(n, ss, W, ss).mean((1, 3)))
    return out


def render_svg(svg_path, size=None, ss=SUPERSAMPLE):
    """Rasterize a KiCad negative-plot SVG at 18 um/px. Returns uint8 exposure (255 = UV on =
    copper) cropped to the non-black area. `size=(W, H)` instead stretches the whole plot area onto
    exactly W x H pixels like Inkscape's selection export (validation only, no crop)."""
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError as e:
        raise ValueError(f'{Path(svg_path).name} is not a valid SVG file ({e}).') from None
    x, y, w, h = _negative_plot_rect(root)
    if size:
        return _rasterize(root, x, y, *size, w / size[0], h / size[1], ss)
    step = PIXEL_MM / _mm_per_user_unit(root)  # one LCD pixel in SVG user units
    W, H = round(w / step), round(h / step)
    # Cheap 8x-coarser pass: find the exposed area, reject oversize boards before the slow render.
    c = 8
    coarse = _rasterize(root, x, y, -(-W // c), -(-H // c), c * step, c * step, ss=1)
    ys, xs = np.nonzero(coarse)
    if not len(xs):
        raise ValueError(f'{Path(svg_path).name}: nothing to expose (image is all black).')
    if (np.ptp(xs) - 1) * c > RES_X or (np.ptp(ys) - 1) * c > RES_Y:
        raise ValueError(f'{Path(svg_path).name}: board is about {(np.ptp(xs) + 1) * c * PIXEL_MM:.0f} x '
                         f'{(np.ptp(ys) + 1) * c * PIXEL_MM:.0f} mm; the Mars 4 Ultra can expose at most '
                         f'{MAX_MM[0]:.2f} x {MAX_MM[1]:.2f} mm.')
    c0, r0 = int(max(xs.min() - 1, 0) * c), int(max(ys.min() - 1, 0) * c)  # window on the same pixel grid
    c1, r1 = int(min((xs.max() + 2) * c, W)), int(min((ys.max() + 2) * c, H))
    gray = _rasterize(root, x + c0 * step, y + r0 * step, c1 - c0, r1 - r0, step, step, ss)
    ys, xs = np.nonzero(gray)
    return gray[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def place(img, side):
    """Put the cropped board into the 8520x4320 LCD frame, matching the reference files
    (image-buffer coordinates, row 0 = top of the stored image):
      front: rotated 180 deg, anchored bottom-left   (Rayhaan_Lab2.goo)
      back:  flipped vertically, anchored bottom-right (Back.goo)"""
    h, w = img.shape
    if w > RES_X or h > RES_Y:
        raise ValueError(f'Board is {w * PIXEL_MM:.2f} x {h * PIXEL_MM:.2f} mm; the Mars 4 Ultra '
                         f'can expose at most {MAX_MM[0]:.2f} x {MAX_MM[1]:.2f} mm.')
    frame = np.zeros((RES_Y, RES_X), np.uint8)
    if side == 'front':
        frame[RES_Y - h:, :w] = img[::-1, ::-1]
    elif side == 'back':
        frame[RES_Y - h:, RES_X - w:] = img[::-1, :]
    else:
        raise ValueError(side)
    return frame


# ---------------------------------------------------------------- GOO encode / decode

def _runs(frame):
    flat = frame.ravel()
    starts = np.concatenate(([0], np.flatnonzero(flat[1:] != flat[:-1]) + 1))
    lengths = np.diff(np.append(starts, flat.size))
    return flat[starts].tolist(), lengths.tolist()


def encode_rle(frame):
    """Layer RLE, byte-for-byte the same algorithm as UVtools' GooFile.LayerDef.EncodeImage."""
    out = bytearray([0x55])
    colors, lengths = _runs(frame)
    for i, (cur, n) in enumerate(zip(colors, lengths)):
        prev = colors[i - 1] if i else 0  # UVtools starts from color 0
        diff = abs(cur - prev)
        if diff <= 0xF and n <= 0xFF and 0 < cur < 0xFF:  # 0b10: small change from previous run
            b = 0x80 | diff | (0x20 if cur < prev else 0) | (0x10 if n > 1 else 0)
            out += bytes([b, n]) if n > 1 else bytes([b])
            continue
        extra = 0 if n <= 0xF else 1 if n <= 0xFFF else 2 if n <= 0xFFFFF else 3
        kind = 0xC0 if cur == 0xFF else 0x40 if cur else 0x00
        out.append(kind | (extra << 4) | (n & 0xF))
        if kind == 0x40:
            out.append(cur)
        out += bytes((n >> s) & 0xFF for s in (20, 12, 4)[3 - extra:])
    out.append(~sum(out[1:]) & 0xFF)
    return bytes(out)


def decode_rle(data, size=RES_X * RES_Y):
    if data[0] != 0x55:
        raise ValueError('layer RLE does not start with 0x55')
    if (~sum(data[1:-1]) & 0xFF) != data[-1]:
        raise ValueError('layer RLE checksum mismatch')
    colors, lengths = [], []
    color, i, end = 0, 1, len(data) - 1
    while i < end:
        b = data[i]
        kind = b >> 6
        if kind == 2:
            d = b & 0xF
            color = (color - d if b & 0x20 else color + d) & 0xFF
            if b & 0x10:
                i += 1
                n = data[i]
            else:
                n = 1
        else:
            if kind == 1:
                i += 1
                color = data[i]
            else:
                color = 0 if kind == 0 else 0xFF
            extra = (b >> 4) & 3
            n = 0
            for k in range(extra):
                n = (n << 8) | data[i + 1 + k]
            n = (n << 4) | (b & 0xF)
            i += extra
        colors.append(color)
        lengths.append(n)
        i += 1
    if sum(lengths) != size:
        raise ValueError(f'layer RLE decodes to {sum(lengths)} pixels, expected {size}')
    return np.repeat(np.array(colors, np.uint8), lengths).reshape(RES_Y, RES_X)


def _rgb565(frame, n):
    """Square n x n preview of the exposed area, RGB565 big-endian as UVtools writes it."""
    ys, xs = np.nonzero(frame)
    img = Image.fromarray(frame[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(xs) else frame)
    img.thumbnail((n, n), Image.LANCZOS)
    canvas = Image.new('L', (n, n))
    canvas.paste(img, ((n - img.width) // 2, (n - img.height) // 2))
    v = np.asarray(canvas.convert('RGB')).astype(np.uint16)
    return (((v[..., 0] >> 3) << 11) | ((v[..., 1] >> 2) << 5) | (v[..., 2] >> 3)).astype('>u2').tobytes()


def write_goo(path, frame, bottom_exposure=10.0):
    rle = encode_rle(frame)
    pixels = int(np.count_nonzero(frame))
    volume = round(pixels * PIXEL_MM * PIXEL_MM * HEADER['LayerHeight'], 3)  # mm^3, as UVtools computes it
    h = dict(HEADER,
             FileCreateTime=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()).encode(),
             SmallPreview565=_rgb565(frame, 116), BigPreview565=_rgb565(frame, 290),
             BottomExposureTime=float(bottom_exposure),
             # Informational only (shown on the printer); formulas fitted to both references.
             PrintTime=int(307.2 + bottom_exposure), Volume=volume,
             MaterialGrams=round(volume / 1000, 3), MaterialCost=round(volume / 1000 * 0.05, 3))
    layer = dict(LAYER, ExposureTime=float(bottom_exposure), DataLength=len(rle))
    with open(path, 'wb') as f:
        f.write(struct.pack(HEADER_FMT, *(h[k] for k, _ in HEADER_FIELDS)))
        f.write(struct.pack(LAYER_FMT, *(layer[k] for k, _ in LAYER_FIELDS)))
        f.write(rle + DELIM + FOOTER)


def read_goo(path):
    """Returns (header dict, [(layer dict, image)]). Raises ValueError on structural problems."""
    data = Path(path).read_bytes()
    header = dict(zip((k for k, _ in HEADER_FIELDS), struct.unpack_from(HEADER_FMT, data)))
    if header['Magic'] != MAGIC or data[-len(FOOTER):] != FOOTER:
        raise ValueError('not a GOO file (magic/footer mismatch)')
    pos, layers = header['LayerDefAddress'], []
    for _ in range(header['LayerCount']):
        layer = dict(zip((k for k, _ in LAYER_FIELDS), struct.unpack_from(LAYER_FMT, data, pos)))
        pos += struct.calcsize(LAYER_FMT)
        rle = data[pos:pos + layer['DataLength']]
        pos += layer['DataLength']
        if data[pos:pos + 2] != DELIM:
            raise ValueError('missing layer delimiter')
        pos += 2
        layers.append((layer, decode_rle(rle, header['ResolutionX'] * header['ResolutionY'])))
    if pos + len(FOOTER) != len(data):
        raise ValueError('unexpected bytes after the last layer')
    return header, layers


# ---------------------------------------------------------------- convenience

def convert(front_svg=None, back_svg=None, out_dir='.', bottom_exposure=10.0):
    """Convert one or both sides. Returns {side: (goo_path, frame)}."""
    results = {}
    for side, svg in (('front', front_svg), ('back', back_svg)):
        if not svg:
            continue
        frame = place(render_svg(svg), side)
        out = Path(out_dir) / (Path(svg).stem + '.goo')
        write_goo(out, frame, bottom_exposure)
        results[side] = (out, frame)
    if not results:
        raise ValueError('Select at least one SVG.')
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--front', help='F.Cu SVG from KiCad (negative plot)')
    p.add_argument('--back', help='B.Cu SVG from KiCad (negative plot)')
    p.add_argument('--out', default='.', help='output folder (default: current)')
    p.add_argument('--bottom-exposure', type=float, default=10.0, help='seconds (default 10)')
    a = p.parse_args(argv)
    for side, (path, frame) in convert(a.front, a.back, a.out, a.bottom_exposure).items():
        ys, xs = np.nonzero(frame)
        print(f'{side}: {path}  board {(np.ptp(xs) + 1) * PIXEL_MM:.2f} x {(np.ptp(ys) + 1) * PIXEL_MM:.2f} mm '
              f'at x {xs.min()}..{xs.max()}, y {ys.min()}..{ys.max()}')


if __name__ == '__main__':
    sys.exit(main())
