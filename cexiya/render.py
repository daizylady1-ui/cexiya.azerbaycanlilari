"""Заполнение шаблонов Canva (assets/templates/*.jpg, 1080×1350) текстом + сторис и плашки для Reels.

Шаблоны содержат надписи-заглушки ("Title", "subtitle", "body text", "xxxx").
Они стираются: каждая строка пикселей заливается плавным переходом между цветами
панели слева и справа от заглушки (+ лёгкое «зерно», как в оригинале).
Если есть «чистые» версии шаблонов без заглушек — просто замените файлы, а в
LAYOUTS уберите соответствующие области "erase".
"""
import glob
import os
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .util import ROOT

W, H_POST, H_STORY = 1080, 1350, 1920
TPL = ROOT / "assets" / "templates"
FONT_DIRS = [ROOT / "assets" / "fonts", Path("/usr/share/fonts"), Path("C:/Windows/Fonts"),
             Path(os.path.expanduser("~/Library/Fonts")), Path("/Library/Fonts")]

DARK = (51, 51, 51)
GRAY = (110, 110, 110)
PANEL = (232, 232, 230)

# ── геометрия шаблонов (пиксели в 1080×1350) ───────────────────
TITLE_ERASE = (112, 108, 320, 252)
TITLE_BOX = (128, 110, 768, 250)
COVER_ERASE = [(590, 698, 810, 782)]
COVER_BOX = (452, 505, 948, 970)            # полупрозрачный квадрат с "xxxx"
LAYOUTS = {
    # a: заголовок + текст + 3 фото снизу
    "a": {"erase": [TITLE_ERASE, (86, 316, 305, 400)], "body": [(97, 322, 962, 700)]},
    # b: заголовок + 2 блока текста + 2 фото
    "b": {"erase": [TITLE_ERASE, (418, 314, 628, 374), (86, 646, 305, 704)],
          "body": [(428, 318, 965, 575), (97, 650, 630, 1015)]},
    # c: заголовок + один большой блок текста
    "c": {"erase": [TITLE_ERASE, (86, 336, 305, 402)], "body": [(97, 340, 962, 1015)]},
    # d: одна большая панель, заголовок внутри
    "d": {"erase": [TITLE_ERASE, (86, 336, 305, 402)], "body": [(97, 300, 962, 1015)]},
}
# порядок чередования макетов слайдов внутри карусели
ROTATION = ["c", "a", "d", "b"]

# недельная погода (weather.jpg)
WX_TODAY_BOX = (313, 393, 753, 735)
WX_PRAHA_COLS = [372, 428, 486, 543, 601, 652, 703]      # центры колонок B.e … B
WX_PRAHA_TEMP_Y = 800
WX_TABLE_COLS = [447, 518, 587, 657, 730, 798, 870]
WX_TABLE_ROWS = [962, 1015, 1068]                        # Brno, Plzen, Ostrava
ICON_BOXES = {                                           # weather_icons.jpg
    "partly": (110, 70, 520, 370), "sunrain": (540, 70, 910, 410), "sun": (120, 420, 420, 715),
    "cloud": (500, 450, 950, 700), "snow": (55, 760, 510, 1195), "rain": (500, 745, 950, 1085),
}


def hex_rgb(h: str, a: int | None = None):
    h = h.lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb + (a,) if a is not None else rgb


class Theme:
    def __init__(self, cfg: dict):
        t = cfg["theme"]
        self.bold_names, self.reg_names = t["font_bold"], t["font_regular"]
        self.handle, self.name = cfg["account"]["handle"], cfg["account"]["name"]
        self.logo = _load_logo(ROOT / t["logo"])

    def font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        return _font(tuple(self.bold_names if bold else self.reg_names), size)


