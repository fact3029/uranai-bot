"""投稿用の画像（ランキング・今日の1枚）と、ガチャ風の縦長動画を作る。"""
import math
import os
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .content import DailyContent

GOLD = (255, 211, 77)
TEXT = (241, 236, 255)
MUTED = (167, 159, 208)
RARITY_COLOR = {"N": (207, 211, 230), "R": (95, 180, 255), "SR": (192, 123, 255), "SSR": (255, 211, 77), "UR": (255, 95, 158)}
RAINBOW = [(255, 95, 158), (255, 211, 77), (95, 255, 176), (95, 180, 255), (192, 123, 255)]
ROMAN = ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV",
         "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"]
NAMES = ["愚者", "魔術師", "女教皇", "女帝", "皇帝", "教皇", "恋人", "戦車", "力", "隠者", "運命の輪", "正義",
         "吊るされた男", "死神", "節制", "悪魔", "塔", "星", "月", "太陽", "審判", "世界"]

# 太字があれば使い、無ければ縁取りで太く見せる
_BOLD = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"]
_REGULAR = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"]


def _find(paths: list[str]) -> str | None:
    env = os.getenv("FONT_PATH")
    for p in ([env] if env else []) + paths:
        if p and Path(p).exists():
            return p
    return None


_bold_path, _reg_path = _find(_BOLD), _find(_REGULAR)
if _reg_path is None and _bold_path is None:
    raise RuntimeError("日本語フォントが見つかりません。fonts-noto-cjk を入れるか FONT_PATH を設定してください")


def font(size: int, bold: bool = False) -> tuple[ImageFont.FreeTypeFont, int]:
    """(フォント, 縁取りの太さ) を返す。"""
    if bold and _bold_path:
        return ImageFont.truetype(_bold_path, size), 0
    return ImageFont.truetype(_reg_path or _bold_path, size), (max(1, size // 28) if bold else 0)


def text(d: ImageDraw.ImageDraw, xy, s: str, size: int, fill, bold=False, anchor="la"):
    f, stroke = font(size, bold)
    d.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=fill)


def background(w: int, h: int, seed: int = 0) -> Image.Image:
    img = Image.new("RGB", (w, h), (8, 5, 25))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-w * 0.3, -h * 0.25, w * 1.3, h * 0.75), fill=(58, 44, 134))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(w // 5)), 0.85)
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)
    for _ in range(w * h // 9000):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.6, 2.6)
        a = rng.randint(90, 255)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(a, a, min(255, a + 20)))
    return img


def _glow_rect(img: Image.Image, box, color, radius=28, blur=40, width=8):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius, outline=color + (255,), width=width * 3)
    img.paste(layer.filter(ImageFilter.GaussianBlur(blur)), (0, 0), layer.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius, fill=(27, 20, 70), outline=color, width=width)


