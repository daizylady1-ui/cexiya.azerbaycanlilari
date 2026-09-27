"""
Ежедневный контент для @cexiyaazerbaycanlilari.

    python -m cexiya generate            # собрать материалы, сделать 3 карусели, 2 Reels, 6 сторис
    python -m cexiya publish             # (после загрузки файлов в ветку media) подтвердить и опубликовать
    python -m cexiya publish --dry-run   # показать, что и по каким ссылкам будет опубликовано
"""
import argparse
import logging
import random
import sys
import time
from pathlib import Path

from . import ai, render, sources, video, weather
from . import publish as ig_api
from .telegram import Telegram
from .util import ROOT, date_az, log, load_config, out_dir, read_json, today, write_json

STATE = ROOT / "state" / "used_urls.json"


def _caption(text: str, items, cfg: dict) -> str:
    srcs = ", ".join(dict.fromkeys(i.source for i in items if i.source))
    parts = [text.strip()]
    if srcs:
        parts.append(f"Mənbələr: {srcs}")
    parts.append(cfg["account"]["hashtags"])
    return "\n\n".join(parts)[:2200]  # лимит подписи Instagram


def generate(cfg: dict, date_str: str) -> None:
    now = today(cfg)
    date_text = date_az(now)
    folder = out_dir(date_str)
    rel = lambda p: Path(p).relative_to(folder).as_posix()  # noqa: E731
    theme = render.Theme(cfg)
    used = set(read_json(STATE, []))
    manifest = {"date": date_str, "posts": [], "reels": [], "stories": []}
    picked: dict[str, list] = {}       # key -> [(item, slide_path, carousel_cfg)]
    selections: dict[str, ai.Selection] = {}

    # ── 1. Погода (шаблон «Həftəlik hava məlumatı») ──
    week = weather.week_forecast(cfg["weather_cities"], cfg["timezone"], now)
    if week:
        p = render.story_weather(theme, week, now.weekday(), folder / "story_1_weather.jpg")
        manifest["stories"].append({"kind": "weather", "file": rel(p), "video": False})

    # ── 2. Три карусели ──
    for c in cfg["carousels"]:
        key = c["key"]
        log.info("Раздел %s: сбор материалов", key)
        material = sources.collect(cfg["sources"].get(key, {}), cfg["ai"]["max_page_chars"], used)
        sel = ai.select(cfg, c["brief"], material, c["max_items"], date_text)
        if not sel or not sel.items:
            log.warning("Раздел %s пропущен: нет подходящих материалов", key)
            continue
        selections[key] = sel
        write_json(folder / f"{key}.json", sel.model_dump())
        slides = render.carousel(theme, c["template"], c["accent"], sel, date_text, folder / key,
                                 is_event=c.get("events", False))
        picked[key] = [(item, slide, c) for item, slide in zip(sel.items, slides[1:])]
        manifest["posts"].append({"key": key, "accent": c["accent"], "files": [rel(s) for s in slides],
                                  "caption": _caption(sel.caption, sel.items, cfg)})
        used.update(i.url for i in sel.items)

    # ── 3. Два Reels ──
    rs = cfg["reel_settings"]
    band = rs["logo_band_bottom"]
    cache = ROOT / ".cache" / "clips"
    clips = video.own_clips()
    intro_clip = ROOT / rs["intro_clip"] if rs.get("intro_clip") else None
    for r in cfg["reels"]:
        pairs = [pair for k in r["from"] for pair in picked.get(k, [])][: r["max_items"]]
        if not pairs:
            continue
        log.info("Reels %s: %d сюжетов", r["key"], len(pairs))
        work = folder / r["key"]
        work.mkdir(exist_ok=True)
        main_c = pairs[0][2]
        segs = []

        ov = render.reel_intro_overlay(theme, r["title"], date_text, main_c["accent"], work / "ov_0.png", band)
        bg = (intro_clip if intro_clip and intro_clip.exists() else None) \
            or video.pexels_clip("Prague city", cache) or (random.choice(clips) if clips else None)
        if bg:
            segs.append(video.segment_from_clip(bg, ov, rs["intro_seconds"], work / "seg_0.mp4"))
        else:
            frame = render.reel_frame_from_slide(folder / main_c["key"] / "01.jpg", work / "fr_0.jpg")
            segs.append(video.segment_from_image(frame, None, rs["intro_seconds"], work / "seg_0.mp4"))

        for n, (item, slide, c) in enumerate(pairs, start=1):
            ov = render.reel_item_overlay(theme, c["label"], c["accent"], item, n, work / f"ov_{n}.png", band)
            bg = video.pexels_clip(item.video_query, cache) or (random.choice(clips) if clips else None)
            if bg:
                segs.append(video.segment_from_clip(bg, ov, rs["seconds_per_item"], work / f"seg_{n}.mp4"))
            else:
                frame = render.reel_frame_from_slide(slide, work / f"fr_{n}.jpg")
                segs.append(video.segment_from_image(frame, None, rs["seconds_per_item"], work / f"seg_{n}.mp4"))

        out = video.assemble(segs, folder / f"{r['key']}.mp4", ROOT / rs["music_dir"])
        for tmp in work.glob("*"):
            tmp.unlink()
        work.rmdir()
        items = [p[0] for p in pairs]
        manifest["reels"].append({"key": r["key"], "file": rel(out),
                                  "caption": _caption(selections[main_c["key"]].reel_caption, items, cfg)})

    # ── 4. Сторис: анонсы 3 постов + 2 Reels ──
    for n, post in enumerate(manifest["posts"], start=2):
        p = render.story_promo(theme, folder / post["files"][0], post["accent"], folder / f"story_{n}_{post['key']}.jpg")
        manifest["stories"].append({"kind": "promo", "file": rel(p), "video": False})
    for reel in manifest["reels"]:
        manifest["stories"].append({"kind": "reel", "file": reel["file"], "video": True})

    write_json(folder / "manifest.json", manifest)
    write_json(STATE, sorted(used)[-800:])
    log.info("Готово: %d постов, %d Reels, %d сторис → %s",
             len(manifest["posts"]), len(manifest["reels"]), len(manifest["stories"]), folder)


