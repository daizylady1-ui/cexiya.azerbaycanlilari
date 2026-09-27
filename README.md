# Cexiya Azərbaycanlıları — автопостинг в Instagram

Каждое утро (07:00 по Праге) бесплатно в GitHub Actions:

| Что | Содержимое |
|---|---|
| **3 карусели** | Faydalı məlumatlar (законы) · Maraqlı tədbirlər · Son xəbərlər (без криминала) — обложка + слайд на каждый пункт |
| **2 Reels** | «Bu həftə Praqada» (афиша) и «Günün xəbərləri» (новости + законы): видео-фон, текст, **логотип внизу** |
| **6 сторис** | погода на неделю (Praha, Brno, Plzen, Ostrava) + анонсы 3 постов + 2 Reels |

Весь текст — на азербайджанском (перевод и отбор делает Claude).
Перед публикацией черновики приходят в **Telegram**: отвечаете `ok` — публикуется, `no` — отмена.

```
Источники (RSS, сайты) ──► Claude: отбор + перевод ──► Pillow: слайды/сторис
        Pexels / ваши видео ──► ffmpeg: Reels ──► Telegram (ok?) ──► Instagram Graph API
```

---

## Настройка (один раз, ~1 час)

### 1. Instagram → профессиональный аккаунт
Instagram → Настройки → «Тип аккаунта» → **Бизнес** (или Автор) → привяжите к **Facebook-странице**.

### 2. Токен Instagram Graph API
1. <https://developers.facebook.com> → *Create App* → тип **Business**.
2. Добавьте продукт **Instagram** → «API setup with Facebook login».
3. <https://business.facebook.com> → Настройки → **Системные пользователи** → создать (роль Admin) →
   «Назначить активы»: ваша страница + Instagram-аккаунт + приложение.
4. «Создать токен» → выбрать приложение → разрешения:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`.
   Токен системного пользователя **не истекает** (обычный — через 60 дней).
5. Узнайте `IG_USER_ID`: в [Graph API Explorer](https://developers.facebook.com/tools/explorer/) запрос
   `me/accounts?fields=instagram_business_account` → поле `instagram_business_account.id`.

### 3. Остальные ключи
- **ANTHROPIC_API_KEY** — <https://console.anthropic.com> (≈ несколько центов в день).
- **PEXELS_API_KEY** — <https://www.pexels.com/api/> (бесплатно; стоковые видео для фона Reels).
- **Telegram**: в @BotFather → `/newbot` → получите **TELEGRAM_BOT_TOKEN**. Напишите боту любое сообщение,
  откройте `https://api.telegram.org/bot<ТОКЕН>/getUpdates` → `chat.id` = **TELEGRAM_CHAT_ID**.

### 4. GitHub
1. Создайте **публичный** репозиторий (публичный нужен, чтобы Instagram мог скачать картинки/видео по ссылке;
   секреты при этом скрыты) и загрузите туда эту папку.
2. *Settings → Secrets and variables → Actions → New repository secret*:
   `ANTHROPIC_API_KEY`, `PEXELS_API_KEY`, `IG_USER_ID`, `IG_ACCESS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. *Actions* → «Daily Instagram» → **Run workflow** — первый тестовый запуск.

### 5. Ваш стиль (из архива «Çexiya esas.zip»)
| Файл | Куда положить |
|---|---|
| логотип на сером фоне | `assets/logo.jpg` (фон вырезается автоматически) |
| шаблоны Canva | уже лежат в `assets/templates/`: `news_*`, `info_*` (faydalı məlumatlar → законы), `events_cover`, `weather`, `weather_icons`, `places_*` (на будущее) |
| 4 слайда «maraqlı tədbirlər» (Title/body text) | `assets/templates/events_c.jpg` (большой текст), `events_b.jpg` (2 текста + 2 фото), `events_a.jpg` (текст + 3 фото), `events_d.jpg` (одна панель). Пока их нет — события рисуются в квадрате обложки |
| `Çexiya esas.mp4` | `assets/clips/intro.mp4` — будет заставкой каждого Reels |
| ваши другие видео | `assets/clips/*.mp4` — фоны для Reels |
| музыка без авторских прав | `assets/music/*.mp3` |
| шрифт **Garet** (Heavy + Book) | `assets/fonts/Garet-Heavy.otf`, `assets/fonts/Garet-Book.otf` (бесплатно на сайте Type Forward) |

Цвета, хэштеги, источники, число пунктов, время — всё в [config.yaml](config.yaml).

---

## Локальный запуск (для проверки дизайна)

```bash
pip install -r requirements.txt
```
```bash
set ANTHROPIC_API_KEY=sk-ant-...        # Windows (на macOS/Linux: export)
```
```bash
python -m cexiya generate
```
Результат — в папке `out/<дата>/`: слайды, `reel_events.mp4`, `reel_news.mp4`, сторис, `manifest.json`.

```bash
python -m cexiya publish --dry-run
```

---

## Важно
- **Instagram-аккаунты** (vanessa.eats.prague, czech_guide, expatscz, pragueforexpats) не парсятся:
  это запрещено правилами Instagram. Смотрите их вручную для идей.
- **Чужие видео и фото** не скачиваются — фоны Reels берутся из ваших клипов и Pexels (свободная лицензия).
  Если хотите использовать видео другого автора — только с его разрешения, положив файл в `assets/clips/`.
- Факты Claude берёт только из источников и пишет «Mənbə», но **проверяйте черновик** в Telegram перед `ok`.
- Лимит API Instagram — 50 публикаций в сутки; мы делаем 11.
- Время: cron `0 5 * * *` в UTC = 07:00 летом / 06:00 зимой. Поменять — в `.github/workflows/daily.yml`.