def card_face(img: Image.Image, c, box, show_rarity=True):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    col = RARITY_COLOR[c.rarity]
    _glow_rect(img, box, col, width=max(4, w // 60))
    d = ImageDraw.Draw(img)
    cx = x0 + w // 2
    s = w / 600
    if show_rarity:
        text(d, (cx, y0 + 70 * s), c.rarity, int(70 * s), col, bold=True, anchor="mm")
    idx = NAMES.index(c.name) if c.name in NAMES else 0
    text(d, (cx, y0 + h * 0.36), ROMAN[idx], int(44 * s), MUTED, anchor="mm")
    size = int(min(120, 560 / max(len(c.name), 1)) * s)
    text(d, (cx, y0 + h * 0.52), c.name, size, col, bold=True, anchor="mm")
    text(d, (cx, y0 + h * 0.66), "逆位置" if c.reversed else "正位置", int(46 * s), TEXT, bold=True, anchor="mm")
    text(d, (cx, y0 + h * 0.76), c.meaning, int(30 * s), MUTED, anchor="mm")


def card_back(img: Image.Image, box, glow_color, shake=(0, 0)):
    x0, y0, x1, y1 = (box[0] + shake[0], box[1] + shake[1], box[2] + shake[0], box[3] + shake[1])
    _glow_rect(img, (x0, y0, x1, y1), glow_color, width=8, blur=50)
    w, h = x1 - x0, y1 - y0
    # 模様はカードの形に切り抜いてから貼る（はみ出さないように）
    pat = Image.new("RGB", (w, h), (27, 20, 70))
    pd = ImageDraw.Draw(pat)
    cx, cy = w // 2, h // 2
    for i in range(18):
        a = i * math.pi / 9
        pd.line((cx, cy, cx + math.cos(a) * w, cy + math.sin(a) * h), fill=(45, 36, 112), width=14)
    pd.rounded_rectangle((20, 20, w - 20, h - 20), 20, outline=(141, 127, 224), width=3)
    r = w // 6
    pd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD)
    pd.ellipse((cx - r + r // 2, cy - r - r // 6, cx + r + r // 2, cy + r - r // 6), fill=(27, 20, 70))  # 三日月
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, w - 8, h - 8), 22, fill=255)
    img.paste(pat, (x0, y0), mask)


# --- 画像 -------------------------------------------------------------------
def ranking_image(c: DailyContent, path: Path) -> Path:
    W, H = 1080, 1350
    img = background(W, H, seed=c.day.toordinal())
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), f"{c.date_label} 12星座ランキング", 58, GOLD, bold=True, anchor="mm")
    top = 170
    row_h = (H - top - 70) // 12
    for i, f in enumerate(c.ranking, start=1):
        y = top + (i - 1) * row_h
        medal = {1: GOLD, 2: (215, 220, 235), 3: (222, 150, 90)}.get(i, (60, 50, 120))
        d.rounded_rectangle((60, y + 6, W - 60, y + row_h - 6), 18, fill=(29, 24, 64) if i > 3 else (45, 36, 100))
        d.ellipse((80, y + 14, 80 + row_h - 28, y + row_h - 14), fill=medal)
        text(d, (80 + (row_h - 28) // 2, y + row_h // 2), str(i), 38, (20, 15, 50) if i <= 3 else TEXT, bold=True, anchor="mm")
        text(d, (190, y + row_h // 2), f["sign"], 44, TEXT, bold=True, anchor="lm")
        stars = "★" * f["scores"]["総合"] + "☆" * (5 - f["scores"]["総合"])
        text(d, (520, y + row_h // 2), stars, 34, GOLD, anchor="lm")
        text(d, (W - 90, y + row_h // 2), f"LUCKY {f['lucky_color']}", 30, MUTED, anchor="rm")
    text(d, (W // 2, H - 35), "月詠の占い  ※占いは娯楽です", 28, MUTED, anchor="mm")
    img.save(path, "JPEG", quality=92)
    return path


def card_image(c: DailyContent, path: Path) -> Path:
    W, H = 1080, 1350
    img = background(W, H, seed=c.day.toordinal() + 1)
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), f"{c.date_label} みんなの今日の1枚", 58, GOLD, bold=True, anchor="mm")
    card_face(img, c.card, (270, 170, 810, 980))
    d = ImageDraw.Draw(img)
    _wrap(d, c.card_message, (W // 2, 1080), 42, TEXT, max_w=W - 160)
    text(d, (W // 2, H - 35), "月詠の占い  ※占いは娯楽です", 28, MUTED, anchor="mm")
    img.save(path, "JPEG", quality=92)
    return path


def _wrap(d, s: str, center, size, fill, max_w):
    f, stroke = font(size)
    lines, line = [], ""
    for ch in s:
        if d.textlength(line + ch, font=f) > max_w:
            lines.append(line)
            line = ch
        else:
            line += ch
    lines.append(line)
    for i, ln in enumerate(lines[:3]):
        d.text((center[0], center[1] + i * size * 1.5), ln, font=f, fill=fill, anchor="mm")


# --- 動画（9:16 のガチャ演出）------------------------------------------------
FPS = 30


def _ease(t: float) -> float:
    return 1 - (1 - min(max(t, 0), 1)) ** 3


def gacha_frames(c: DailyContent, W=1080, H=1920):
    """1枚ずつ PIL 画像を返す。全体で約9秒。"""
    order = ["N", "R", "SR", "SSR", "UR"]
    top = order.index(c.card.rarity)
    base = background(W, H, seed=7)
    box = (240, 520, 840, 1420)
    rng = random.Random(c.day.toordinal())
    parts = []
    intro, charge_per, flip, reveal, outro = 1.2, 0.7, 0.6, 2.4, 2.2
    charge = 1.0 + charge_per * top
    total = intro + charge + flip + reveal + outro
    for n in range(int(total * FPS)):
        t = n / FPS
        img = base.copy()
        d = ImageDraw.Draw(img)
        text(d, (W // 2, 230), f"{c.date_label}", 56, MUTED, anchor="mm")
        text(d, (W // 2, 330), "今日の運命のカード", 80, GOLD, bold=True, anchor="mm")
        if t < intro + charge:
            k = max(0, t - intro)
            level = min(top, int(max(0, k - 1.0) / charge_per) + 1) if k > 1.0 else 0
            col = RARITY_COLOR[order[level]] if order[level] != "UR" else RAINBOW[n % 5]
            amp = 0 if t < intro else 4 + 4 * level
            shake = (rng.randint(-amp, amp), rng.randint(-amp, amp)) if amp else (0, 0)
            drop = int((1 - _ease(t / 0.6)) * -300)
            card_back(img, (box[0], box[1] + drop, box[2], box[3] + drop), col, shake)
            d = ImageDraw.Draw(img)
            hint = {1: "…！", 2: "！？", 3: "SSR以上確定!!", 4: "UR 確定!!"}.get(level, "")
            if hint:
                text(d, (W // 2, 1560), hint, 90, col, bold=True, anchor="mm")
            text(d, (W // 2, 1720), "あなたへのメッセージは…？", 44, MUTED, anchor="mm")
        elif t < intro + charge + flip:
            k = (t - intro - charge) / flip
            sx = abs(math.cos(k * math.pi))  # 横につぶして裏返す
            card = Image.new("RGB", (W, H))
            card.paste(base)
            if k < 0.5:
                card_back(card, box, RARITY_COLOR.get(c.card.rarity, GOLD))
            else:
                card_face(card, c.card, box)
            crop = card.crop(box)
            cw = max(2, int((box[2] - box[0]) * sx))
            crop = crop.resize((cw, box[3] - box[1]))
            img.paste(crop, ((W - cw) // 2, box[1]))
            if 0.4 < k < 0.7:  # 白く光る
                img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), 0.6 * (1 - abs(k - 0.55) / 0.15))
        else:
            k = t - intro - charge - flip
            card_face(img, c.card, box)
            if not parts:
                cols = RAINBOW if c.card.rarity == "UR" else [RARITY_COLOR[c.card.rarity], (255, 255, 255)]
                for i in range(40 + 40 * top):
                    a, sp = rng.uniform(0, 2 * math.pi), rng.uniform(6, 22)
                    parts.append([W / 2, (box[1] + box[3]) / 2, math.cos(a) * sp, math.sin(a) * sp - 6, cols[i % len(cols)], rng.uniform(4, 10)])
            d = ImageDraw.Draw(img)
            for p in parts:
                p[0] += p[2]; p[1] += p[3]; p[3] += 0.6; p[2] *= 0.98
                life = max(0.0, 1 - k / reveal)
                if life > 0:
                    r = p[5] * life
                    d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=p[4])
            pop = _ease(k / 0.4)
            text(d, (W // 2, 1540), f"【{c.card.rarity}】", int(110 * (0.6 + 0.4 * pop)), RARITY_COLOR[c.card.rarity], bold=True, anchor="mm")
            if k > reveal * 0.5:
                _wrap(d, c.card_message, (W // 2, 1680), 50, TEXT, max_w=W - 140)
            if k > reveal:
                text(d, (W // 2, 1840), "フォローで毎朝お届け", 44, GOLD, anchor="mm")
        yield img


def gacha_video(c: DailyContent, path: Path) -> Path:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
           "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "22",
           "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for frame in gacha_frames(c):
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg で動画を作れませんでした")
    return path