def publish(cfg: dict, date_str: str, dry_run: bool, no_approval: bool) -> int:
    folder = ROOT / "out" / date_str
    manifest = read_json(folder / "manifest.json", None)
    if not manifest:
        log.error("Нет %s/manifest.json — сначала запустите generate", folder)
        return 1
    url = lambda f: ig_api.media_url(cfg, f"{date_str}/{f}")  # noqa: E731

    tg = Telegram()
    need_ok = cfg["publish"]["approval"] == "telegram" and not no_approval and not dry_run
    if need_ok:
        if not tg.enabled:
            log.error("approval=telegram, но TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы")
            return 1
        tg.text(f"Черновики на {date_str}. Проверьте ↓")
        for post in manifest["posts"]:
            tg.album([folder / f for f in post["files"]], post["caption"])
        for reel in manifest["reels"]:
            tg.video(folder / reel["file"], reel["caption"])
        tg.album([folder / s["file"] for s in manifest["stories"] if not s["video"]], "Сторис")
        tg.text(f"Ответьте ok — опубликовать всё, no — отменить. Жду {cfg['publish']['approval_timeout_min']} мин.")
        answer = tg.wait_for_answer(cfg["publish"]["approval_timeout_min"])
        if answer is not True:
            tg.text("Публикация отменена." if answer is False else "Ответа не было — публикация отменена.")
            return 0

    # порядок: погода → посты → Reels → анонсы постов → Reels в сторис
    stories = manifest["stories"]
    plan = [("story", s) for s in stories if s["kind"] == "weather"] \
        + [("post", p) for p in manifest["posts"]] \
        + [("reel", r) for r in manifest["reels"]] \
        + [("story", s) for s in stories if s["kind"] != "weather"]

    if dry_run:
        for kind, x in plan:
            files = x.get("files") or [x["file"]]
            print(kind.upper(), *[url(f) for f in files], sep="\n  ")
        return 0

    ig = ig_api.Instagram(cfg)
    done, failed = [], []
    for kind, x in plan:
        try:
            if kind == "post":
                mid = ig.carousel([url(f) for f in x["files"]], x["caption"])
            elif kind == "reel":
                mid = ig.reel(url(x["file"]), x["caption"])
            else:
                mid = ig.story(url(x["file"]), x["video"])
            done.append(f"✅ {kind} {x.get('key', x.get('kind'))}: {ig.permalink(mid)}")
            log.info(done[-1])
        except (ig_api.InstagramError, KeyError, ValueError) as e:
            failed.append(f"❌ {kind} {x.get('key', x.get('kind'))}: {e}")
            log.error(failed[-1])
        time.sleep(cfg["publish"]["gap_seconds"])
    tg.text("\n".join(done + failed) or "Нечего публиковать")
    return 1 if failed else 0



def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="cexiya")
    ap.add_argument("command", choices=["generate", "publish"])
    ap.add_argument("--date", help="YYYY-MM-DD (по умолчанию сегодня, Прага)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-approval", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    date_str = args.date or today(cfg).strftime("%Y-%m-%d")
    if args.command == "generate":
        generate(cfg, date_str)
        return 0
    return publish(cfg, date_str, args.dry_run, args.no_approval)


if __name__ == "__main__":
    sys.exit(main())
