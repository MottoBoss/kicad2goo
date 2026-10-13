
## Self-check: GOO RLE codec
- PASS: encode -> decode round trip (noise, runs, gradients)
- PASS: Rayhaan_Lab2.goo: re-encoding its decoded layer reproduces the UVtools RLE byte-for-byte
- PASS: Back.goo: re-encoding its decoded layer reproduces the UVtools RLE byte-for-byte

## Test A: SVG rasterization vs Inkscape PNG (same export window)
- front 4742x2166 px: exact 99.100% | within 16/255 99.988% | mean |diff| 0.0437 | max 77 | coverage ratio 0.99968
- PASS: front: >99.5% of pixels within 16/255 of Inkscape
  - cropped exposed area: mine 4143x1393 px, Inkscape 4142x1393 px
- PASS: front: cropped size within 1 px
- back 4743x2166 px: exact 99.467% | within 16/255 99.997% | mean |diff| 0.0255 | max 69 | coverage ratio 0.99974
- PASS: back: >99.5% of pixels within 16/255 of Inkscape
  - cropped exposed area: mine 4143x1393 px, Inkscape 4143x1393 px
- PASS: back: cropped size within 1 px

## Test B: front GOO vs reference Rayhaan_Lab2.goo
- hand-edited pixels in the reference (pixel-editor marks): 0 px
- placement logic, fed the Inkscape PNG, vs reference (outside hand edits): exact 99.789% | within 16/255 99.827% | mean |diff| 0.1530 | max 238 | coverage ratio 0.99979
- reference non-zero bbox (x0,y0,x1,y1): (0, 2927, 4142, 4319)  generated: (0, 2927, 4142, 4319)
- PASS: front: board lands on exactly the same pixels as the reference
- generated vs reference, whole frame: exact 99.716% | within 16/255 99.864% | mean |diff| 0.0581 | max 140 | coverage ratio 0.99930
- generated vs reference, excluding hand edits: exact 99.716% | within 16/255 99.864% | mean |diff| 0.0581 | max 140 | coverage ratio 0.99930
- PASS: front: >99.8% of pixels within 16/255 and total exposure within 0.2% of the reference
- header fields that differ (reference -> generated): {'DisplayWidth': (81.0, 153.36000061035156), 'DisplayHeight': (128.0, 77.76000213623047)}
- layer-definition fields that differ: none
- informational: PrintTime 317 -> 317 s, Volume 35.013 -> 40.250 mm3

## Test C: back GOO vs reference Back.goo
- hand-edited pixels in the reference (pixel-editor marks): 146738 px
- placement logic, fed the Inkscape PNG, vs reference (outside hand edits): exact 100.000% | within 16/255 100.000% | mean |diff| 0.0000 | max 255 | coverage ratio 0.99999
- reference non-zero bbox (x0,y0,x1,y1): (3670, 2927, 8519, 4319)  generated: (4377, 2927, 8519, 4319)
- PASS: back: board lands on exactly the same pixels as the reference
- generated vs reference, whole frame: exact 99.440% | within 16/255 99.533% | mean |diff| 1.0287 | max 255 | coverage ratio 0.78587
- generated vs reference, excluding hand edits: exact 99.839% | within 16/255 99.933% | mean |diff| 0.0306 | max 255 | coverage ratio 0.99943
- PASS: back: >99.8% of pixels within 16/255 and total exposure within 0.2% of the reference
- header fields that differ (reference -> generated): {'BottomExposureTime': (9.5, 10.0)}
- layer-definition fields that differ: {'ExposureTime': (9.5, 10.0)}
- informational: PrintTime 316 -> 317 s, Volume 22.920 -> 18.155 mm3

## Double-sided registration
- copper shared by front and mirrored back (pads/vias): 292678 px at offset 0,0; best offset (0, 0)
- PASS: pads and vias register exactly when the board is flipped left-right into the opposite corner

## Test D: file validity
- PASS: Dark_Sensor-F_Cu.goo: header layout (V3.0, 195477-byte header)
- PASS: Dark_Sensor-F_Cu.goo: 8520x4320, 1 layer, bottom layer count 10
- PASS: Dark_Sensor-F_Cu.goo: bottom exposure 10 s (header and layer), normal exposure 3 s
- PASS: Dark_Sensor-F_Cu.goo: layer decodes (checksum OK) to a non-empty 8520x4320 image
- PASS: Dark_Sensor-F_Cu.goo: UVtools 7.0.0 opens it and decodes the identical layer image
  - UVtools: BoundingRectangle: {X=0,Y=2927,Width=4143,Height=1393}; BoundingRectangleMillimeters: {X=0,Y=52.69,Width=74.57,Height=25.07}; Resolution: {Width=8520, Height=4320}; Display: {Width=153.36, Height=77.76}; PixelSizeMicrons: {Width=18, Height=18}; ExposureRepresentation: 10/3s
