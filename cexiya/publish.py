"""Публикация через официальный Instagram Graph API (контент-паблишинг)."""
import os
import time

import requests

from .util import log


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, cfg: dict):
        self.base = f"https://graph.facebook.com/{cfg['publish']['graph_version']}"
        self.user = os.environ["IG_USER_ID"]
        self.token = os.environ["IG_ACCESS_TOKEN"]

    def _post(self, path: str, **data) -> dict:
        r = requests.post(f"{self.base}/{path}", data={**data, "access_token": self.token}, timeout=120)
        body = r.json()
        if not r.ok or "error" in body:
            raise InstagramError(f"{path}: {body.get('error', body)}")
        return body

    def _wait(self, container: str, timeout: int = 900) -> None:
        """Видео обрабатывается асинхронно — ждём status_code=FINISHED."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(f"{self.base}/{container}",
                             params={"fields": "status_code,status", "access_token": self.token}, timeout=60).json()
            status = r.get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Контейнер {container}: {r.get('status')}")
            time.sleep(10)
        raise InstagramError(f"Контейнер {container} не обработан за {timeout} с")

    def _publish(self, container: str) -> str:
        self._wait(container)
        return self._post(f"{self.user}/media_publish", creation_id=container)["id"]

    def carousel(self, image_urls: list[str], caption: str) -> str:
        children = [self._post(f"{self.user}/media", image_url=u, is_carousel_item="true")["id"] for u in image_urls]
        for c in children:
            self._wait(c)
        parent = self._post(f"{self.user}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)
        return self._publish(parent["id"])

    def reel(self, video_url: str, caption: str) -> str:
        c = self._post(f"{self.user}/media", media_type="REELS", video_url=video_url,
                       caption=caption, share_to_feed="true")
        return self._publish(c["id"])

    def story(self, url: str, is_video: bool) -> str:
        kind = "video_url" if is_video else "image_url"
        c = self._post(f"{self.user}/media", media_type="STORIES", **{kind: url})
        return self._publish(c["id"])

    def permalink(self, media_id: str) -> str:
        r = requests.get(f"{self.base}/{media_id}", params={"fields": "permalink", "access_token": self.token}, timeout=30)
        return r.json().get("permalink", media_id)


def media_url(cfg: dict, rel_path: str) -> str:
    return cfg["publish"]["media_url_template"].format(
        repo=os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO"), sha=os.environ.get("MEDIA_SHA", "media"), path=rel_path)