def _load_logo(path: Path) -> Image.Image | None:
    """Логотип на светлом фоне → обрезаем поля и делаем фон прозрачным."""
    if not path.exists():
        alt = sorted((ROOT / "assets").glob("logo.*"))
        if not alt:
            return None
        path = alt[0]
    img = Image.open(path).convert("RGB")
    bg = Image.new("RGB", img.size, img.getpixel((5, 5)))
    mask = ImageOps.grayscale(ImageChops.difference(img, bg)).point(lambda v: 255 if v > 18 else 0)
    box = mask.getbbox()
    rgba = img.convert("RGBA")
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(0.6)))
    return rgba.crop(box) if box else rgba


@lru_cache(maxsize=None)
def _find_font_file(names: tuple) -> str | None:
    for name in names:
        for d in FONT_DIRS:
            if d.exists():
                for ext in ("ttf", "otf", "TTF"):
                    hits = glob.glob(str(d / "**" / f"{name}.{ext}"), recursive=True)
                    if hits:
                        return hits[0]
    return None


@lru_cache(maxsize=None)
def _font(names: tuple, size: int) -> ImageFont.FreeTypeFont:
    path = _find_font_file(names)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


# ── текст ─────────────────────────────────────────────────────

def wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            test = f"{cur} {word}".strip()
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def fit(draw, theme: Theme, text: str, max_w: int, max_h: int, start: int, minimum: int,
        bold: bool = True, spacing: float = 1.22):
    size = start
    while True:
        f = theme.font(size, bold)
        lines = wrap(draw, text, f, max_w)
        if len(lines) * size * spacing <= max_h or size <= minimum:
            return f, lines, size
        size -= 2


def draw_lines(draw, x, y, lines, font, size, fill, spacing=1.22, align="left", box_w=0) -> int:
    for line in lines:
        lx = x + (box_w - draw.textlength(line, font=font)) / 2 if align == "center" else x
        draw.text((lx, y), line, font=font, fill=fill)
        y += int(size * spacing)
    return y


