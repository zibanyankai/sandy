import json, os, time, tkinter as tk

CFG = "cfg.json"
BASE = os.path.dirname(os.path.abspath(__file__))
CFGP = os.path.join(BASE, CFG)

BG = "#0e0b1a"
SURF = "#171233"
INSET = "#0b0916"
RAISE = "#241d4d"
BORDER = "#352c5e"
TXT = "#f2f0f8"
LBL = "#9a92b8"
DIM = "#5d5480"
ACC = "#fcee0a"
DARK = "#0d0221"
FONT = "Yu Gothic UI"
MONO = "Consolas"

def mix(a, b, t):
    a = a.lstrip("#")
    b = b.lstrip("#")
    r = [int(a[i:i+2], 16) + (int(b[i:i+2], 16) - int(a[i:i+2], 16)) * t for i in (0, 2, 4)]
    return "#" + "".join("%02x" % int(v) for v in r)

root = tk.Tk()
root.title("SANDY")
root.geometry("420x404+8+40")
root.configure(bg=BG)
root.attributes("-topmost", True)
root.overrideredirect(True)
root.attributes("-alpha", 0.0)

def fade(w, a, b, steps=7, ms=16):
    def step(i):
        if i > steps:
            return
        try:
            w.config(bg=mix(a, b, i / steps))
        except Exception:
            return
        root.after(ms, step, i + 1)
    step(0)

def load():
    try:
        return json.load(open(CFGP, encoding="utf-8"))
    except Exception:
        return {}

data = load()

def save(*_):
    try:
        t = json.dumps(data, indent=2, ensure_ascii=False)
        open(CFGP, "w", encoding="utf-8").write(t + chr(10))
        d2 = os.path.join(BASE, "dist", "APEXAI")
        if os.path.isdir(d2):
            open(os.path.join(d2, "cfg.json"), "w", encoding="utf-8").write(t + chr(10))
    except Exception:
        pass

def press(e):
    root._x = e.x_root - root.winfo_x()
    root._y = e.y_root - root.winfo_y()

def drag(e):
    root.geometry(f"+{e.x_root - root._x}+{e.y_root - root._y}")

tk.Frame(root, bg=ACC, height=2).pack(fill="x")
hdr = tk.Frame(root, bg=BG, height=46)
hdr.pack(fill="x")
hdr.pack_propagate(False)
tk.Label(hdr, text="SANDY", bg=BG, fg=ACC, font=(MONO, 13, "bold")).pack(side="left", padx=(16, 8))
tk.Label(hdr, text="QUICK TUNE", bg=SURF, fg=LBL, font=(MONO, 7), padx=6, pady=2).pack(side="left")
tk.Button(hdr, text="✕", command=root.destroy, bg=BG, fg=DIM, relief="flat", bd=0, font=(FONT, 11), activebackground=BG).pack(side="right", padx=(0, 14))
tk.Button(hdr, text="–", command=lambda: root.iconify(), bg=BG, fg=DIM, relief="flat", bd=0, font=(FONT, 11), activebackground=BG).pack(side="right")
hdr.bind("<Button-1>", press)
hdr.bind("<B1-Motion>", drag)
tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

CELLH = 34

