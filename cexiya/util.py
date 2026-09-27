import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("cexiya")

MONTHS_AZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun",
             "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
WEEKDAYS_AZ = ["Bazar ertəsi", "Çərşənbə axşamı", "Çərşənbə", "Cümə axşamı",
               "Cümə", "Şənbə", "Bazar"]


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def today(cfg: dict) -> datetime:
    return datetime.now(ZoneInfo(cfg.get("timezone", "Europe/Prague")))


def date_az(d: datetime) -> str:
    return f"{d.day} {MONTHS_AZ[d.month - 1]}, {WEEKDAYS_AZ[d.weekday()]}"


def out_dir(date_str: str) -> Path:
    p = ROOT / "out" / date_str
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
