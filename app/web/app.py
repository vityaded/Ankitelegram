from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from aiogram import Bot

from app.services.admin_auth import verify_upload_token
from app.services.import_service import import_apkg_from_path

def create_web_app(
    *,
    settings,
    bot: Bot,
    bot_username: str,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> FastAPI:
    app = FastAPI(title="anki_listen_bot uploader")

    def _html_page(body: str) -> HTMLResponse:
        return HTMLResponse(f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Anki Deck Upload</title>
  <style>
    body{{font-family:Arial, sans-serif; max-width:720px; margin:40px auto; padding:0 16px;}}
    .card{{border:1px solid #ddd; border-radius:12px; padding:16px;}}
    input,button{{font-size:16px; padding:8px;}}
    .row{{margin:12px 0;}}
    small{{color:#666;}}
  </style>
</head>
<body>
  <div class="card">
    {body}
  </div>
</body>
</html>""")

    @app.get("/healthz")
    async def healthz():
        return PlainTextResponse("ok")

    @app.get("/upload", response_class=HTMLResponse)
    async def upload_get(token: str = Query(...)):
        td = verify_upload_token(settings.upload_secret, token)
        if not td or td.admin_id not in settings.admin_ids:
            return _html_page("<h3>Unauthorized</h3><p>Invalid or expired link.</p>")

        body = f"""
        <h2>Upload .apkg (large deck)</h2>
        <p><small>After upload finishes, you will receive a Telegram message with the deck link.</small></p>
        <form action="/upload" method="post" enctype="multipart/form-data">
          <input type="hidden" name="token" value="{token}"/>
          <div class="row">
            <label>Deck title (optional)</label><br/>
            <input type="text" name="title" style="width:100%" placeholder="My deck"/>
          </div>
          <div class="row">
            <label>New cards per day</label><br/>
            <input type="number" name="new_per_day" min="1" max="500" value="10"/>
          </div>
          <div class="row">
            <input type="file" name="files" accept=".apkg" multiple required/>
            <div><small>You can select multiple .apkg files.</small></div>
          </div>
          <div class="row">
            <button type="submit">Upload</button>
          </div>
        </form>
        """
        return _html_page(body)

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_post(
        token: str = Form(...),
        title: str = Form(""),
        new_per_day: int = Form(10),
        file: UploadFile | None = File(None),
        files: list[UploadFile] | None = File(None),
    ):
        td = verify_upload_token(settings.upload_secret, token)
        if not td or td.admin_id not in settings.admin_ids:
            return _html_page("<h3>Unauthorized</h3><p>Invalid or expired link.</p>")

        upload_files: list[UploadFile] = []
        if files:
            upload_files.extend(files)
        elif file:
            upload_files.append(file)

        if not upload_files:
            return _html_page("<h3>Error</h3><p>Please upload at least one .apkg file.</p>")

        bad = [f.filename for f in upload_files if not (f.filename and f.filename.lower().endswith(".apkg"))]
        if bad:
            return _html_page("<h3>Error</h3><p>Only .apkg files are allowed.</p>")

        if new_per_day < 1 or new_per_day > 500:
            return _html_page("<h3>Error</h3><p>new_per_day must be 1..500.</p>")

        os.makedirs(settings.import_tmp_dir, exist_ok=True)
        prefix = title.strip()
        multiple_files = len(upload_files) > 1
        seen_titles: dict[str, int] = {}

        def _make_deck_title(upload_file: UploadFile) -> str:
            filename = upload_file.filename or "Deck"
            stem = Path(filename).stem if upload_file.filename else "Deck"
            if multiple_files:
                base = stem if not prefix else f"{prefix} - {stem}"
            else:
                base = prefix or filename or "Deck"
            count = seen_titles.get(base, 0) + 1
            seen_titles[base] = count
            if count > 1:
                return f"{base} ({count})"
            return base

        async def _bg_import_one(dest: Path, deck_title: str):
            try:
                res = await import_apkg_from_path(
                    settings=settings,
                    bot=bot,
                    bot_username=bot_username,
                    sessionmaker=sessionmaker,
                    admin_tg_id=td.admin_id,
                    apkg_path=str(dest),
                    deck_title=deck_title,
                    new_per_day=new_per_day,
                )
                await bot.send_message(
                    td.admin_id,
                    f"Imported: {res['imported']}, skipped: {res['skipped']}\n"
                    f"Anki mode: {res['links']['anki']}\n"
                    f"Watch mode: {res['links']['watch']}",
                )
            except Exception as e:
                await bot.send_message(td.admin_id, f"Import failed: {type(e).__name__}: {e}")
            finally:
                dest.unlink(missing_ok=True)

        tasks: list[asyncio.Task] = []

        for upload_file in upload_files:
            deck_title = _make_deck_title(upload_file)
            dest = Path(settings.import_tmp_dir) / f"web_{uuid.uuid4().hex}.apkg"

            # Stream-save to disk (avoid holding whole file in memory)
            with dest.open("wb") as f:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

            await bot.send_message(td.admin_id, f"Web upload received: {deck_title}\nImporting...")
            tasks.append(asyncio.create_task(_bg_import_one(dest, deck_title)))

        if multiple_files:
            summary = f"Queued {len(tasks)} deck(s) for import. You can close this page."
        else:
            summary = "You can close this page. Results will arrive in Telegram."

        return _html_page(f"<h3>Upload complete</h3><p>{summary}</p>")

    return app
