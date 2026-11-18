import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import subprocess
from collections import deque
import time

import cv2
import numpy as np
import onnxruntime as ort
import vgamepad as vg
import threading
from windows_capture import DxgiDuplicationSession

ROI = (640, 145, 1280, 785)
SIZE = 640
CX = 320.0
CY = 395.0
FOV_R = 240
DBG_X = 1490
DBG_Y = 523
KNOCK_AR = 1.15
KNOCK_P = 1.8
HEAD_T = 0.10
HEAD_B = 0.30
SIDE_L = 0.38
SIDE_R = 0.62
UP_HIP = 316
DN_HIP = 196
UP_ADS = 112
DN_ADS = 120
R_ADS = 144
AIM_Y = 0.50
GAIN_FAR = 1.64
GAIN_NEAR = 0.87
KDF = 0.6
CY_OFF = 316
RGB8 = np.empty((SIZE, SIZE, 3), np.uint8)
BLOB = np.empty((1, 3, SIZE, SIZE), np.float32)
ADS_G = 1.0
DEAD = 4.0
TRIG = 20
SA = 0.55
FAR_A = 2500
FAR_MULT = 0.70
LOCK_MODE = 1
SH_SA = 0.15
HYST = 16.0
RECOIL = 1.3
JIT = 0.045
JIT_FR = 2
JST = [1.0, 0]
JON = [1]
JP = [False]
JADD = [0.0]
JD = [False, False]
MIN_OUT = 0.10
SMOOTH = 0.69
KI = 0.12
KD = 0.38
PLAYER_CUT = 0.3
PUSH_R = 0.70
SWITCH_R = 0.6
SW_HOLD = 3
CONF = 0.32
IOU = 0.40
MODEL = "apex_detect_v8n_v2.1.onnx"
ENABLED = 1
ACT_MODE = 0
CFG = "cfg.json"

KEYS = ["FOV_R", "KNOCK_AR", "KNOCK_P", "HEAD_T", "HEAD_B", "SIDE_L", "SIDE_R", "DBG_X", "DBG_Y", "UP_HIP", "DN_HIP", "UP_ADS", "DN_ADS", "R_ADS", "AIM_Y",
        "GAIN_FAR", "GAIN_NEAR", "ADS_G", "DEAD", "TRIG", "MIN_OUT", "SMOOTH",
        "KI", "KD", "KDF", "PLAYER_CUT", "PUSH_R", "SWITCH_R", "SW_HOLD", "CONF", "IOU", "SA", "SH_SA", "HYST", "FAR_A", "FAR_MULT", "LOCK_MODE", "RECOIL", "JIT", "JIT_FR", "ACT_MODE"]

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)
xi = ctypes.WinDLL("xinput1_4")

PROCS = {"r5apex.exe", "r5apex_dx12.exe", "r5apex_dx11.exe"}


class XS(ctypes.Structure):
    _fields_ = [("pkt", ctypes.c_uint), ("btn", ctypes.c_ushort),
                ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                ("lx", ctypes.c_short), ("ly", ctypes.c_short),
                ("rx", ctypes.c_short), ("ry", ctypes.c_short)]