def ellipsize(draw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def pill(draw, xy, text, font, bg, fg, pad_x=28, pad_y=14):
    x, y = xy
    tw, th = draw.textlength(text, font=font), font.size
    draw.rounded_rectangle((x, y, x + tw + 2 * pad_x, y + th + 2 * pad_y), radius=th, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=fg)


# ── шаблоны ───────────────────────────────────────────────────

def template(name: str) -> Image.Image | None:
    p = TPL / f"{name}.jpg"
    return Image.open(p).convert("RGB") if p.exists() else None


def erase(img: Image.Image, box) -> None:
    """Стирает надпись-заглушку: построчный градиент между соседними пикселями панели."""
    x0, y0, x1, y1 = box
    px = img.load()
    rnd = random.Random(x0 * 31 + y0)

    def avg(xs, y):
        cs = [px[x, y] for x in xs]
        return [sum(c[i] for c in cs) / len(cs) for i in range(3)]

    for y in range(y0, y1):
        left, right = avg(range(x0 - 5, x0 - 1), y), avg(range(x1 + 1, x1 + 5), y)
        for x in range(x0, x1):
            t = (x - x0) / max(1, x1 - x0)
            n = rnd.randint(-3, 3)
            px[x, y] = tuple(int(left[i] + (right[i] - left[i]) * t + n) for i in range(3))


def save_jpg(img: Image.Image, path: Path) -> Path:
    img.convert("RGB").save(path, "JPEG", quality=93, optimize=True)
    return path


# ── карусель ──────────────────────────────────────────────────

def carousel(theme: Theme, tpl: str, accent: str, sel, date_text: str, folder: Path, is_event: bool) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    acc = hex_rgb(accent)
    paths = [save_jpg(_cover(theme, tpl, acc, sel.cover_title, date_text), folder / "01.jpg")]
    for i, item in enumerate(sel.items):
        layout = ROTATION[i % len(ROTATION)]
        img = template(f"{tpl}_{layout}")
        if img is None:                       # нет шаблона слайда → событие в квадрате обложки
            img = _boxed_item(theme, tpl, acc, item)
        else:
            _fill_layout(theme, img, layout, acc, item, is_event)
        paths.append(save_jpg(img, folder / f"{i + 2:02d}.jpg"))
    return paths


def _cover(theme, tpl, acc, title, date_text):
    img = template(f"{tpl}_cover") or Image.new("RGB", (W, H_POST), PANEL)
    for b in COVER_ERASE:
        erase(img, b)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = COVER_BOX
    f, lines, size = fit(d, theme, title, x1 - x0, 330, 64, 34, spacing=1.15)
    df = theme.font(30, False)
    block = len(lines) * int(size * 1.15) + 30 + 40
    y = y0 + (y1 - y0 - block) // 2
    y = draw_lines(d, x0, y, lines, f, size, acc, 1.15, "center", x1 - x0) + 30
    d.text((x0 + (x1 - x0 - d.textlength(date_text, font=df)) / 2, y), date_text, font=df, fill=DARK)
    return img


def _title(d, theme, acc, title: str, subtitle: str) -> None:
    x0, y0, x1, y1 = TITLE_BOX
    sub_h = 42 if subtitle else 0
    f, lines, size = fit(d, theme, title, x1 - x0, y1 - y0 - sub_h - 6, 50, 28, spacing=1.12)
    lines = lines[:3]
    y = draw_lines(d, x0, y0 + 2, lines, f, size, DARK, 1.12)
    if subtitle:
        sf = theme.font(30, False)
        d.text((x0, y + 4), ellipsize(d, subtitle, sf, x1 - x0), font=sf, fill=acc)


def _body(d, theme, box, text: str, footer: str = "", acc=GRAY) -> None:
    x0, y0, x1, y1 = box
    foot_h = 50 if footer else 0
    f, lines, size = fit(d, theme, text, x1 - x0, y1 - y0 - foot_h, 40, 22, bold=False, spacing=1.4)
    draw_lines(d, x0, y0, lines, f, size, DARK, 1.4)
    if footer:
        ff = theme.font(24, False)
        d.text((x0, y1 - 32), ellipsize(d, footer, ff, x1 - x0), font=ff, fill=acc)


def _fill_layout(theme, img, layout, acc, item, is_event):
    spec = LAYOUTS[layout]
    for b in spec["erase"]:
        erase(img, b)
    d = ImageDraw.Draw(img)
    meta = " · ".join(x for x in (item.when, item.place) if x)
    _title(d, theme, acc, item.title, meta if is_event else "")
    source = f"Mənbə: {item.source}"
    if len(spec["body"]) == 1:
        text = item.text if is_event or not meta else f"{meta}\n{item.text}"
        _body(d, theme, spec["body"][0], text, source, acc)
    else:
        # макет b: левый-верхний блок — суть, нижний — детали
        _body(d, theme, spec["body"][0], item.text)
        details = "\n".join(x for x in (
            f"Tarix: {item.when}" if item.when else "",
            f"Məkan: {item.place}" if item.place else "",
            source,
        ) if x)
        _body(d, theme, spec["body"][1], details, "", acc)


def _boxed_item(theme, tpl, acc, item):
    img = template(f"{tpl}_cover") or Image.new("RGB", (W, H_POST), PANEL)
    for b in COVER_ERASE:
        erase(img, b)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = COVER_BOX
    y = y0
    if item.when:
        wf = theme.font(32)
        d.text((x0, y), ellipsize(d, item.when, wf, x1 - x0), font=wf, fill=acc)
        y += 52
    f, lines, size = fit(d, theme, item.title, x1 - x0, 170, 44, 28, spacing=1.12)
    y = draw_lines(d, x0, y, lines, f, size, DARK, 1.12) + 12
    if item.place:
        pf = theme.font(26, False)
        d.text((x0, y), ellipsize(d, item.place, pf, x1 - x0), font=pf, fill=GRAY)
        y += 44
    _body(d, theme, (x0, y + 6, x1, y1), item.text, f"Mənbə: {item.source}", acc)
    return img


# ── сторис ────────────────────────────────────────────────────

def to_story(post: Image.Image) -> Image.Image:
    """Кадр 4:5 → 9:16: размытое продолжение фона сверху/снизу."""
    bg = ImageOps.fit(post, (W, H_STORY), Image.LANCZOS).filter(ImageFilter.GaussianBlur(30))
    bg.paste(post.convert(bg.mode), (0, (H_STORY - H_POST) // 2))
    return bg.convert("RGBA")


def story_promo(theme: Theme, cover_path: Path, accent: str, out: Path) -> Path:
    img = to_story(Image.open(cover_path).convert("RGB"))
    d = ImageDraw.Draw(img)
    f = theme.font(44)
    label = "YENİ POST"
    tw = d.textlength(label, font=f) + 56
    pill(d, ((W - tw) / 2, 140), label, f, hex_rgb(accent), (255, 255, 255))
    for text, y, size in (("Tam oxumaq üçün profilə keçin", H_STORY - 190, 40),):
        ff = theme.font(size)
        tw = d.textlength(text, font=ff)
        d.rounded_rectangle(((W - tw) / 2 - 30, y - 18, (W + tw) / 2 + 30, y + size + 18), radius=40, fill=(255, 255, 255))
        d.text(((W - tw) / 2, y), text, font=ff, fill=DARK)
    return save_jpg(img, out)


def wmo(code: int) -> tuple[str, str]:
    if code == 0:
        return "Günəşli", "sun"
    if code in (1, 2):
        return "Az buludlu", "partly"
    if code in (3, 45, 48):
        return "Buludlu", "cloud"
    if code in (80, 81, 82):
        return "Leysan", "sunrain"
    if 71 <= code <= 77 or code in (85, 86):
        return "Qar", "snow"
    return ("Tufan" if code >= 95 else "Yağış"), "rain"


@lru_cache(maxsize=None)
def _icon(kind: str, size: int) -> Image.Image | None:
    sheet = template("weather_icons")
    if sheet is None:
        return None
    ic = sheet.crop(ICON_BOXES[kind]).convert("RGBA")
    alpha = ImageOps.grayscale(ic).point(lambda v: 0 if v > 238 else 255)
    ic.putalpha(alpha)
    ic = ic.crop(alpha.getbbox())
    ic.thumbnail((size, size), Image.LANCZOS)
    return ic


def story_weather(theme: Theme, week: list[dict], today_idx: int, out: Path) -> Path:
    """week: [{name, days:[{code,max,min,rain}×7 (пн…вс)]}], первый — Praha."""
    img = template("weather") or Image.new("RGB", (W, H_POST), (60, 110, 170))
    d = ImageDraw.Draw(img, "RGBA")   # RGB-холст + RGBA-заливки = полупрозрачное смешивание
    white, soft = (255, 255, 255), (220, 232, 245)
    praha = week[0]["days"]
    t = praha[today_idx]
    text, kind = wmo(t["code"])

    # «Bugün Praha»: большая температура + иконка
    x0, y0, x1, _ = WX_TODAY_BOX
    d.text((x0 + 34, y0 + 30), f"{t['max']}°", font=theme.font(110), fill=white)
    d.text((x0 + 38, y0 + 160), f"{text} · {t['min']}°", font=theme.font(30, False), fill=soft)
    ic = _icon(kind, 150)
    if ic:
        img.paste(ic, (x1 - ic.width - 30, y0 + 30), ic)

    # строка дней Праги: максимумы, сегодняшний выделен
    for i, cx in enumerate(WX_PRAHA_COLS):
        s = f"{praha[i]['max']}°"
        f = theme.font(24 if i != today_idx else 26, i == today_idx)
        tw = d.textlength(s, font=f)
        if i == today_idx:
            d.rounded_rectangle((cx - tw / 2 - 8, WX_PRAHA_TEMP_Y - 4, cx + tw / 2 + 8, WX_PRAHA_TEMP_Y + 32),
                                radius=10, fill=(255, 255, 255, 70))
        d.text((cx - tw / 2, WX_PRAHA_TEMP_Y), s, font=f, fill=white)

    # таблица городов: иконка + максимум
    for r, cy in enumerate(WX_TABLE_ROWS):
        if r + 1 >= len(week):
            break
        for i, cx in enumerate(WX_TABLE_COLS):
            day = week[r + 1]["days"][i]
            ic = _icon(wmo(day["code"])[1], 28)
            s = f"{day['max']}°"
            f = theme.font(20, i == today_idx)
            tw = d.textlength(s, font=f)
            total = (ic.width + 3 if ic else 0) + tw
            x = cx - total / 2
            if ic:
                img.paste(ic, (int(x), int(cy - ic.height / 2)), ic)
                x += ic.width + 3
            d.text((x, cy - 12), s, font=f, fill=white)
    return save_jpg(to_story(img), out)


# ── плашки для Reels (прозрачный PNG 1080×1920) ──────────────

def _logo_band(img: Image.Image, theme: Theme, bottom_offset: int) -> None:
    d = ImageDraw.Draw(img)
    y = H_STORY - bottom_offset
    d.rounded_rectangle((200, y, W - 200, y + 150), radius=40, fill=(236, 235, 231, 235))
    if theme.logo is not None:
        logo = theme.logo.copy()
        logo.thumbnail((600, 120), Image.LANCZOS)
        img.alpha_composite(logo, ((W - logo.width) // 2, y + (150 - logo.height) // 2))
    else:
        f = theme.font(40)
        d.text(((W - d.textlength(theme.name, font=f)) / 2, y + 50), theme.name, font=f, fill=(20, 60, 120))


def _card(img, theme, acc, title: str, meta: str, top_hint: int | None, band: int) -> None:
    d = ImageDraw.Draw(img)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f, lines, size = fit(probe, theme, title, W - 260, 380, 68, 40, spacing=1.12)
    mf = theme.font(36, False)
    mlines = wrap(probe, meta, mf, W - 260)[:2] if meta else []
    h = len(lines) * int(size * 1.12) + len(mlines) * 48 + 90
    top = top_hint if top_hint is not None else H_STORY - band - 60 - h
    d.rounded_rectangle((80, top, W - 80, top + h), radius=24, fill=(236, 235, 231, 240))
    d.rectangle((104, top + 40, 116, top + h - 40), fill=acc)
    y = draw_lines(d, 140, top + 42, lines, f, size, DARK, 1.12)
    draw_lines(d, 140, y + 8, mlines, mf, 36, acc, 1.33)


def reel_intro_overlay(theme: Theme, title: str, date_text: str, accent: str, out: Path, band: int) -> Path:
    img = Image.new("RGBA", (W, H_STORY), (0, 0, 0, 60))
    _card(img, theme, hex_rgb(accent), title, date_text, 700, band)
    _logo_band(img, theme, band)
    img.save(out)
    return out


def reel_item_overlay(theme: Theme, label: str, accent: str, item, n: int, out: Path, band: int) -> Path:
    img = Image.new("RGBA", (W, H_STORY), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pill(d, (80, 230), f"{label}  {n:02d}", theme.font(38), hex_rgb(accent), (255, 255, 255))
    meta = " · ".join(x for x in (item.when, item.place) if x)
    _card(img, theme, hex_rgb(accent), item.title, meta, None, band)
    _logo_band(img, theme, band)
    img.save(out)
    return out


def reel_frame_from_slide(slide: Path, out: Path) -> Path:
    to_story(Image.open(slide).convert("RGB")).convert("RGB").save(out, "JPEG", quality=92)
    return out
