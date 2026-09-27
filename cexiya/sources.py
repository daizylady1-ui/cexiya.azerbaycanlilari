"""Сбор сырых материалов: RSS-ленты и текст обычных страниц."""
import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from .util import log

UA = {"User-Agent": "Mozilla/5.0 (compatible; CexiyaBot/1.0; +https://instagram.com/cexiyaazerbaycanlilari)"}


@dataclass
class Candidate:
    title: str
    summary: str
    url: str
    source: str
    published: str = ""


def _gnews_url(query: str) -> str:
    # Google News RSS: свежие (за сутки) новости на чешском
    return f"https://news.google.com/rss/search?q={quote_plus(query + ' when:1d')}&hl=cs&gl=CZ&ceid=CZ:cs"


def _clean(html: str, limit: int = 400) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def fetch_rss(spec: str, limit: int = 15) -> list[Candidate]:
    url = _gnews_url(spec[6:]) if spec.startswith("gnews:") else spec
    try:
        resp = requests.get(url, headers=UA, timeout=25)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("RSS %s: %s", spec, e)
        return []
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries[:limit]:
        src = getattr(getattr(e, "source", None), "title", None) or urlparse(url).netloc
        items.append(Candidate(
            title=e.get("title", "").strip(),
            summary=_clean(e.get("summary", "")),
            url=e.get("link", ""),
            source=src,
            published=e.get("published", ""),
        ))
    return items


def fetch_page(url: str, max_chars: int) -> str:
    """Возвращает читаемый текст страницы + ссылки (чтобы Claude мог указать источник)."""
    try:
        resp = requests.get(url, headers=UA, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Page %s: %s", url, e)
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "footer", "form"]):
        tag.decompose()
    # Заменяем ссылки на "текст [url]", чтобы сохранить адреса событий/статей
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        label = a.get_text(" ", strip=True)
        if label and len(label) > 12 and href.startswith("http"):
            a.replace_with(f"{label} [{href}]")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return text[:max_chars]


def collect(section: dict, max_page_chars: int, used_urls: set[str]) -> str:
    """Собирает весь материал раздела в один текстовый блок для Claude."""
    parts = []
    for spec in section.get("rss", []) or []:
        for c in fetch_rss(spec):
            if c.url in used_urls:
                continue
            parts.append(f"- {c.title} | {c.summary} | источник: {c.source} | {c.published} | {c.url}")
    for url in section.get("pages", []) or []:
        text = fetch_page(url, max_page_chars)
        if text:
            parts.append(f"\n=== СТРАНИЦА {url} ===\n{text}")
    log.info("Собрано %d блоков материала", len(parts))
    return "\n".join(parts)