BTN = [(0x1000, vg.XUSB_BUTTON.XUSB_GAMEPAD_A), (0x2000, vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
       (0x4000, vg.XUSB_BUTTON.XUSB_GAMEPAD_X), (0x8000, vg.XUSB_BUTTON.XUSB_GAMEPAD_Y),
       (0x0100, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER),
       (0x0200, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER),
       (0x0020, vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK), (0x0010, vg.XUSB_BUTTON.XUSB_GAMEPAD_START),
       (0x0040, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB),
       (0x0080, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB),
       (0x0001, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP),
       (0x0002, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN),
       (0x0004, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT),
       (0x0008, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)]


def load_cfg():
    g = globals()
    if not os.path.exists(CFG):
        json.dump({k: g[k] for k in KEYS}, open(CFG, "w", encoding="utf-8"), indent=2)
        print("cfg.json を作成しました")
        return
    try:
        with open(CFG, encoding="utf-8-sig") as fp:
            d = json.load(fp)
        for k, v in d.items():
            if k in g and k != "ENABLED":
                try:
                    g[k] = v if isinstance(g[k], str) else (float(v) if isinstance(g[k], float) else int(v))
                except (TypeError, ValueError):
                    print("cfg type error", k, v)
        print("cfg.json を読み込みました")
    except Exception as e:
        print("cfg.json 読み込み失敗:", e)


def dpi():
    try:
        shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()


def _pid(hwnd):
    p = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


def _exe(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        b = ctypes.create_unicode_buffer(512)
        n = wt.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, b, ctypes.byref(n)):
            return os.path.basename(b.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if w > 800 and h > 400 and _exe(_pid(hwnd)) in PROCS:
            found.append((w * h, hwnd))
        return True

    user32.EnumWindows(cb, 0)
    return max(found)[1] if found else None



def clamp(v):
    if v != v:
        return 0
    return max(-32768, min(32767, int(round(v))))


def state(i):
    s = XS()
    return s if xi.XInputGetState(i, ctypes.byref(s)) == 0 else None


def identify(pad):
    time.sleep(0.8)
    pad.right_joystick(x_value=30000, y_value=0)
    pad.update()
    hits = [0, 0, 0, 0]
    for _ in range(12):
        time.sleep(0.1)
        pad.update()
        for i in range(4):
            s = state(i)
            if s is not None and s.rx > 25000:
                hits[i] += 1
    print("hits", hits)
    mine = hits.index(max(hits)) if max(hits) >= 3 else 0
    others = [i for i in range(4) if i != mine and state(i) is not None]
    pad.right_joystick(x_value=0, y_value=0)
    pad.update()
    return mine, others


def activity(s):
    return (abs(s.lx) + abs(s.ly) + abs(s.rx) + abs(s.ry)
            + s.lt + s.rt + (1 if s.btn else 0))


ACT_LAST = [0.0]
ACT_DBL = [0.0]


def act_ok(st):
    if not ENABLED:
        return False
    if ACT_MODE == 1:
        return st.rt > TRIG and st.lt > TRIG
    if ACT_MODE == 2:
        return st.rt > TRIG and st.lt <= TRIG
    if ACT_MODE == 3:
        return st.rt > 200
    if ACT_MODE == 4:
        return ACT_DBL[0] > 0.0 and st.rt > TRIG
    if ACT_MODE == 5:
        return st.lt > TRIG
    if ACT_MODE == 6:
        return st.rt > TRIG or st.lt > TRIG
    return st.rt > TRIG


def choose(mine):
    best, score = None, 0
    for i in range(3, -1, -1):
        if i == mine:
            continue
        s = state(i)
        if s is None:
            continue
        sc = activity(s)
        if sc > score:
            best, score = i, sc
    if best is not None:
        return best
    for i in range(3, -1, -1):
        if i != mine and state(i) is not None:
            return i
    return None


class Tracker:
    def __init__(self):
        self.t = []
        self.n = 0

    @staticmethod
    def iou(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0, min(ay + ah, by + bh) - max(ay, by))
        i = ix * iy
        u = aw * ah + bw * bh - i
        return i / u if u > 0 else 0.0

    def update(self, boxes):
        for o in self.t:
            o["age"] += 1
        for b in boxes:
            best, bi = 0.0, -1
            for i, o in enumerate(self.t):
                v = self.iou(b, o["box"])
                if v > best:
                    best, bi = v, i
            if best > 0.3:
                self.t[bi]["box"] = b
                self.t[bi]["age"] = 0
            else:
                self.n += 1
                self.t.append({"id": self.n, "box": b, "age": 0})
        self.t = [o for o in self.t if o["age"] <= 5]
        return self.t


def pick(tracks, locked=None):
    best, bs = None, -1e9
    for o in tracks:
        if o["age"] > 2:
            continue
        x, y, w, h = o["box"]
        cx, cy = x + w / 2, y + h / 2
        d = ((cx - CX) ** 2 + ((cy - CY) * 1.4) ** 2) ** 0.5
        if d > FOV_R:
            continue
        if w > h * KNOCK_AR:
            d *= KNOCK_P
        s = -d + min(w * h, 40000) * 0.0006
        if o["id"] == locked:
            s += 25.0
        if w > 0:
            ar = h / w
            if 1.2 <= ar <= 4.5:
                s += 12.0
        if s > bs:
            best, bs = o, s
    return best


def merge(boxes):
    keep = []
    for x, y, w, h in sorted(boxes, key=lambda b: -(b[2] * b[3])):
        cx, cy = x + w / 2, y + h / 2
        for X, Y, Wd, Hd in keep:
            if X <= cx <= X + Wd and Y <= cy <= Y + Hd:
                break
        else:
            keep.append((x, y, w, h))
    return keep


def decode(out, conf):
    o = out[0]
    sc = o[4]
    m = sc > np.where(o[2] * o[3] < FAR_A, conf * FAR_MULT, conf)
    if not m.any():
        return []
    j = np.flatnonzero(m)
    if j.size > 32:
        j = j[np.argpartition(-sc[j], 32)[:32]]
    b = o[:4, j]
    cx, cy, bw, bh = b[0], b[1], b[2], b[3]
    boxes = np.stack([cx - bw * 0.5, cy - bh * 0.5, bw, bh], 1).astype(np.float32)
    idx = cv2.dnn.NMSBoxes(np.ascontiguousarray(boxes), sc[j].astype(np.float32), conf, IOU)
    if not len(idx):
        return []
    return merge(boxes[np.array(idx).flatten()].tolist())


def gate(boxes, ads):
    r = R_ADS if ads else FOV_R
    up = UP_ADS if ads else UP_HIP
    dn = DN_ADS if ads else DN_HIP
    keep = []
    for x, y, w, h in boxes:
        cx = x + w / 2
        cy = y + h / 2
        if cy < CY - up or cy > CY + dn:
            continue
        if ((cx - CX) ** 2 + (cy - CY) ** 2) ** 0.5 > r:
            continue
        keep.append([x, y, w, h])
    return keep


def min_console():
    u = ctypes.windll.user32
    for cls in ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"):
        h = u.FindWindowW(cls, None)
        if h:
            u.ShowWindow(h, 6)
            u.PostMessageW(h, 0x0112, 0xF020, 0)
def res(name):
    for base in (getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()):
        if base:
            q = os.path.join(base, name)
            if os.path.exists(q):
                return q
    return name

if getattr(sys, "frozen", False):
    try:
        _lp = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'apexai.log')
        try:
            if os.path.getsize(_lp) > 2000000:
                os.replace(_lp, _lp + '.old')
        except Exception:
            pass
        _lg = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "apexai.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = _lg
        sys.stderr = _lg
        print("--- start", time.strftime("%H:%M:%S"))
    except Exception:
        pass


if len(sys.argv) > 1 and sys.argv[1] == "tune":
    try:
        exec(compile(open(res("tune.py"), encoding="utf-8").read(), "tune.py", "exec"))
    except Exception as e:
        print("tune error:", e)
    sys.exit()


def main():
    global ENABLED, CX, CY, BLOB
    kernel32.CreateMutexW(None, False, ctypes.c_wchar_p("APEXAI_SINGLE"))
    if kernel32.GetLastError() == 183:
        print("既に起動しています")
        return 0
    dpi()
    cv2.setNumThreads(1)
    load_cfg()
    pad = vg.VX360Gamepad()
    mine, _ = identify(pad)
    if mine is None:
        mine = 0
    print("仮想パッド", mine)
    if mine != 0:
        print("!! 仮想パッドがスロット0にいません。パッドを抜いて起動し直してください")
    idx = choose(mine)
    print("入力パッド", idx)
    import keyboard
    hwnd = None
    for _w in range(360):
        if keyboard.is_pressed("esc"):
            print("中止")
            return 0
        hwnd = find_window()
        if hwnd is not None:
            break
        n2 = choose(mine)
        if n2 != idx:
            idx = n2
            print("入力パッド", idx)
        time.sleep(0.5)
    if hwnd is None:
        print("Apex が見つかりません")
        return 2

    so = ort.SessionOptions()
    so.enable_mem_pattern = False
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    sess = ort.InferenceSession(res(MODEL), so,
                                providers=[("DmlExecutionProvider", {"device_id": 0, "disable_cpu_ep_fallback": "1"})])
    inp = sess.get_inputs()[0].name

    def refine(a, box, ox, oy):
        bx, by, bw, bh = box
        cx = int(bx + bw * 0.5) + ox
        cy = int(by + bh * 0.5) + oy
        r = SIZE // 4
        sx = max(0, min(a.shape[1] - 2 * r, cx - r))
        sy = max(0, min(a.shape[0] - 2 * r, cy - r))
        c = a[sy:sy + 2 * r, sx:sx + 2 * r]
        if c.shape[0] != 2 * r or c.shape[1] != 2 * r:
            return None
        sm = cv2.resize(c, (SIZE, SIZE))
        cv2.cvtColor(sm, cv2.COLOR_BGRA2RGB, dst=RGB8)
        np.multiply(RGB8.transpose(2, 0, 1), 0.00392156862745098, out=BLOB[0], casting="unsafe")
        bs = decode(sess.run(None, {inp: BLOB})[0], CONF * 0.7)
        if not bs:
            return None
        mid = SIZE * 0.5
        best, bd = None, 1e9
        for x, y, w, h in bs:
            dd = ((x + w * 0.5 - mid) ** 2 + (y + h * 0.5 - mid) ** 2) ** 0.5
            if dd < bd:
                best, bd = (x, y, w, h), dd
        if best is None or bd > SIZE * 0.35:
            return None
        x, y, w, h = best
        return (x * 0.5 + sx - ox, y * 0.5 + sy - oy, w * 0.5, h * 0.5)


    if mine is None:
        print("!! ViGEm のパッドが XInput に出ていません")

    cam = DxgiDuplicationSession(None)
    tr = Tracker()
    x1, y1, x2, y2 = ROI

    ei = eiy = edf = prevex = 0.0
    axs = ays = 0.0
    locked = None
    tctl = 0.0
    hold_box = None
    hold_t = 0.0 
    prev = 0
    prev_rt = False
    sw_id = None
    sw_n = 0
    o_prev = False
    last = XS()
    dead = 0 
    n = 0
    nprev = 0
    tp = time.perf_counter()
    lat = deque(maxlen=60)
    mx = deque(maxlen=120)
    ovr = [0]
    paxs = [0.0]
    lc = deque(maxlen=60)
    lp = deque(maxlen=60)
    li = deque(maxlen=60)
    lo = deque(maxlen=60)
    lf = deque(maxlen=60)
    did = False
    prev_sig = b""
    sx = sy = sw = sh = 0.0
    sm_id = None
    last_dir = 0
    tracks = []

    tune = None
    try:
        tune = subprocess.Popen([sys.executable, "tune"] if getattr(sys, "frozen", False) else [sys.executable, "tune.py"])
    except Exception:
        pass

    mt = 0.0
    try:
        mt = os.path.getmtime(CFG)
    except Exception:
        pass
    if SHOW_DBG: cv2.namedWindow("dbg", cv2.WINDOW_NORMAL)
    if SHOW_DBG: cv2.setWindowProperty("dbg", cv2.WND_PROP_TOPMOST, 1)
    if SHOW_DBG: cv2.resizeWindow("dbg", 400, 400)
    if SHOW_DBG: cv2.moveWindow("dbg", DBG_X, DBG_Y)
    time.sleep(0.3)
    user32.SetForegroundWindow(hwnd)
    min_console()
    hc = kernel32.GetConsoleWindow()
    if hc:
        user32.SetWindowPos(hc, 0, 0, 150, 600, 560, 0x0040)
        min_console()

    print("Esc で終了")

    min_console()
    try:
        while True:
            try:
                nm = os.path.getmtime(CFG)
            except Exception:
                nm = mt
            if nm != mt:
                mt = nm
                load_cfg()
                print("\ncfg applied")
                if SHOW_DBG: cv2.moveWindow("dbg", DBG_X, DBG_Y)
            import keyboard
            if keyboard.is_pressed("esc"):
                break
            op = keyboard.is_pressed("o")
            if op and not o_prev:
                ENABLED = 1 - ENABLED
                print("\n" + ("ON" if ENABLED else "OFF"))
            o_prev = op

            st = state(idx) if idx is not None else None
            if st is None:
                idx = choose(mine)
                prev = 0
                st = state(idx) if idx is not None else None
                if st is None:
                    dead += 1
                    st = XS() if dead > 20 else last
                else:
                    dead = 0
            last = st
            on_rt = st.rt > TRIG
            if on_rt and not prev_rt:
                tn = time.perf_counter()
                if tn - ACT_LAST[0] < 0.30:
                    ACT_DBL[0] = 1.0
                ACT_LAST[0] = tn
            elif not on_rt:
                ACT_DBL[0] = 0.0
            prev_rt = on_rt

            if st.btn != prev:
                for mask, btn in BTN:
                    on = st.btn & mask
                    if on and not prev & mask:
                        pad.press_button(button=btn)
                    elif not on and prev & mask:
                        pad.release_button(button=btn)
                prev = st.btn
            pad.left_joystick(x_value=st.lx, y_value=st.ly)
            pad.left_trigger(value=st.lt)
            pad.right_trigger(value=st.rt)

            rx, ry = st.rx, st.ry
            t0 = time.perf_counter()
            try:
                f = cam.acquire_frame(timeout_ms=1)
            except Exception:
                f = None
            ta = time.perf_counter()
            if f is None:
                pad.right_joystick(x_value=rx, y_value=ry)
                pad.update()
                time.sleep(0.001)
                continue

            a = f.to_numpy()
            fh, fw = a.shape[:2]
            if fw < SIZE or fh < SIZE:
                pad.right_joystick(x_value=rx, y_value=ry)
                pad.update()
                continue
            x1 = min(max(0, fw // 2 - SIZE // 2), fw - SIZE)
            y1 = min(max(0, fh // 2 - CY_OFF), fh - SIZE)
            CX = fw // 2 - x1
            CY = fh // 2 - y1
            roi = a[y1:y1 + SIZE, x1:x1 + SIZE]
            ads = st.lt > TRIG
            sig = a[y1 + 8, x1:x1 + SIZE].tobytes() + a[y1 + SIZE - 8, x1:x1 + SIZE].tobytes()
            ta = time.perf_counter()
            if roi is None:
                pad.right_joystick(x_value=rx, y_value=ry)
                pad.update()
                time.sleep(0.0005)
                continue
            ads = st.lt > TRIG
            sig = roi[8].tobytes() + roi[SIZE - 8].tobytes()
            if sig != prev_sig:
                prev_sig = sig
                tb = time.perf_counter()
                cv2.cvtColor(roi, cv2.COLOR_BGRA2RGB, dst=RGB8)
                np.multiply(RGB8.transpose(2, 0, 1), 0.00392156862745098, out=BLOB[0], casting="unsafe")
                tc = time.perf_counter()
                out = sess.run(None, {inp: BLOB})[0]
                td = time.perf_counter()
                tracks = tr.update(gate(decode(out, CONF), ads))
                did = True

            tgt = None
            if act_ok(st):
                cur = None
                if locked is not None:
                    for o in tracks:
                        if o["id"] == locked and o["age"] <= 3:
                            cur = o
                            break
                if cur is not None:
                    cand = pick(tracks, locked)
                    if cand is not None and cand["id"] != cur["id"]:
                        xc, yc, wc, hc2 = cur["box"]
                        xn, yn, wn, hn = cand["box"]
                        dc = ((xc + wc / 2 - CX) ** 2 + (yc + hc2 / 2 - CY) ** 2) ** 0.5
                        dn = ((xn + wn / 2 - CX) ** 2 + (yn + hn / 2 - CY) ** 2) ** 0.5
                        sw = dn < dc * SWITCH_R
                        if sw and dn > dc * 0.20 and (wn * hn) < (wc * hc2) * 0.55:
                            sw = False
                        if not sw and (yn + hn) > (yc + hc2) + 32 and dn < 176:
                            sw = True
                        if sw:
                            if cand["id"] == sw_id:
                                sw_n += 1
                            else:
                                sw_id, sw_n = cand["id"], 1
                            if sw_n < SW_HOLD:
                                sw = False
                        else:
                            sw_id, sw_n = cand["id"], 0
                        if LOCK_MODE:
                            sw = False
                        if sw:
                            cur = cand
                            locked = cand["id"] 
                            ei = eiy = edf = prevex = 0.0
                    tgt = cur
                else:
                    tgt = pick(tracks, locked)
                    if tgt is not None:
                        locked = tgt["id"]
                        ei = eiy = edf = prevex = 0.0
            else:
                locked = None

            if tgt is not None and n % 2 == 0 and tgt["box"][2] * tgt["box"][3] < FAR_A:
                nb = refine(a, tgt["box"], x1, y1)
                if nb is not None:
                    tgt = dict(tgt)
                    tgt["box"] = nb
            tnow = time.perf_counter()
            ex = ey = d = 0.0
            box = None
            if tgt is not None:
                hold_box = tgt["box"]
                hold_t = time.perf_counter()
                box = hold_box
            elif act_ok(st) and hold_box is not None and time.perf_counter() - hold_t < 0.15:
                box = hold_box
            if box is not None:
                x, y, w, h = box
                if locked != sm_id:
                    sm_id = locked
                    sx, sy, sw, sh = x, y, w, h
                    prevex = sx + sw * 0.5
                else:
                    sx += (x - sx) * SA
                    sy += (y - sy) * SA
                    sw += (w - sw) * SH_SA
                    sh += (h - sh) * SH_SA
                x, y, w, h = sx, sy, sw, sh
                ex = (x + w / 2) - CX
                l0 = x + w * min(SIDE_L, SIDE_R)
                l1 = x + w * max(SIDE_L, SIDE_R)
                if CX < l0:
                    ex = l0 - CX
                elif CX > l1:
                    ex = l1 - CX
                else:
                    ex = 0.0
                tb0 = y + h * min(HEAD_T, HEAD_B)
                tb1 = y + h * max(HEAD_T, HEAD_B)
                if CY < tb0:
                    ey = tb0 - CY
                elif CY > tb1:
                    ey = tb1 - CY
                else:
                    ey = 0.0
                exh = ex
                if exh > 0.0:
                    exh = max(0.0, exh - HYST)
                elif exh < 0.0:
                    exh = min(0.0, exh + HYST)
                d = (exh * exh + ey * ey) ** 0.5
                mx.append(abs(ex))
                vx = (sx + sw * 0.5) - prevex
                prevex = sx + sw * 0.5
                edf = edf * KDF + vx * (1 - KDF)
                if d > DEAD:
                    if exh != 0.0:
                        nd = 1 if exh > 0 else -1
                        if last_dir != 0 and nd != last_dir:
                            ei = 0.0
                            edf = 0.0
                        last_dir = nd
                    g = GAIN_NEAR + (GAIN_FAR - GAIN_NEAR) * min(1.0, d * 0.005)
                    if ads:
                        g *= ADS_G
                    gv = g * RECOIL if ey > 0.0 else g
                    ei = max(-1000.0, min(1000.0, ei * 0.85 + exh))
                    eiy = max(-1000.0, min(1000.0, eiy * 0.85 + ey))
                    ax = float(np.clip(g * (exh + KI * ei + KD * edf) / CX, -1, 1))
                    ay = float(np.clip(-gv * (ey + KI * eiy) / CY, -1, 1))
                    axs = axs * (1 - SMOOTH) + ax * SMOOTH
                    if axs * paxs[0] < 0:
                        ovr[0] += 1
                    paxs[0] = axs
                    ays = ays * (1 - SMOOTH) + ay * SMOOTH
                    m = max(abs(rx), abs(ry)) / 32767.0
                    push = min(max(PUSH_R, 0.0), 0.999)
                    if PLAYER_CUT and m > push:
                        f2 = 1.0 - PLAYER_CUT * min(1.0, (m - push) / (1.0 - push))
                        axs *= f2
                        ays *= f2
                    if abs(axs) < MIN_OUT:
                        axs = MIN_OUT * (1 if axs > 0 else (-1 if axs < 0 else 0))
                    if abs(ays) < MIN_OUT:
                        ays = MIN_OUT * (1 if ays > 0 else (-1 if ays < 0 else 0))
                    if tnow >= tctl:
                        tctl = tnow + 0.004166
                        rx = clamp(rx + axs * 32767)
                        ry = clamp(ry + ays * 32767)
            else:
                axs = ays = 0.0

            if keyboard.is_pressed("f11"):
                if not JP[0]:
                    JP[0] = True
                    JON[0] = 0 if JON[0] else 1
                    print("\njit ", "ON" if JON[0] else "OFF")
            else:
                JP[0] = False
            if keyboard.is_pressed("f8"):
                rx, ry = 20000, 20000
            jo = 0
            if keyboard.is_pressed("f10"):
                if not JD[0]:
                    JD[0] = True
                    JADD[0] = round(JADD[0] + 0.02, 3)
                    print("\njit ", round(JIT + JADD[0], 3))
            else:
                JD[0] = False
            if keyboard.is_pressed("f9"):
                if not JD[1]:
                    JD[1] = True
                    JADD[0] = round(JADD[0] - 0.02, 3)
                    print("\njit ", round(JIT + JADD[0], 3))
            else:
                JD[1] = False
            jv = JIT + JADD[0]
            if jv > 0.0 and JON[0] and st.rt > TRIG and ads:
                JST[1] += 1
                if JST[1] >= max(1, int(JIT_FR)):
                    JST[1] = 0
                    JST[0] = -JST[0]
                jo = JST[0] * jv * 32767
            pad.right_joystick(x_value=clamp(rx + jo), y_value=ry)
            pad.update()
            t1 = time.perf_counter()
            ms = (t1 - t0) * 1000
            lat.append(ms)
            if n % 1000 == 0:
                try:
                    print("m lat=%.1f avg=%.1f cy=%.0f y1=%d co=%d fh=%d" % (ms, sum(lat) / len(lat), CY, y1, CY_OFF, fh))
                    with open("latency.log", "a", encoding="utf-8") as lg:
                        lg.write("%s lat=%.1f avg=%.1f inf=%.1f cap=%.1f conv=%.1f tgt=%d" % (time.strftime("%H:%M:%S"), ms, sum(lat) / len(lat), lf[-1] if lf else 0, lc[-1] if lc else 0, li[-1] if li else 0, 1 if tgt else 0))
                except Exception:
                    pass
            if did:
                lc.append((ta - t0) * 1000)
                lp.append((tb - ta) * 1000)
                li.append((tc - tb) * 1000)
                lf.append((td - tc) * 1000)
                lo.append((t1 - td) * 1000)
                did = False

            if SHOW_DBG and n % 3 == 0:
                vis = cv2.cvtColor(roi, cv2.COLOR_BGRA2BGR)
                vh, vw = vis.shape[:2]
                cv2.circle(vis, (int(CX), int(CY)), int(FOV_R), (150, 110, 40), 1)
                cv2.line(vis, (int(CX) - 7, int(CY)), (int(CX) + 7, int(CY)), (200, 200, 200), 1)
                cv2.line(vis, (int(CX), int(CY) - 7), (int(CX), int(CY) + 7), (200, 200, 200), 1)
                for o in tracks:
                    bx, by, bw, bh = [int(v) for v in o["box"]]
                    hit = bool(tgt) and o["id"] == tgt["id"]
                    col = (255, 220, 40) if hit else (120, 120, 120)
                    l = max(4, min(10, bw // 4, bh // 4))
                    cv2.line(vis, (bx, by), (bx + l, by), col, 1)
                    cv2.line(vis, (bx, by), (bx, by + l), col, 1)
                    cv2.line(vis, (bx + bw, by), (bx + bw - l, by), col, 1)
                    cv2.line(vis, (bx + bw, by), (bx + bw, by + l), col, 1)
                    cv2.line(vis, (bx, by + bh), (bx + l, by + bh), col, 1)
                    cv2.line(vis, (bx, by + bh), (bx, by + bh - l), col, 1)
                    cv2.line(vis, (bx + bw, by + bh), (bx + bw - l, by + bh), col, 1)
                    cv2.line(vis, (bx + bw, by + bh), (bx + bw, by + bh - l), col, 1)
                if tgt:
                    tx, ty, tw, th = tgt["box"]
                    px, py = int(tx + tw / 2), int(ty + th * AIM_Y)
                    cv2.line(vis, (int(CX), int(CY)), (px, py), (150, 110, 40), 1)
                    cv2.circle(vis, (px, py), 2, (60, 60, 255), -1)
                if len(lat) > 60:
                    lat.pop(0)
                cv2.putText(vis, f"{ms:.0f}ms {sum(lat)/len(lat):.1f}", (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
                cv2.putText(vis, f"C{CONF:.2f} F{int(FOV_R)}", (vw - 86, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
                cv2.putText(vis, f"d{d:.0f} ax{axs:.1f} ay{ays:.1f} a{int(act_ok(st))}", (6, vh - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                cv2.putText(vis, "SANDY", (vw - 52, vh - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 110, 40), 1)
                cv2.putText(vis, f"e{(sum(mx)/len(mx) if mx else 0):.0f} ov{ovr[0]}", (6, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(vis, "ON" if ENABLED else "OFF", (int(CX) - 14, vh - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0) if ENABLED else (0, 0, 255), 1)
                cv2.imshow("dbg", vis)
                cv2.waitKey(1)

            n += 1
            if time.perf_counter() - tp > 1.0:
                tp = time.perf_counter()
                cur_n = n - nprev
                nprev = n
                ov_now = ovr[0]
                ovr[0] = 0
                br = ""
                if lc:
                    br = " cap=%.1f pre=%.1f conv=%.1f inf=%.1f post=%.1f" % (sum(lc) / len(lc), sum(lp) / len(lp), sum(li) / len(li), sum(lf) / len(lf), sum(lo) / len(lo))
                    lc.clear(); lp.clear(); li.clear(); lf.clear(); lo.clear()
                print(f"  {cur_n}fps tgt={'Y' if tgt else 'N'} idx={idx} rt={st.rt} lt={st.lt} ON={ENABLED}{br}", end="\r")
    except KeyboardInterrupt:
        pass
    finally:
        if tune is not None:
            tune.terminate()
        pad.reset()
        pad.update()
        cv2.destroyAllWindows()
        print("\n終了")
    return 0


if __name__ == "__main__":
    main()