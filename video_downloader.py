"""
AB Video Downloader - YouTube & TikTok (dan ratusan situs lain)
Paste link -> pratinjau (thumbnail + judul) -> download dengan animasi progress.

Dibuat dengan Tkinter (UI custom) + yt-dlp + Pillow.
Jalankan:  python video_downloader.py  [opsional: URL]
"""

import os
import re
import io
import sys
import glob
import json
import base64
import shutil
import threading
import queue
import urllib.request
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    raise SystemExit("Modul 'yt-dlp' belum terpasang. Jalankan:  pip install -U yt-dlp")

try:
    from yt_dlp.utils import DownloadCancelled
except ImportError:                      # yt-dlp lama: pakai pengecualian sendiri
    class DownloadCancelled(Exception):
        pass

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "VideoDownloader")

# ---------- Token warna (semua pasangan diverifikasi WCAG >= 4.5:1) ----------
# Tangga permukaan: BG (paling dalam) -> SURFACE (kartu) -> INSET (kolom input)
BG_TOP = "#10101F"
BG_BOT = "#07070E"
SHADOW = "#04040A"          # bayangan di bawah kartu
CARD = "#242645"            # permukaan kartu, elevasi 1.38:1 vs BG
CARD_BORDER = "#3A3D6B"     # garis tepi kartu
CARD_HILITE = "#43477A"     # hairline atas kartu (kesan cahaya dari atas)
INNER = "#0C0C18"           # kolom input (inset, lebih gelap dari kartu)

# Aksen dipisah: FILL untuk bidang (teks putih 6.4:1), TEXT untuk teks di atas gelap
ACCENT = "#6338E8"
ACCENT_HOVER = "#7048F5"
ACCENT_PRESS = "#5227D4"
ACCENT_DEEP = "#3F2596"
ACCENT_TEXT = "#A78BFA"     # 7.4:1 di atas BG
RING = "#8B6BFF"            # cincin fokus keyboard
SHIMMER = "#CBB6FF"

TEXT = "#F2F3FA"
MUTED = "#A8ABC9"
FAINT = "#8E92B4"
OK = "#4ADE80"              # ikon & teks sukses (aksen kecil)
OK_FILL = "#2E9E60"         # bidang besar: saturasi diturunkan agar tidak berteriak
ERR = "#FF8A8A"
TRACK = "#1B1D36"
PILL = "#2C2F52"
PILL_HOVER = "#373B63"
PILL_TEXT = "#C3C6E0"
BTN_SUB = "#32355C"
BTN_SUB_HOVER = "#3E4270"

FONT = "Segoe UI"                 # teks: netral, terbaca, native Windows
FONT_DISPLAY = "Bahnschrift SemiCondensed"   # judul & label panel (turunan DIN)
FONT_MONO = "Consolas"            # telemetri: persen, kecepatan, ukuran

# Skala spasi 8px (ritme konsisten)
SP_1, SP_2, SP_3, SP_4, SP_5 = 8, 16, 24, 32, 40


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def friendly_error(msg: str) -> str:
    """Ubah error teknis yt-dlp jadi kalimat yang menjelaskan langkah berikutnya.

    Pesan mentah seperti "HTTP Error 403: Forbidden" tidak memberi tahu pengguna
    apa yang harus dilakukan. Penyebab tersering justru yt-dlp yang tertinggal
    versi, karena YouTube sering mengubah sistemnya.
    """
    m = msg.lower()
    if "403" in m or "forbidden" in m:
        return ("YouTube menolak unduhan ini. Biasanya yt-dlp perlu diperbarui: "
                "jalankan  pip install -U yt-dlp  lalu build ulang aplikasi.")
    if "sign in" in m and ("age" in m or "confirm" in m):
        return "Video dibatasi usia, jadi tidak bisa diunduh tanpa login."
    if "private video" in m:
        return "Video ini privat, jadi tidak bisa diunduh."
    if "video unavailable" in m or "removed" in m or "not available" in m:
        return "Video tidak tersedia. Mungkin sudah dihapus atau dibatasi wilayah."
    if "unsupported url" in m or "no video" in m:
        return "Link ini tidak dikenali. Pastikan itu link video, bukan halaman lain."
    if any(k in m for k in ("getaddrinfo", "connection", "timed out",
                            "network", "temporary failure", "resolve")):
        return "Koneksi terputus. Periksa internet lalu coba lagi."
    if "ffmpeg" in m:
        return "Penggabungan video gagal karena ffmpeg bermasalah."
    # Tidak dikenali: tampilkan pesan aslinya, dipangkas agar muat satu baris
    clean = msg.strip()
    if clean.upper().startswith("ERROR:"):
        clean = clean[6:].strip()
    return clean if len(clean) <= 150 else clean[:149] + "\u2026"


def find_ffmpeg() -> "str | None":
    # 1. ffmpeg yang dibundel di dalam .exe (PyInstaller) — prioritas utama
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and os.path.exists(os.path.join(meipass, "ffmpeg.exe")):
        return meipass
    # 2. ffmpeg di PATH
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(exe)
    # 3. Hasil instalasi winget
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        pattern = os.path.join(local, "Microsoft", "WinGet", "Packages",
                               "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe")
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return os.path.dirname(matches[0])
    return None


FFMPEG_DIR = find_ffmpeg()


def enable_deno() -> bool:
    """Pastikan Deno (runtime JS untuk yt-dlp) tersedia di PATH.

    Membuat ekstraksi YouTube lebih cepat & stabil. Kalau tak ada, yt-dlp
    tetap jalan (hanya lebih lambat), jadi ini opsional.
    """
    if shutil.which("deno"):
        return True
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        matches = glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages",
                                         "DenoLand.Deno*", "**", "deno.exe"), recursive=True)
        if matches:
            os.environ["PATH"] = os.path.dirname(matches[0]) + os.pathsep + os.environ.get("PATH", "")
            return True
    return False


HAS_DENO = enable_deno()


def prefers_reduced_motion() -> bool:
    """Cek setelan Windows "Show animations". Kalau pengguna mematikannya,
    animasi dekoratif dilewati (padanan prefers-reduced-motion di web)."""
    try:
        import ctypes
        SPI_GETCLIENTAREAANIMATION = 0x1042
        enabled = ctypes.c_int()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0)
        return bool(ok) and enabled.value == 0
    except Exception:
        return False


REDUCED_MOTION = prefers_reduced_motion()


def resource_path(name: str) -> str:
    """Path ke file bawaan (ikon). Kompatibel dengan bundel PyInstaller (.exe)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def app_data_dir() -> str:
    """Folder untuk menyimpan preferensi (persisten, di luar bundel .exe)."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                            "VideoDownloader")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = os.path.expanduser("~")
    return base


