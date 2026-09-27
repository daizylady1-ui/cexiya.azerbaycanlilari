"""Отбор материалов и перевод на азербайджанский с помощью Claude."""
import anthropic
from pydantic import BaseModel, Field

from .util import log

SYSTEM = """Sən "Cexiya Azərbaycanlıları" (@cexiyaazerbaycanlilari) Instagram səhifəsinin redaktorusan.
Auditoriya: Çexiyada yaşayan azərbaycanlılar. Bütün mətnləri səlis, sadə AZƏRBAYCAN dilində (latın əlifbası) yaz.

Qaydalar:
- YALNIZ verilmiş materialdakı faktlardan istifadə et. Heç nə uydurma: tarix, saat, qiymət, məkan yoxdursa, boş saxla.
- Hər maddənin "url" sahəsinə materialdakı orijinal linki yaz (başqa link uydurma).
- "source" — mənbənin qısa adı (məs. "iROZHLAS", "prague.eu").
- Başlıqlar qısa və cəlbedici (maks. 70 simvol), mətn 1-3 cümlə (maks. 260 simvol).
- Çex yer adlarını Azərbaycan oxunuşuna uyğun yaz, lazım olsa mötərizədə orijinalı ver.
- "video_query" — bu mövzu üçün stok video axtarışı üçün 1-3 İNGİLİS sözü (məs. "Prague tram", "concert crowd").
- Uyğun material azdırsa, az maddə qaytar; zəif və ya köhnə materialı əlavə etmə.
- "caption" — Instagram post mətni: 1 cəlbedici giriş cümləsi, sonra hər maddə üçün emoji + 1 sətir,
  sonda "Faydalı olsa, yadda saxlayın və dostlarınızla paylaşın!". Heşteq YAZMA (onları sistem əlavə edir).
- "reel_caption" — Reels üçün 1-2 cümləlik qısa mətn."""


class Item(BaseModel):
    title: str
    text: str
    when: str = Field(description="Tədbirlər üçün tarix və saat, məs. '28 sentyabr, 19:00'; xəbərlər üçün boş")
    place: str = Field(description="Tədbir məkanı/şəhər; yoxdursa boş")
    source: str
    url: str
    video_query: str


class Selection(BaseModel):
    cover_title: str = Field(description="Karusel üz qabığı üçün maks. 45 simvolluq başlıq")
    items: list[Item]
    caption: str
    reel_caption: str


def select(cfg: dict, brief: str, material: str, max_items: int, date_text: str) -> Selection | None:
    if not material.strip():
        log.warning("Нет материала для раздела")
        return None
    client = anthropic.Anthropic()
    prompt = (
        f"Bu gün: {date_text}.\n\nTAPŞIRIQ:\n{brief}\n\n"
        f"Ən yaxşı {max_items} maddəni seç (maksimum {max_items}).\n\n"
        f"MATERİAL:\n{material}"
    )
    response = client.messages.parse(
        model=cfg["ai"]["model"],
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=Selection,
    )
    if response.stop_reason == "refusal":
        log.warning("Claude отказался обрабатывать раздел")
        return None
    sel: Selection = response.parsed_output
    sel.items = sel.items[:max_items]
    return sel
