"""Черновики в Telegram и ожидание подтверждения ("ok" / "no")."""
import json
import os
import time
from pathlib import Path

import requests

from .util import log

YES = {"ok", "ок", "да", "hə", "he", "yes", "+", "go"}
NO = {"no", "нет", "yox", "stop", "-"}


class Telegram:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat = os.environ.get("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat)

    def _api(self, method: str, **kw):
        r = requests.post(f"https://api.telegram.org/bot{self.token}/{method}", timeout=120, **kw)
        if not r.ok:
            log.warning("Telegram %s: %s", method, r.text[:300])
        return r.json() if r.ok else {}

    def text(self, msg: str) -> None:
        if self.enabled:
            # Telegram ограничивает сообщение 4096 символами
            for i in range(0, len(msg), 4000):
                self._api("sendMessage", data={"chat_id": self.chat, "text": msg[i:i + 4000]})

    def album(self, images: list[Path], caption: str = "") -> None:
        if not self.enabled:
            return
        for start in range(0, len(images), 10):
            chunk = images[start:start + 10]
            media, files = [], {}
            for i, p in enumerate(chunk):
                files[f"f{i}"] = open(p, "rb")
                item = {"type": "photo", "media": f"attach://f{i}"}
                if i == 0 and start == 0 and caption:
                    item["caption"] = caption[:1000]
                media.append(item)
            try:
                self._api("sendMediaGroup", data={"chat_id": self.chat, "media": json.dumps(media)}, files=files)
            finally:
                for f in files.values():
                    f.close()

    def video(self, path: Path, caption: str = "") -> None:
        if self.enabled:
            with open(path, "rb") as f:
                self._api("sendVideo", data={"chat_id": self.chat, "caption": caption[:1000]}, files={"video": f})

    def wait_for_answer(self, timeout_min: int) -> bool | None:
        """True = публиковать, False = отмена, None = ответа не было."""
        if not self.enabled:
            return None
        # пропускаем старые сообщения
        updates = self._api("getUpdates", data={"timeout": 0}).get("result", [])
        offset = updates[-1]["update_id"] + 1 if updates else 0
        deadline = time.time() + timeout_min * 60
        while time.time() < deadline:
            res = self._api("getUpdates", data={"offset": offset, "timeout": 50}).get("result", [])
            for u in res:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != str(self.chat):
                    continue
                word = (msg.get("text") or "").strip().lower()
                if word in YES:
                    return True
                if word in NO:
                    return False
        return None