- PASS: Dark_Sensor-B_Cu.goo: header layout (V3.0, 195477-byte header)
- PASS: Dark_Sensor-B_Cu.goo: 8520x4320, 1 layer, bottom layer count 10
- PASS: Dark_Sensor-B_Cu.goo: bottom exposure 10 s (header and layer), normal exposure 3 s
- PASS: Dark_Sensor-B_Cu.goo: layer decodes (checksum OK) to a non-empty 8520x4320 image
- PASS: Dark_Sensor-B_Cu.goo: UVtools 7.0.0 opens it and decodes the identical layer image
  - UVtools: BoundingRectangle: {X=4377,Y=2927,Width=4143,Height=1393}; BoundingRectangleMillimeters: {X=78.79,Y=52.69,Width=74.57,Height=25.07}; Resolution: {Width=8520, Height=4320}; Display: {Width=153.36, Height=77.76}; PixelSizeMicrons: {Width=18, Height=18}; ExposureRepresentation: 10/3s

## Test E: other boards

| Board | Side | Plot area (mm) | Result | Exposed size (mm) | vs Inkscape CLI (same SVG) |
|---|---|---|---|---|---|
| KiCad demo ecc83-pp | back | 65.8 x 59.4 | GOO OK, in corner | 52.200 x 46.512 | 99.31% exact, 99.990% within 16/255, size diff -1/+0 px |
| KiCad demo ecc83-pp | front | 65.8 x 59.4 | GOO OK, in corner | 52.200 x 46.512 | 99.68% exact, 99.996% within 16/255, size diff -1/+0 px |
| KiCad demo StickHub | back | 29.0 x 62.0 | GOO OK, in corner | 16.614 x 40.122 | 98.90% exact, 99.948% within 16/255, size diff +0/+0 px |
| KiCad demo StickHub | front | 29.0 x 62.0 | GOO OK, in corner | 16.614 x 40.122 | 99.03% exact, 99.951% within 16/255, size diff +0/+0 px |
| KiCad demo RoyalBlue54L-Feather | back | 72.3 x 42.8 | GOO OK, in corner | 58.536 x 24.588 | 98.67% exact, 99.978% within 16/255, size diff +0/+0 px |
| KiCad demo RoyalBlue54L-Feather | front | 72.3 x 42.8 | GOO OK, in corner | 58.536 x 24.588 | 98.45% exact, 99.960% within 16/255, size diff +0/+0 px |
| KiCad demo pic_programmer | back | 181.3 x 127.1 | rejected: pic_programmer-bottom_layer.svg: board is about 160 x 99 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 160.1 x 99.2 mm (too large) |
| KiCad demo pic_programmer | front | 181.3 x 127.1 | rejected: pic_programmer-top_layer.svg: board is about 160 x 99 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 160.1 x 99.2 mm (too large) |
| KiCad demo interf_u | back | 149.4 x 127.9 | rejected: interf_u-bottom_copper.svg: board is about 116 x 108 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 115.7 x 108.4 mm (too large) |
| KiCad demo interf_u | front | 149.4 x 127.9 | rejected: interf_u-top_copper.svg: board is about 116 x 108 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 115.7 x 108.4 mm (too large) |
| KiCad demo tinytapeout-demo | back | 142.1 x 118.0 | rejected: tinytapeout-demo-B_Cu.svg: board is about 105 x 81 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 104.6 x 81.1 mm (too large) |
| KiCad demo tinytapeout-demo | front | 142.1 x 118.0 | rejected: tinytapeout-demo-F_Cu.svg: board is about 105 x 81 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 104.6 x 81.1 mm (too large) |
| synthetic 150 x 75 mm | front | 160.0 x 85.0 | GOO OK, in corner | 150.066 x 75.060 (drawn 150.05 x 75.05) | 99.81% exact, 99.991% within 16/255, size diff +0/+0 px |
| synthetic 154 x 50 mm | front | 164.0 x 60.0 | rejected: synthetic-154x50-F_Cu.svg: board is about 154 x 50 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 154.1 x 50.0 mm (too large) |
| synthetic 60 x 100 mm | front | 70.0 x 110.0 | rejected: synthetic-60x100-F_Cu.svg: board is about 60 x 100 mm; the Mars 4 Ultra can expose at most 153.36 x 77.76 mm. |  | Inkscape: exposed area 60.0 x 100.0 mm (too large) |

Error handling:
- PASS: positive (non-negative) plot is rejected with: "No negative-plot background found. In KiCad's Plot dialog enable 'Negative plot' (and 'Black and white') and export the SVG again."
- PASS: not an SVG is rejected with: "pcb2goo.py is not a valid SVG file (not well-formed (invalid token): line 1, column 1)."

**0 failure(s)**
exit=0