SETTINGS_FILE = os.path.join(app_data_dir(), "settings.json")


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def round_rect_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def fmt_duration(seconds):
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def make_thumb_png_b64(raw_bytes, w, h, radius=10):
    """Ubah bytes gambar -> PNG base64, di-crop rapi + sudut membulat."""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    scale = max(w / im.width, h / im.height)
    nw, nh = max(w, int(im.width * scale)), max(h, int(im.height * scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    im = im.crop((left, top, left + w, top + h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    im.putalpha(mask)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    """Campur dua warna hex; t=0 -> c1, t=1 -> c2."""
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out(t):
    """Pelambatan di akhir, terasa natural (mirip ease-out CSS)."""
    return 1 - (1 - t) ** 3


# ---------- Ikon vektor ----------
# Digambar dari primitif Canvas, bukan emoji: warna bisa dikontrol token,
# ukuran & ketebalan garis konsisten, dan tampil sama di semua sistem.
ICON_STROKE = 2


def icon_film(c, x, y, size, color, tags=()):
    """Ikon film/video (persegi + lubang perforasi)."""
    s = size
    r = s * 0.12
    c.create_polygon(round_rect_points(x, y, x + s, y + s * 0.82, r),
                     smooth=True, outline=color, fill="", width=ICON_STROKE, tags=tags)
    hole = s * 0.11
    for i in range(3):
        ty = y + s * 0.14 + i * s * 0.26
        c.create_oval(x + s * 0.12, ty, x + s * 0.12 + hole, ty + hole,
                      outline=color, fill=color, tags=tags)
        c.create_oval(x + s - s * 0.12 - hole, ty, x + s - s * 0.12, ty + hole,
                      outline=color, fill=color, tags=tags)


def icon_music(c, x, y, size, color, tags=()):
    """Ikon nada musik (dua kepala not + tiang + palang)."""
    s = size
    head = s * 0.28
    c.create_oval(x, y + s * 0.6, x + head, y + s * 0.6 + head * 0.8,
                  outline=color, fill=color, tags=tags)
    c.create_oval(x + s * 0.58, y + s * 0.46, x + s * 0.58 + head, y + s * 0.46 + head * 0.8,
                  outline=color, fill=color, tags=tags)
    c.create_line(x + head, y + s * 0.68, x + head, y + s * 0.12,
                  fill=color, width=ICON_STROKE, tags=tags)
    c.create_line(x + s * 0.58 + head, y + s * 0.54, x + s * 0.58 + head, y,
                  fill=color, width=ICON_STROKE, tags=tags)
    c.create_line(x + head, y + s * 0.12, x + s * 0.58 + head, y,
                  fill=color, width=ICON_STROKE, tags=tags)


def icon_download(c, x, y, size, color, tags=()):
    """Ikon unduh (panah ke bawah + alas)."""
    s = size
    cx = x + s / 2
    c.create_line(cx, y, cx, y + s * 0.62, fill=color, width=ICON_STROKE + 1,
                  capstyle="round", tags=tags)
    c.create_line(cx - s * 0.26, y + s * 0.36, cx, y + s * 0.64,
                  fill=color, width=ICON_STROKE + 1, capstyle="round", tags=tags)
    c.create_line(cx + s * 0.26, y + s * 0.36, cx, y + s * 0.64,
                  fill=color, width=ICON_STROKE + 1, capstyle="round", tags=tags)
    c.create_line(x + s * 0.08, y + s * 0.92, x + s * 0.92, y + s * 0.92,
                  fill=color, width=ICON_STROKE + 1, capstyle="round", tags=tags)


def icon_search(c, x, y, size, color, tags=()):
    """Ikon cari (lingkaran + gagang)."""
    s = size
    d = s * 0.66
    c.create_oval(x, y, x + d, y + d, outline=color, fill="", width=ICON_STROKE, tags=tags)
    c.create_line(x + d * 0.82, y + d * 0.82, x + s, y + s,
                  fill=color, width=ICON_STROKE, capstyle="round", tags=tags)


def icon_folder(c, x, y, size, color, tags=()):
    """Ikon folder (siluet dengan tab di kiri atas)."""
    s = size
    pts = [
        x, y + s * 0.86,
        x, y + s * 0.20,
        x + s * 0.34, y + s * 0.20,
        x + s * 0.46, y + s * 0.36,
        x + s, y + s * 0.36,
        x + s, y + s * 0.86,
    ]
    c.create_polygon(pts, outline=color, fill="", width=ICON_STROKE,
                     joinstyle="round", tags=tags)


def icon_check(c, x, y, size, color, tags=()):
    """Ikon centang."""
    s = size
    c.create_line(x, y + s * 0.55, x + s * 0.36, y + s * 0.86,
                  fill=color, width=ICON_STROKE + 1, capstyle="round", tags=tags)
    c.create_line(x + s * 0.36, y + s * 0.86, x + s, y + s * 0.16,
                  fill=color, width=ICON_STROKE + 1, capstyle="round", tags=tags)


def icon_alert(c, x, y, size, color, tags=()):
    """Ikon peringatan/gagal (silang)."""
    s = size
    c.create_line(x, y, x + s, y + s, fill=color, width=ICON_STROKE + 1,
                  capstyle="round", tags=tags)
    c.create_line(x + s, y, x, y + s, fill=color, width=ICON_STROKE + 1,
                  capstyle="round", tags=tags)


# Glyph X dipakai untuk error maupun aksi batalkan
icon_close = icon_alert


class CanvasButton:
    """Tombol Canvas dengan transisi hover halus dan umpan balik saat ditekan.

    Tkinter tidak punya CSS transition, jadi perpindahan warna dianimasikan
    manual (~160ms, ease-out) supaya perubahan state tidak terasa mendadak.
    """

    _counter = 0
    FADE_MS = 160
    STEP_MS = 16          # ~60fps

    def __init__(self, canvas, x1, y1, x2, y2, text, command,
                 base, hover, fg, font, radius=14, press=None, icon=None):
        CanvasButton._counter += 1
        self.canvas = canvas
        self.command = command
        self.base, self.hover = base, hover
        self.press = press or mix(base, "#000000", 0.18)
        self.fg = fg
        self.enabled = True
        self.hovering = False
        self.box = (x1, y1, x2, y2)
        self.radius = radius
        self.tag = f"btn{CanvasButton._counter}"
        self._anim_job = None
        self._cur = base

        pts = round_rect_points(x1, y1, x2, y2, radius)
        self.bg = canvas.create_polygon(pts, smooth=True, fill=base, outline="",
                                        tags=(self.tag,))
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

        # Ikon vektor opsional, diletakkan di kiri teks (bukan emoji)
        self.icon_fn = icon
        self.icon_tag = f"{self.tag}_ic"
        tw = font.measure(text)
        if icon:
            isz = 16
            gap = 10
            total = isz + gap + tw
            self.icon_pos = (cx - total / 2, cy - isz / 2, isz)
            self.label = canvas.create_text(cx - total / 2 + isz + gap, cy, text=text,
                                            anchor="w", fill=fg, font=font,
                                            tags=(self.tag,))
            self._draw_icon()
        else:
            self.icon_pos = None
            self.label = canvas.create_text(cx, cy, text=text, fill=fg, font=font,
                                            tags=(self.tag,))

        for t in (self.tag, self.icon_tag):
            canvas.tag_bind(t, "<Enter>", self._enter)
            canvas.tag_bind(t, "<Leave>", self._leave)
            canvas.tag_bind(t, "<ButtonPress-1>", self._press)
            canvas.tag_bind(t, "<ButtonRelease-1>", self._release)

    # ----- ikon -----
    def _draw_icon(self):
        if not self.icon_fn or not self.icon_pos:
            return
        self.canvas.delete(self.icon_tag)
        x, y, sz = self.icon_pos
        self.icon_fn(self.canvas, x, y, sz, self.fg, tags=(self.icon_tag,))

    # ----- animasi warna -----
    def _animate_to(self, target):
        if self._anim_job:
            self.canvas.after_cancel(self._anim_job)
            self._anim_job = None
        start = self._cur
        if start == target:
            return
        if REDUCED_MOTION:
            self._cur = target
            self.canvas.itemconfig(self.bg, fill=target)
            return
        steps = max(1, self.FADE_MS // self.STEP_MS)

        def step(i=1):
            t = ease_out(i / steps)
            self._cur = mix(start, target, t)
            try:
                self.canvas.itemconfig(self.bg, fill=self._cur)
            except tk.TclError:
                return
            if i < steps:
                self._anim_job = self.canvas.after(self.STEP_MS, step, i + 1)
            else:
                self._cur = target
                self._anim_job = None

        step()

    # ----- state -----
    def _enter(self, _=None):
        self.hovering = True
        if self.enabled:
            self._animate_to(self.hover)
            self.canvas.config(cursor="hand2")

    def _leave(self, _=None):
        self.hovering = False
        if self.enabled:
            self._animate_to(self.base)
        self.canvas.config(cursor="")

    def _press(self, _=None):
        if self.enabled:
            # respons instan saat ditekan (<80ms) agar terasa responsif
            self._cur = self.press
            self.canvas.itemconfig(self.bg, fill=self.press)

    def _release(self, _=None):
        if not self.enabled:
            return
        self._animate_to(self.hover if self.hovering else self.base)
        if self.command:
            self.command()

    def set_text(self, t):
        self.canvas.itemconfig(self.label, text=t)
        if self.icon_pos:
            # jaga ikon+teks tetap terpusat saat labelnya berubah
            x1, y1, x2, y2 = self.box
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            font = tkfont.Font(font=self.canvas.itemcget(self.label, "font"))
            isz, gap = self.icon_pos[2], 10
            total = isz + gap + font.measure(t)
            self.icon_pos = (cx - total / 2, cy - isz / 2, isz)
            self.canvas.coords(self.label, cx - total / 2 + isz + gap, cy)
            self._draw_icon()

    def set_colors(self, base, hover, press=None):
        self.base, self.hover = base, hover
        self.press = press or mix(base, "#000000", 0.18)
        if self._anim_job:
            self.canvas.after_cancel(self._anim_job)
            self._anim_job = None
        self._cur = base
        self.canvas.itemconfig(self.bg, fill=base)

    def set_icon_color(self, color):
        self.fg = color
        self.canvas.itemconfig(self.label, fill=color)
        self._draw_icon()

    def set_icon(self, fn):
        """Ganti ikon tombol (mis. Download -> Batalkan)."""
        self.icon_fn = fn
        self._draw_icon()

    def set_command(self, fn):
        """Ganti aksi tombol tanpa membangun ulang bentuknya."""
        self.command = fn

    def set_enabled(self, e):
        self.enabled = e


class VideoDownloaderApp:
    W, H = 600, 738
    ML, MR = 28, 572
    CL, CR = 48, 552

    # Koordinat tiap seksi
    LINK_Y1, LINK_Y2 = 96, 182
    PV_Y1, PV_Y2 = 194, 312
    PV_TX, PV_TY, PV_TW, PV_TH = 46, 206, 160, 90
    OPT_Y1, OPT_Y2 = 324, 492
    TG_X1, TG_Y1, TG_X2, TG_Y2 = 48, 362, 268, 406
    TG_MID = (TG_X1 + TG_X2) / 2
    Q_Y1, Q_Y2 = 444, 474
    FD_Y1, FD_Y2 = 504, 578
    DL_Y1, DL_Y2 = 596, 652
    PR_Y1, PR_Y2 = 664, 686      # film strip (22px: 2 baris perforasi + badan)
    ST_Y = 712

    def __init__(self, root: tk.Tk, initial_url=None):
        self.root = root
        self.root.title("AB Video Downloader — YouTube & TikTok")
        self.root.geometry(f"{self.W}x{self.H}")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_BOT)

        icon_path = resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

        # State (muat preferensi terakhir)
        cfg = load_settings()
        self.download_dir = cfg.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        self.mode = cfg.get("mode", "video")
        self.quality = cfg.get("quality", "Terbaik")
        self.msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self.is_downloading = False
        self._open_ready = False
        self.cancel_event = threading.Event()   # sinyal batal ke thread unduhan
        self._partials = set()                  # berkas .part yang sedang ditulis
        if self.mode not in ("video", "audio"):
            self.mode = "video"
        if self.quality not in self._quality_values():
            self.quality = "Terbaik"

        # Pratinjau
        self._preview_job = None
        self._preview_token = 0
        self._last_fetched = None
        self._thumb_photo = None

        # Animasi
        self.animating = False
        self.anim_phase = 0.0
        self.progress_mode = "idle"     # idle | determinate | indeterminate
        self.progress_pct = 0.0

        # Fonts
        # Tiga peran huruf: display teknis, teks, telemetri.
        # Bahnschrift dipakai untuk judul & label panel; kalau tak tersedia,
        # jatuh kembali ke Segoe UI supaya tetap aman di komputer lain.
        avail = set(tkfont.families())
        disp = FONT_DISPLAY if FONT_DISPLAY in avail else FONT
        mono = FONT_MONO if FONT_MONO in avail else FONT

        self.f_title = tkfont.Font(family=disp, size=23, weight="bold")
        self.f_sub = tkfont.Font(family=FONT, size=10)
        self.f_label = tkfont.Font(family=disp, size=10, weight="bold")
        self.f_body = tkfont.Font(family=FONT, size=10)
        self.f_pill = tkfont.Font(family=FONT, size=10)
        self.f_btn = tkfont.Font(family=disp, size=15, weight="bold")
        self.f_small = tkfont.Font(family=FONT, size=9)
        self.f_ptitle = tkfont.Font(family=FONT, size=11, weight="bold")
        self.f_tele = tkfont.Font(family=mono, size=9)          # telemetri
        self.f_tele_hi = tkfont.Font(family=mono, size=9, weight="bold")

        self.canvas = tk.Canvas(root, width=self.W, height=self.H, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self._build_ui()
        self._poll_queue()

        if initial_url:
            self.link_entry.insert(0, initial_url)
            self._schedule_preview(delay=100)

    # ---------- Bangun UI ----------
    def _build_ui(self):
        c = self.canvas
        self._draw_gradient()

        # Lencana ikon (ikon vektor di dalam kotak beraksen), bukan emoji
        bx, by, bs = self.ML, 26, 34
        c.create_polygon(round_rect_points(bx, by, bx + bs, by + bs, 10),
                         smooth=True, fill=ACCENT, outline="")
        icon_film(c, bx + 8, by + 9, 18, "#FFFFFF")
        c.create_text(bx + bs + 14, 40, text="AB Video Downloader", anchor="w",
                      fill=TEXT, font=self.f_title)
        c.create_text(self.ML, 76, text="Tempel link YouTube atau TikTok, lalu klik Download.",
                      anchor="w", fill=MUTED, font=self.f_sub)

        # Kartu Link
        self._card(self.ML, self.LINK_Y1, self.MR, self.LINK_Y2)
        c.create_text(self.CL, self.LINK_Y1 + 18, text="LINK VIDEO", anchor="w",
                      fill=FAINT, font=self.f_label)
        self.link_entry = tk.Entry(self.root, font=(FONT, 11), bg=INNER, fg=TEXT,
                                   insertbackground=ACCENT_TEXT, relief="flat",
                                   highlightthickness=2, highlightbackground=CARD_BORDER,
                                   highlightcolor=RING, selectbackground=ACCENT,
                                   selectforeground="#FFFFFF")
        self.link_entry.place(x=self.CL, y=self.LINK_Y1 + 40, width=406, height=34)
        self.link_entry.bind("<Return>", lambda e: self.start_download())
        self.link_entry.bind("<KeyRelease>", lambda e: self._schedule_preview())
        CanvasButton(c, 466, self.LINK_Y1 + 40, self.CR, self.LINK_Y1 + 74, "Paste",
                     self.paste_clipboard, BTN_SUB, BTN_SUB_HOVER, TEXT, self.f_body, radius=12)

        # Kartu Pratinjau
        self._card(self.ML, self.PV_Y1, self.MR, self.PV_Y2)
        self._show_preview_empty()

        # Kartu Opsi
        self._card(self.ML, self.OPT_Y1, self.MR, self.OPT_Y2)
        c.create_text(self.CL, self.OPT_Y1 + 18, text="JENIS", anchor="w",
                      fill=FAINT, font=self.f_label)
        self._render_toggle()
        c.create_text(self.CL, self.Q_Y1 - 18, text="KUALITAS", anchor="w",
                      fill=FAINT, font=self.f_label)
        self._render_quality()

        # Kartu Folder
        self._card(self.ML, self.FD_Y1, self.MR, self.FD_Y2)
        c.create_text(self.CL, self.FD_Y1 + 18, text="SIMPAN KE FOLDER", anchor="w",
                      fill=FAINT, font=self.f_label)
        self.folder_text = c.create_text(self.CL, self.FD_Y1 + 42, anchor="w",
                                         fill=MUTED, font=self.f_body)
        self._update_folder_text()
        c.tag_bind(self.folder_text, "<Button-1>", lambda e: self.open_folder())
        c.tag_bind(self.folder_text, "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind(self.folder_text, "<Leave>", lambda e: c.config(cursor=""))
        CanvasButton(c, 460, self.FD_Y1 + 24, self.CR, self.FD_Y1 + 58, "Ubah",
                     self.choose_folder, BTN_SUB, BTN_SUB_HOVER, TEXT, self.f_body,
                     radius=12, icon=icon_folder)

        # Tombol Download
        self.download_btn = CanvasButton(c, self.ML, self.DL_Y1, self.MR, self.DL_Y2,
                                         "Download", self.start_download,
                                         ACCENT, ACCENT_HOVER, "#FFFFFF", self.f_btn,
                                         radius=16, press=ACCENT_PRESS, icon=icon_download)

        # Track progress + status
        self._draw_film_strip()
        self._punch_perforations()
        self.status_id = c.create_text(self.ML, self.ST_Y, anchor="w",
                                       fill=MUTED, font=self.f_small)
        # Telemetri rata kanan: angka dibaca sebagai data instrumen, bukan kalimat
        self.tele_id = c.create_text(self.MR, self.ST_Y, anchor="e",
                                     fill=FAINT, font=self.f_tele, text="")
        c.tag_bind(self.status_id, "<Button-1>",
                   lambda e: self.open_folder() if self._open_ready else None)
        c.tag_bind(self.status_id, "<Enter>",
                   lambda e: c.config(cursor="hand2") if self._open_ready else None)
        c.tag_bind(self.status_id, "<Leave>", lambda e: c.config(cursor=""))

        if not FFMPEG_DIR:
            self._set_status("ffmpeg tidak ditemukan, kualitas tinggi & MP3 bisa gagal. "
                             "Install: winget install Gyan.FFmpeg", ERR)
        else:
            self._set_status("Siap. Tempel link lalu klik Download.", MUTED)

    def _draw_gradient(self):
        r1, g1, b1 = self.root.winfo_rgb(BG_TOP)
        r2, g2, b2 = self.root.winfo_rgb(BG_BOT)
        for i in range(self.H):
            t = i / self.H
            r = int((r1 + (r2 - r1) * t) / 256)
            g = int((g1 + (g2 - g1) * t) / 256)
            b = int((b1 + (b2 - b1) * t) / 256)
            self.canvas.create_line(0, i, self.W, i, fill=f"#{r:02x}{g:02x}{b:02x}")

    def _card(self, x1, y1, x2, y2, r=18):
        """Kartu dengan kedalaman: bayangan lembut + hairline cahaya di tepi atas."""
        c = self.canvas
        # Bayangan berlapis di bawah kartu (makin jauh makin samar)
        for i, depth in enumerate((3, 2, 1)):
            shade = mix(BG_BOT, SHADOW, 0.5 - i * 0.15)
            c.create_polygon(round_rect_points(x1 + depth * 0.5, y1 + depth,
                                               x2 - depth * 0.5, y2 + depth, r),
                             smooth=True, fill=shade, outline="")
        # Badan kartu
        c.create_polygon(round_rect_points(x1, y1, x2, y2, r),
                         smooth=True, fill=CARD, outline=CARD_BORDER, width=1)
        # Hairline di tepi atas: memberi kesan sumber cahaya dari atas
        c.create_line(x1 + r * 0.8, y1 + 1, x2 - r * 0.8, y1 + 1,
                      fill=CARD_HILITE, width=1)

    # ---------- Pratinjau ----------
    def _schedule_preview(self, delay=700):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(delay, self._maybe_fetch_preview)

    def _maybe_fetch_preview(self):
        self._preview_job = None
        url = self.link_entry.get().strip()
        if not re.match(r"^https?://\S{5,}", url):
            if not url:
                self._show_preview_empty()
                self._last_fetched = None
            return
        if url == self._last_fetched:
            return
        self._last_fetched = url
        self._preview_token += 1
        token = self._preview_token
        self._show_preview_loading()
        threading.Thread(target=self._preview_worker, args=(url, token), daemon=True).start()

    def _preview_worker(self, url, token):
        try:
            opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
            if not info:
                raise ValueError("no info")
            title = info.get("title") or info.get("id") or "Video"
            uploader = info.get("uploader") or info.get("channel") or info.get("uploader_id") or ""
            duration = fmt_duration(info.get("duration"))

            thumb_url = info.get("thumbnail")
            if not thumb_url:
                thumbs = info.get("thumbnails") or []
                if thumbs:
                    thumb_url = thumbs[-1].get("url")

            b64 = None
            if thumb_url and HAS_PIL:
                req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                b64 = make_thumb_png_b64(raw, self.PV_TW, self.PV_TH)

            self.msg_queue.put(("preview", token, title, uploader, duration, b64))
        except Exception:
            self.msg_queue.put(("preview_err", token))

    def _clear_preview_items(self):
        self._stop_preview_spinner()
        self.canvas.delete("preview")

    def _centered_icon_text(self, icon_fn, text, color, isz=16, gap=10):
        c = self.canvas
        cx = (self.ML + self.MR) / 2
        cy = (self.PV_Y1 + self.PV_Y2) / 2
        total = isz + gap + self.f_body.measure(text)
        icon_fn(c, cx - total / 2, cy - isz / 2, isz, color, tags=("preview",))
        c.create_text(cx - total / 2 + isz + gap, cy, text=text, anchor="w",
                      fill=color, font=self.f_body, tags=("preview",))

    def _show_preview_empty(self):
        self._stop_preview_spinner()
        self._clear_preview_items()
        self._centered_icon_text(icon_search, "Pratinjau video akan muncul di sini", FAINT)

    def _show_preview_loading(self):
        """Umpan balik bahwa proses sedang berjalan."""
        self._clear_preview_items()
        if REDUCED_MOTION:
            self._centered_icon_text(icon_search, "Memuat pratinjau…", MUTED)
            return
        self._spinner_angle = 0
        self._spin_preview()

    def _spin_preview(self):
        c = self.canvas
        c.delete("spinner")
        cx = (self.ML + self.MR) / 2
        cy = (self.PV_Y1 + self.PV_Y2) / 2
        label = "Memuat pratinjau…"
        isz, gap = 18, 10
        total = isz + gap + self.f_body.measure(label)
        x = cx - total / 2
        # Busur yang berputar (arc) sebagai indikator proses
        c.create_arc(x, cy - isz / 2, x + isz, cy + isz / 2,
                     start=self._spinner_angle, extent=100, style="arc",
                     outline=ACCENT_TEXT, width=2, tags=("preview", "spinner"))
        c.create_text(x + isz + gap, cy, text=label, anchor="w",
                      fill=MUTED, font=self.f_body, tags=("preview", "spinner"))
        self._spinner_angle = (self._spinner_angle - 12) % 360
        self._spinner_job = self.root.after(40, self._spin_preview)

    def _stop_preview_spinner(self):
        job = getattr(self, "_spinner_job", None)
        if job:
            self.root.after_cancel(job)
            self._spinner_job = None

    def _show_preview(self, title, uploader, duration, b64):
        self._clear_preview_items()
        c = self.canvas
        # thumbnail
        if b64:
            try:
                self._thumb_photo = tk.PhotoImage(data=b64)
                c.create_image(self.PV_TX, self.PV_TY, anchor="nw",
                               image=self._thumb_photo, tags=("preview",))
            except tk.TclError:
                self._thumb_placeholder()
        else:
            self._thumb_placeholder()

        tx = self.PV_TX + self.PV_TW + 18
        # judul (maks ~90 karakter, wrap otomatis)
        shown = title if len(title) <= 90 else title[:89] + "…"
        c.create_text(tx, self.PV_TY + 2, anchor="nw", text=shown, fill=TEXT,
                      font=self.f_ptitle, width=self.CR - tx, tags=("preview",))
        # Bingkai tipis di sekeliling thumbnail supaya menyatu dengan bahasa kartu
        c.create_polygon(round_rect_points(self.PV_TX, self.PV_TY,
                                           self.PV_TX + self.PV_TW,
                                           self.PV_TY + self.PV_TH, 10),
                         smooth=True, fill="", outline=CARD_BORDER, width=1,
                         tags=("preview",))
        # meta: channel + durasi
        meta = "   ·   ".join(x for x in (uploader, duration) if x)
        if meta:
            c.create_text(tx, self.PV_TY + self.PV_TH - 4, anchor="w", text=meta,
                          fill=MUTED, font=self.f_small, tags=("preview",))

    def _thumb_placeholder(self):
        self.canvas.create_polygon(
            round_rect_points(self.PV_TX, self.PV_TY, self.PV_TX + self.PV_TW,
                              self.PV_TY + self.PV_TH, 10),
            smooth=True, fill=INNER, outline="", tags=("preview",))
        icon_film(self.canvas, self.PV_TX + self.PV_TW / 2 - 13,
                  self.PV_TY + self.PV_TH / 2 - 13, 26, FAINT, tags=("preview",))

    # ---------- Toggle ----------
    def _render_toggle(self, pos=None):
        """Gambar toggle. `pos` 0.0 = Video, 1.0 = Audio (dipakai saat animasi geser)."""
        c = self.canvas
        c.delete("toggle")
        if pos is None:
            pos = 0.0 if self.mode == "video" else 1.0
        self._toggle_pos = pos

        # Alur (track) dengan tepi halus
        c.create_polygon(round_rect_points(self.TG_X1, self.TG_Y1, self.TG_X2, self.TG_Y2, 15),
                         smooth=True, fill=TRACK, outline=mix(TRACK, CARD_BORDER, 0.6),
                         width=1, tags=("toggle",))

        # Thumb yang meluncur mengikuti `pos` (kontinuitas spasial)
        half = (self.TG_X2 - self.TG_X1) / 2
        tx1 = self.TG_X1 + 3 + pos * (half - 2)
        tx2 = tx1 + half - 4
        c.create_polygon(round_rect_points(tx1, self.TG_Y1 + 3, tx2, self.TG_Y2 - 3, 13),
                         smooth=True, fill=ACCENT, outline="", tags=("toggle",))

        cy = (self.TG_Y1 + self.TG_Y2) / 2
        # Warna label mengikuti posisi thumb agar transisi terasa menyatu
        vid_col = mix("#FFFFFF", PILL_TEXT, pos)
        aud_col = mix(PILL_TEXT, "#FFFFFF", pos)

        for cx_center, label, icon_fn, col in (
            ((self.TG_X1 + self.TG_MID) / 2, "Video", icon_film, vid_col),
            ((self.TG_MID + self.TG_X2) / 2, "Audio", icon_music, aud_col),
        ):
            tw = self.f_pill.measure(label)
            isz, gap = 15, 8
            total = isz + gap + tw
            icon_fn(c, cx_center - total / 2, cy - isz / 2, isz, col, tags=("toggle",))
            c.create_text(cx_center - total / 2 + isz + gap, cy, text=label, anchor="w",
                          fill=col, font=self.f_pill, tags=("toggle",))

        c.tag_bind("toggle", "<Button-1>", self._toggle_click)
        c.tag_bind("toggle", "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind("toggle", "<Leave>", lambda e: c.config(cursor=""))

    def _animate_toggle(self, target):
        """Geser thumb toggle secara halus (~180ms) alih-alih melompat."""
        start = getattr(self, "_toggle_pos", 0.0)
        if getattr(self, "_toggle_job", None):
            self.root.after_cancel(self._toggle_job)
            self._toggle_job = None
        if REDUCED_MOTION:
            self._render_toggle(target)
            return
        steps = 11

        def step(i=1):
            t = ease_out(i / steps)
            self._render_toggle(start + (target - start) * t)
            if i < steps:
                self._toggle_job = self.root.after(16, step, i + 1)
            else:
                self._toggle_job = None
                self._render_toggle(target)

        step()

    def _toggle_click(self, event):
        new = "video" if event.x < self.TG_MID else "audio"
        if new != self.mode:
            self.mode = new
            self.quality = "Terbaik"
            self._animate_toggle(0.0 if new == "video" else 1.0)
            self._render_quality()
            self._save()

    # ---------- Kualitas ----------
    def _quality_values(self):
        if self.mode == "video":
            return ["Terbaik", "1080p", "720p", "480p", "360p"]
        return ["Terbaik", "192 kbps", "128 kbps"]

    def _render_quality(self):
        c = self.canvas
        c.delete("qpill")
        x = self.CL
        self._qpill_shapes = {}
        for i, val in enumerate(self._quality_values()):
            w = self.f_pill.measure(val) + 32
            sel = (val == self.quality)
            tag = f"qpill_{i}"
            shape = c.create_polygon(
                round_rect_points(x, self.Q_Y1, x + w, self.Q_Y2, 15), smooth=True,
                fill=ACCENT if sel else PILL,
                outline=ACCENT_TEXT if sel else mix(PILL, CARD_BORDER, 0.7),
                width=1, tags=("qpill", tag))
            c.create_text(x + w / 2, (self.Q_Y1 + self.Q_Y2) / 2, text=val,
                          fill="#FFFFFF" if sel else PILL_TEXT, font=self.f_pill,
                          tags=("qpill", tag))
            self._qpill_shapes[tag] = (shape, sel)
            c.tag_bind(tag, "<Button-1>", lambda e, v=val: self._set_quality(v))
            c.tag_bind(tag, "<Enter>", lambda e, t=tag: self._qpill_hover(t, True))
            c.tag_bind(tag, "<Leave>", lambda e, t=tag: self._qpill_hover(t, False))
            x += w + 10

    def _qpill_hover(self, tag, entering):
        """Sorot pill yang belum terpilih saat kursor di atasnya."""
        info = getattr(self, "_qpill_shapes", {}).get(tag)
        self.canvas.config(cursor="hand2" if entering else "")
        if not info:
            return
        shape, selected = info
        if selected:
            return
        try:
            self.canvas.itemconfig(shape, fill=PILL_HOVER if entering else PILL)
        except tk.TclError:
            pass

    def _set_quality(self, val):
        self.quality = val
        self._render_quality()
        self._save()

    # ---------- Folder ----------
    def _fit_path(self, path, max_px):
        if self.f_body.measure(path) <= max_px:
            return path
        head, tail, ell = path[:len(path) // 3], path, "…"
        while self.f_body.measure(head + ell + tail) > max_px and len(tail) > 4:
            tail = tail[1:]
        return head + ell + tail

    def _update_folder_text(self):
        self.canvas.itemconfig(self.folder_text, text=self._fit_path(self.download_dir, 402))

    # ---------- Preferensi & folder ----------
    def _save(self):
        save_settings({"download_dir": self.download_dir,
                       "mode": self.mode, "quality": self.quality})

    def open_folder(self):
        target = self.download_dir
        if os.path.isdir(target):
            try:
                os.startfile(target)
            except Exception:
                pass

    # ---------- Aksi ----------
    def paste_clipboard(self):
        try:
            text = self.root.clipboard_get().strip()
            self.link_entry.delete(0, tk.END)
            self.link_entry.insert(0, text)
            self._schedule_preview(delay=100)
        except tk.TclError:
            self._set_status("Clipboard kosong. Salin link video dulu.", MUTED)

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self._update_folder_text()
            self._save()

    def start_download(self):
        if self.is_downloading:
            return
        url = self.link_entry.get().strip()
        if not url:
            messagebox.showwarning("Link kosong", "Paste link video dulu ya.")
            return
        if not re.match(r"^https?://", url):
            messagebox.showwarning("Link tidak valid", "Link harus diawali http:// atau https://")
            return
        os.makedirs(self.download_dir, exist_ok=True)
        self.is_downloading = True
        self._open_ready = False
        self.cancel_event.clear()
        self._partials = set()
        # Tombol yang sama berubah peran: Download -> Batalkan (layout tidak bergeser)
        self.download_btn.set_colors(BTN_SUB, BTN_SUB_HOVER)
        self.download_btn.set_icon(icon_close)
        self.download_btn.set_icon_color(TEXT)
        self.download_btn.set_text("Batalkan")
        self.download_btn.set_command(self.cancel_download)
        self.download_btn.set_enabled(True)
        self.progress_mode = "indeterminate"
        self._start_anim()
        self._set_tele("")
        self._set_status("Menyiapkan", ACCENT_TEXT)
        threading.Thread(target=self._download_worker,
                         args=(url, self.download_dir), daemon=True).start()

    def cancel_download(self):
        """Minta thread unduhan berhenti. Berkas .part yang sudah ditulis dihapus."""
        if not self.is_downloading or self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.download_btn.set_enabled(False)
        self._set_status("Membatalkan", MUTED)
        self._set_tele("")

    def _cleanup_partials(self):
        """Hapus berkas sementara dari unduhan yang dibatalkan.

        Hanya menyentuh berkas yang tercatat lewat progress hook DAN berakhiran
        .part/.ytdl, supaya tidak pernah menghapus hasil unduhan yang utuh.
        """
        for path in list(self._partials):
            try:
                if path.endswith((".part", ".ytdl")) and os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        self._partials.clear()

    def _pp_hook(self, d):
        """Hook postprocessor: memungkinkan batal saat tahap penggabungan."""
        if self.cancel_event.is_set():
            raise DownloadCancelled()

    def _build_opts(self, out_dir):
        opts = {
            "outtmpl": os.path.join(out_dir, "%(title).200B [%(id)s].%(ext)s"),
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._pp_hook],
            "noplaylist": True, "quiet": True, "no_warnings": True, "ignoreerrors": False,
        }
        if FFMPEG_DIR:
            opts["ffmpeg_location"] = FFMPEG_DIR
        if self.mode == "audio":
            bitrate = {"192 kbps": "192", "128 kbps": "128"}.get(self.quality, "0")
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                       "preferredcodec": "mp3", "preferredquality": bitrate}]
        else:
            height = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360}.get(self.quality)
            if height:
                opts["format"] = (f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                                  f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best")
            else:
                opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"
        return opts

    def _download_worker(self, url, out_dir):
        try:
            with yt_dlp.YoutubeDL(self._build_opts(out_dir)) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "video") if info else "video"
            if self.cancel_event.is_set():
                self._cleanup_partials()
                self.msg_queue.put(("cancelled",))
            else:
                self.msg_queue.put(("done", title))
        except DownloadCancelled:
            self._cleanup_partials()
            self.msg_queue.put(("cancelled",))
        except Exception as e:
            # yt-dlp kadang membungkus pembatalan di dalam DownloadError
            if self.cancel_event.is_set():
                self._cleanup_partials()
                self.msg_queue.put(("cancelled",))
            else:
                # Bersihkan juga saat gagal: berkas .part dari unduhan yang error
                # (mis. HTTP 403) bisa dilanjutkan di percobaan berikutnya dan
                # menghasilkan video korup, meski yt-dlp melapor berhasil.
                self._cleanup_partials()
                self.msg_queue.put(("error", strip_ansi(str(e))))

    def _progress_hook(self, d):
        if self.cancel_event.is_set():
            raise DownloadCancelled()
        tmp = d.get("tmpfilename")
        if tmp:
            self._partials.add(tmp)
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = d.get("downloaded_bytes", 0) / total * 100
                speed = d.get("speed") or 0
                speed_txt = f"{speed / 1024 / 1024:.1f} MB/s" if speed else ""
                self.msg_queue.put(("progress", pct, speed_txt))
        elif st == "finished":
            self.msg_queue.put(("processing", None))

    # ---------- Antrian pesan ----------
    def _poll_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, pct, speed = item
                    self.progress_mode = "determinate"
                    self.progress_pct = pct
                    self._set_status("Mengunduh", ACCENT_TEXT)
                    tele = f"{pct:5.1f}%"
                    if speed:
                        tele += f"   {speed}"
                    self._set_tele(tele, ACCENT_TEXT)
                elif kind == "processing":
                    self.progress_mode = "indeterminate"
                    self._set_status("Menggabungkan video & audio", ACCENT_TEXT)
                    self._set_tele("ffmpeg", ACCENT_TEXT)
                elif kind == "done":
                    self._open_ready = True
                    self._finish("Selesai! Klik di sini untuk buka folder hasil.",
                                 OK, icon=icon_check)
                elif kind == "cancelled":
                    # Nama aksi konsisten: tombol "Batalkan" -> status "Dibatalkan"
                    self._finish("Unduhan dibatalkan.", MUTED)
                elif kind == "error":
                    self._finish(friendly_error(item[1]), ERR, icon=icon_alert)
                elif kind == "preview":
                    _, token, title, uploader, duration, b64 = item
                    if token == self._preview_token:
                        self._show_preview(title, uploader, duration, b64)
                elif kind == "preview_err":
                    if item[1] == self._preview_token:
                        self._show_preview_empty()
                        self._last_fetched = None
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _finish(self, msg, color, icon=None):
        self.is_downloading = False
        self.cancel_event.clear()
        self.download_btn.set_enabled(True)
        self.download_btn.set_colors(ACCENT, ACCENT_HOVER, ACCENT_PRESS)
        self.download_btn.set_icon(icon_download)
        self.download_btn.set_icon_color("#FFFFFF")
        self.download_btn.set_text("Download")
        self.download_btn.set_command(self.start_download)
        self._stop_anim()
        self.canvas.delete("pfill")
        if color == OK:
            # Strip terisi penuh: gulungan selesai dibaca
            self._draw_round(self.ML, self.MR, OK_FILL)
            self._set_tele("100%", OK)
        else:
            self._set_tele("")
        self.canvas.tag_raise("perf")
        self._set_status(msg, color, icon=icon)

    # ---------- Animasi progress ----------
    def _start_anim(self):
        if not self.animating:
            self.animating = True
            self.anim_phase = 0.0
            self._tick_anim()

    def _stop_anim(self):
        self.animating = False

    # ---------- Film strip (elemen signature) ----------
    PERF_W, PERF_H, PERF_GAP = 9, 4, 30

    def _draw_film_strip(self):
        """Alur progres digambar sebagai film strip: perforasi menembus badan."""
        c = self.canvas
        c.delete("strip_base")
        c.create_polygon(
            round_rect_points(self.ML, self.PR_Y1, self.MR, self.PR_Y2, 4),
            smooth=True, fill=TRACK, outline=mix(TRACK, CARD_BORDER, 0.55),
            width=1, tags=("strip_base",))

    def _punch_perforations(self):
        """Lubang sprocket digambar paling akhir agar menembus isian, seperti film asli."""
        c = self.canvas
        c.delete("perf")
        w, h, gap = self.PERF_W, self.PERF_H, self.PERF_GAP
        y_top = self.PR_Y1 + 3
        y_bot = self.PR_Y2 - 3 - h
        x = self.ML + 6
        while x + w <= self.MR - 6:
            for y in (y_top, y_bot):
                c.create_polygon(round_rect_points(x, y, x + w, y + h, 1),
                                 smooth=True, fill=BG_BOT, outline="", tags=("perf",))
            x += gap

    def _draw_playhead(self, x):
        """Playhead: garis terang di ujung isian, penanda posisi baca."""
        c = self.canvas
        x = max(self.ML + 1, min(self.MR - 1, x))
        c.create_line(x, self.PR_Y1 - 2, x, self.PR_Y2 + 2,
                      fill=SHIMMER, width=2, tags=("pfill",))

    def _draw_round(self, x1, x2, fill):
        self.canvas.create_polygon(
            round_rect_points(x1, self.PR_Y1, x2, self.PR_Y2, 4),
            smooth=True, fill=fill, outline="", tags=("pfill",))

    def _tick_anim(self):
        if not self.animating:
            return
        c = self.canvas
        c.delete("pfill")
        tw = self.MR - self.ML

        if self.progress_mode == "determinate":
            w = max(0.0, min(100.0, self.progress_pct)) / 100 * tw
            if w > 2:
                self._draw_round(self.ML, self.ML + w, ACCENT)
                # Kilau menyapu bagian terisi (dekoratif, dilewati bila reduced motion)
                if w > 46 and not REDUCED_MOTION:
                    sx = self.ML + ((self.anim_phase * 1.3) % 1.0) * w
                    x1 = max(self.ML + 2, sx - 26)
                    x2 = min(self.ML + w - 2, sx + 26)
                    if x2 > x1:
                        self._draw_round(x1, x2, mix(ACCENT, SHIMMER, 0.55))
                self._draw_playhead(self.ML + w)
        elif self.progress_mode == "indeterminate":
            bw = tw * 0.28
            span = tw + bw
            p = ((self.anim_phase * 0.9) % 1.0) * span - bw
            x1 = self.ML + max(0.0, p)
            x2 = self.ML + min(tw, p + bw)
            if x2 - x1 > 2:
                self._draw_round(x1, x2, ACCENT)
                mid = (x1 + x2) / 2
                sx1, sx2 = max(x1, mid - 18), min(x2, mid + 18)
                if sx2 > sx1 and not REDUCED_MOTION:
                    self._draw_round(sx1, sx2, mix(ACCENT, SHIMMER, 0.5))
                if x2 < self.MR:
                    self._draw_playhead(x2)

        # Perforasi statis: cukup diangkat ke lapisan atas, tidak digambar ulang.
        # (menggambar ulang ~36 poligon tiap frame memboroskan CPU tanpa manfaat)
        c.tag_raise("perf")

        self.anim_phase += 0.02
        self.root.after(30, self._tick_anim)

    def _set_tele(self, text, color=None):
        """Baris telemetri (mono, rata kanan): persen, kecepatan, ukuran."""
        self.canvas.itemconfig(self.tele_id, text=text, fill=color or FAINT)

    def _set_status(self, text, color, icon=None):
        """Perbarui baris status. `icon` opsional (ikon vektor, bukan emoji)."""
        c = self.canvas
        c.delete("status_icon")
        isz, gap = 12, 9
        offset = (isz + gap) if icon else 0
        tele = self.canvas.itemcget(self.tele_id, "text")
        reserved = (self.f_tele.measure(tele) + 24) if tele else 0
        avail = (self.MR - self.ML) - offset - reserved
        if self.f_small.measure(text) > avail:
            while self.f_small.measure(text + "…") > avail and len(text) > 8:
                text = text[:-1]
            text += "…"
        if icon:
            icon(c, self.ML, self.ST_Y - isz / 2, isz, color, tags=("status_icon",))
        c.coords(self.status_id, self.ML + offset, self.ST_Y)
        c.itemconfig(self.status_id, text=text, fill=color)


def main():
    # Hook diagnostik (untuk verifikasi build) — tulis status lalu keluar
    if os.environ.get("VD_DIAG"):
        try:
            with open(os.path.join(app_data_dir(), "diag.txt"), "w", encoding="utf-8") as f:
                f.write(f"frozen={getattr(sys, 'frozen', False)}\n")
                f.write(f"FFMPEG_DIR={FFMPEG_DIR}\n")
                f.write(f"ffmpeg_exists={bool(FFMPEG_DIR) and os.path.exists(os.path.join(FFMPEG_DIR, 'ffmpeg.exe'))}\n")
                f.write(f"HAS_DENO={HAS_DENO}\n")
                f.write(f"HAS_PIL={HAS_PIL}\n")
        except Exception:
            pass
        return

    # Hook tes download headless (untuk verifikasi build) — unduh lalu keluar
    testdl = os.environ.get("VD_TESTDL")
    if testdl:
        result = {"ok": True, "msg": "", "ffmpeg_dir": FFMPEG_DIR}
        try:
            out_dir = os.path.join(os.path.expanduser("~"), "Downloads", "VideoDownloader")
            os.makedirs(out_dir, exist_ok=True)
            opts = {
                "outtmpl": os.path.join(out_dir, "%(title).100B [%(id)s].%(ext)s"),
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
            }
            if FFMPEG_DIR:
                opts["ffmpeg_location"] = FFMPEG_DIR
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(testdl, download=True)
                result["file"] = ydl.prepare_filename(info)
        except Exception as e:
            result["ok"] = False
            result["msg"] = strip_ansi(str(e))[:600]
        try:
            with open(os.path.join(app_data_dir(), "testdl.txt"), "w", encoding="utf-8") as f:
                for k, v in result.items():
                    f.write(f"{k}={v}\n")
        except Exception:
            pass
        return

    initial = None
    if len(sys.argv) > 1 and re.match(r"^https?://", sys.argv[1]):
        initial = sys.argv[1]
    root = tk.Tk()
    VideoDownloaderApp(root, initial_url=initial)
    root.mainloop()


if __name__ == "__main__":
    main()
