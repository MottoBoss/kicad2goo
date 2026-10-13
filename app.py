#!/usr/bin/env python3
"""One-window GUI: pick KiCad F.Cu / B.Cu SVGs, click Convert, get Mars 4 Ultra .goo files."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

import pcb2goo

PREVIEW = (pcb2goo.RES_X // 20, pcb2goo.RES_Y // 20)  # 426 x 216


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('KiCad SVG → Elegoo Mars 4 Ultra GOO')
        self.resizable(False, False)
        self.front, self.back, self.out = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.exposure = tk.DoubleVar(value=10.0)
        self.result = None

        f = ttk.Frame(self, padding=12)
        f.grid(sticky='nsew')
        rows = [('Front SVG (F.Cu):', self.front, lambda: self.pick_svg(self.front)),
                ('Back SVG (B.Cu, optional):', self.back, lambda: self.pick_svg(self.back)),
                ('Output folder:', self.out, self.pick_out)]
        for r, (label, var, cmd) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky='w', pady=3)
            ttk.Entry(f, textvariable=var, width=70).grid(row=r, column=1, columnspan=2, sticky='we', padx=6)
            ttk.Button(f, text='Browse…', command=cmd).grid(row=r, column=3)
        ttk.Label(f, text='Bottom-layer exposure (s):').grid(row=3, column=0, sticky='w', pady=3)
        ttk.Spinbox(f, from_=1, to=120, increment=0.5, textvariable=self.exposure, width=8).grid(
            row=3, column=1, sticky='w', padx=6)
        self.button = ttk.Button(f, text='Convert', command=self.convert)
        self.button.grid(row=3, column=3, sticky='e', pady=6)

        self.status = tk.Label(f, text='Select the SVGs exported from KiCad (File → Plot → SVG).',
                               anchor='w', justify='left', wraplength=860)
        self.status.grid(row=4, column=0, columnspan=4, sticky='we', pady=(6, 8))

        self.previews = {}
        for c, side in enumerate(('front', 'back')):
            box = ttk.LabelFrame(f, text=f'{side.title()} — printer image', padding=4)
            box.grid(row=5, column=2 * c, columnspan=2, padx=(0, 6 * (1 - c)))
            self.previews[side] = tk.Label(box, bg='black')
            self.previews[side].grid()
            self.show(side, None)
        ttk.Label(f, text='Previews show the whole 153.36 × 77.76 mm LCD as stored in the .goo file '
                          '(white = exposed copper).', foreground='gray').grid(
            row=6, column=0, columnspan=4, sticky='w', pady=(4, 0))

    def show(self, side, frame):
        img = Image.new('L', PREVIEW) if frame is None else Image.fromarray(frame).resize(PREVIEW, Image.BOX)
        label = self.previews[side]
        label.image = ImageTk.PhotoImage(img)  # keep a reference or Tk shows nothing
        label.config(image=label.image)

    def pick_svg(self, var):
        path = filedialog.askopenfilename(filetypes=[('KiCad SVG', '*.svg'), ('All files', '*.*')])
        if path:
            var.set(path)
            if not self.out.get():
                self.out.set(str(Path(path).parent))

    def pick_out(self):
        path = filedialog.askdirectory()
        if path:
            self.out.set(path)

    def say(self, text, color='black'):
        self.status.config(text=text, fg=color)

    def convert(self):
        try:
            exposure = float(self.exposure.get())
            if not 0 < exposure <= 600:
                raise ValueError
        except (tk.TclError, ValueError):
            return self.say('Bottom-layer exposure must be a number of seconds (e.g. 10).', 'red')
        if not self.front.get() and not self.back.get():
            return self.say('Select at least one SVG.', 'red')
        if 'b_cu' in Path(self.front.get()).name.lower() or 'f_cu' in Path(self.back.get()).name.lower():
            return self.say('Front and back look swapped: Front must be the F_Cu SVG, Back the B_Cu SVG.', 'red')
        out = self.out.get() or str(Path(self.front.get() or self.back.get()).parent)
        if not Path(out).is_dir():
            return self.say(f'Output folder does not exist: {out}', 'red')
        self.button.state(['disabled'])
        self.say('Converting… (10–60 s per side, depending on board size)', 'blue')

        def work():
            try:
                self.result = pcb2goo.convert(self.front.get() or None, self.back.get() or None, out, exposure)
            except Exception as e:  # shown to the user, nothing else to do with it
                self.result = e
        self.result = None
        threading.Thread(target=work, daemon=True).start()
        self.after(200, self.poll)

    def poll(self):
        if self.result is None:
            return self.after(200, self.poll)
        self.button.state(['!disabled'])
        if isinstance(self.result, Exception):
            return self.say(f'Error: {self.result}', 'red')
        lines = []
        for side in ('front', 'back'):
            path, frame = self.result.get(side, (None, None))
            self.show(side, frame)
            if path:
                lines.append(f'    {path.name}   ({side})')
                folder = path.parent
        self.say(f'Done. Saved in {folder}:\n' + '\n'.join(lines), 'green4')


if __name__ == '__main__':
    App().mainloop()