class Seg(tk.Frame):
    def __init__(self, master, names, cb):
        super().__init__(master, bg=INSET, highlightthickness=1, highlightbackground=BORDER)
        self.cb = cb
        self.sel = None
        self.b = {}
        self.cells = tk.Frame(self, bg=INSET)
        self.cells.pack(fill="x")
        self.ind = tk.Frame(self.cells, bg=ACC, height=2)
        for n in names:
            w = tk.Label(self.cells, text=n, bg=INSET, fg=LBL, font=(FONT, 10, "bold"), pady=9, cursor="hand2")
            w.pack(side="left", fill="x", expand=True, padx=1, pady=1)
            w.bind("<Button-1>", lambda e, q=n: self.pick(q))
            w.bind("<Enter>", lambda e, q=n: self.hov(q, True))
            w.bind("<Leave>", lambda e, q=n: self.hov(q, False))
            self.b[n] = w
        self.ind.place(x=1, y=CELLH - 3, width=1)

    def hov(self, k, on):
        if k == self.sel:
            return
        w = self.b[k]
        fade(w, INSET, RAISE) if on else fade(w, RAISE, INSET)

    def slide(self, tx, tw):
        cx = self.ind.winfo_x()
        cw = max(1, self.ind.winfo_width())
        def step(i):
            t = i / 6.0
            self.ind.place(x=int(cx + (tx - cx) * t), y=CELLH - 3, width=max(1, int(cw + (tw - cw) * t)))
            if i < 6:
                root.after(14, step, i + 1)
        step(0)

    def pick(self, k):
        names = list(self.b.keys())
        i = names.index(k)
        self.sel = k
        for q, w in self.b.items():
            w.config(fg=DARK if q == k else LBL)
        cw = max(1, self.cells.winfo_width() // max(1, len(names)))
        self.slide(i * cw + 2, cw - 4)
        self.cb(k)

    def clear(self):
        self.sel = None
        for w in self.b.values():
            w.config(fg=LBL)
        self.slide(1, 1)

PRESET = {
    "STRENGTH": {
        "弱": {"ADS_G": 1.7, "KDF": 0.08, "GAIN_NEAR": 1.0, "GAIN_FAR": 0.8, "MIN_OUT": 0.04},
        "中": {"ADS_G": 2.1, "KDF": 0.10, "GAIN_NEAR": 1.4, "GAIN_FAR": 1.0, "MIN_OUT": 0.03},
        "強": {"ADS_G": 2.5, "KDF": 0.12, "GAIN_NEAR": 1.9, "GAIN_FAR": 1.3, "MIN_OUT": 0.02},
    },
    "RANGE": {
        "狭": {"FOV_R": 70, "R_ADS": 40, "CONF": 0.55},
        "中": {"FOV_R": 85, "R_ADS": 50, "CONF": 0.50},
        "広": {"FOV_R": 110, "R_ADS": 65, "CONF": 0.45},
    },
}

body = tk.Frame(root, bg=BG)
body.pack(fill="both", expand=True, padx=14, pady=12)
card = tk.Frame(body, bg=SURF, highlightthickness=1, highlightbackground=BORDER)
card.pack(fill="x")
tk.Label(card, text="押した時点で保存されます", bg=SURF, fg=DIM, font=(FONT, 8)).pack(anchor="w", padx=14, pady=(11, 0))

vals = {}
segs = []
for kind, names in PRESET.items():
    tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(9, 0))
    top = tk.Frame(card, bg=SURF)
    top.pack(fill="x", padx=14, pady=(9, 5))
    tk.Frame(top, bg=ACC, width=4, height=4).pack(side="left", pady=(5, 0))
    tk.Label(top, text=kind, bg=SURF, fg=LBL, font=(MONO, 8, "bold")).pack(side="left", padx=7)
    v = tk.Label(top, text="", bg=INSET, fg=DIM, font=(MONO, 7), padx=6, pady=2)
    v.pack(side="right")
    def mk(k=kind):
        def f(name):
            data.update(PRESET[k][name])
            save()
            paint()
        return f
    sg = Seg(card, list(names), mk())
    sg.pack(fill="x", padx=14)
    segs.append(sg)
    vals[kind] = v

tk.Frame(card, bg=SURF, height=11).pack()

BASE_VALS = {"ADS_G": 2.1, "KDF": 0.10, "GAIN_NEAR": 1.4, "GAIN_FAR": 1.0, "MIN_OUT": 0.03, "FOV_R": 85, "R_ADS": 50, "CONF": 0.50}

def paint():
    a = vals["STRENGTH"]
    b = vals["RANGE"]
    a.config(text="G %s  K %s  N %s  F %s" % (data.get("ADS_G", 0), data.get("KDF", 0), data.get("GAIN_NEAR", 0), data.get("GAIN_FAR", 0)))
    b.config(text="FOV %s  R %s  C %s" % (data.get("FOV_R", 0), data.get("R_ADS", 0), data.get("CONF", 0)))

def reset():
    data.update(BASE_VALS)
    save()
    for w in segs:
        w.clear()
    paint()

foot = tk.Frame(root, bg=BG)
foot.pack(fill="x", padx=14, pady=(12, 14))
tk.Button(foot, text="リセット", command=reset, bg=INSET, fg=LBL, relief="flat", bd=0, font=(FONT, 9), padx=16, pady=6, activebackground=RAISE, activeforeground=TXT).pack(side="left")
tk.Button(foot, text="保存", command=save, bg=ACC, fg=DARK, relief="flat", bd=0, font=(FONT, 9, "bold"), padx=22, pady=6, activebackground=ACC).pack(side="right")

root.bind("<Escape>", lambda e: root.destroy())

paint()

def rise(i=0):
    root.attributes("-alpha", min(1.0, i / 8.0))
    if i < 8:
        root.after(18, rise, i + 1)

rise()
root.mainloop()
