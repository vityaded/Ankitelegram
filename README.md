# anki_listen_bot (Telegram-only listening SRS)

## What it does
- Admin uploads an `.apkg` (video/audio on front, subtitle text on back).
- Bot imports, caches Telegram `file_id`, asks admin only `new_per_day`.
- Bot returns student link: `t.me/<bot>?start=deck_<token>`
- Student flow: open deck link -> media is sent immediately -> type answer -> immediate compare -> auto-next in 1 second.
- Daily: at 07:00 (TZ), bot sends the first card for each enrolled deck.
- When finished: "It's all for today" + button **Study more**.
- Button: **Bad card** (flags + suspends that card for that student, no penalty).

## Requirements
- Python 3.11+ recommended
- A Telegram bot token from BotFather

## Install (venv)
```bash
cd anki_listen_bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # set BOT_TOKEN and optionally DATABASE_URL
```

## Run
```bash
source .venv/bin/activate
python -m app.main
```

## Notes about `.apkg` format
- Bot expects:
  - Front contains media reference (`[sound:...]` or `<video ... src="...">`)
  - Back contains subtitle text (plain or HTML)
  - Optional alternative answers separated by `||`

## Troubleshooting
- If media upload fails for some cards, they will be skipped and reported.
- Very large videos may exceed Telegram limits; prefer short snippets.

## Large deck uploads (web)
- Set `ADMIN_IDS` and `UPLOAD_SECRET` in `.env`
- Set `WEB_BASE_URL` to your public URL (domain + port)
- Run `python -m app.main`
- In Telegram, admins will see **Upload deck (large)** button on /start
