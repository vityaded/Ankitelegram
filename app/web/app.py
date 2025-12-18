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
        <form id="uploadForm" action="/upload" method="post" enctype="multipart/form-data">
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
            <label>Select .apkg files</label><br/>
            <input id="fileInput" type="file" name="files" accept=".apkg" multiple/>
            <div><small>You can select single or multiple .apkg files.</small></div>
          </div>
          <div class="row">
            <label>Select folder(s)</label><br/>
            <input id="folderInput" type="file" webkitdirectory directory multiple/>
            <div><small>All .apkg files inside the chosen folder(s) and subfolders will be imported.</small></div>
          </div>
          <div class="row">
            <div id="fileInfo"><small>No .apkg files selected yet.</small></div>
          </div>
          <div class="row">
            <button id="submitBtn" type="submit" disabled>Upload</button>
          </div>
        </form>
        <script>
        (function() {{
            const form = document.getElementById('uploadForm');
            const fileInput = document.getElementById('fileInput');
            const folderInput = document.getElementById('folderInput');
            const infoEl = document.getElementById('fileInfo');
            const submitBtn = document.getElementById('submitBtn');

            function apkgFiles() {{
                const files = [...(fileInput.files || []), ...(folderInput.files || [])];
                return files.filter(f => /\\.apkg$/i.test(f.name || ''));
            }}

            function updateInfo() {{
                const files = apkgFiles();
                const count = files.length;
                infoEl.textContent = count
                    ? `Found ${{count}} .apkg files in selected folder(s)`
                    : "No .apkg files selected yet.";
                submitBtn.disabled = count === 0;
            }}

            fileInput.addEventListener('change', updateInfo);
            folderInput.addEventListener('change', updateInfo);
            updateInfo();

            form.addEventListener('submit', async (ev) => {{
                ev.preventDefault();
                const files = apkgFiles();
                if (!files.length) {{
                    infoEl.textContent = "Please select at least one .apkg file or folder.";
                    return;
                }}
                submitBtn.disabled = true;
                submitBtn.textContent = "Uploading...";

                const fd = new FormData();
                fd.append("token", form.querySelector('input[name="token"]').value);
                fd.append("title", form.querySelector('input[name="title"]').value || "");
                fd.append("new_per_day", form.querySelector('input[name="new_per_day"]').value || "10");
                for (const f of files) {{
                    fd.append("files", f);
                    fd.append("paths", f.webkitRelativePath || f.name);
                }}
                try {{
                    const resp = await fetch("/upload", {{ method: "POST", body: fd }});
                    const text = await resp.text();
                    document.open();
                    document.write(text);
                    document.close();
                }} catch (e) {{
                    infoEl.textContent = "Upload failed. Please try again.";
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Upload";
                }}
            }});
        }})();
        </script>
        """
        return _html_page(body)

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_post(
        token: str = Form(...),
        title: str = Form(""),
        new_per_day: int = Form(10),
        file: UploadFile | None = File(None),
        files: list[UploadFile] | None = File(None),
        paths: list[str] = Form([]),
    ):
        td = verify_upload_token(settings.upload_secret, token)
        if not td or td.admin_id not in settings.admin_ids:
            return _html_page("<h3>Unauthorized</h3><p>Invalid or expired link.</p>")

        upload_files: list[UploadFile] = []
        if files:
            upload_files.extend(files)
        if file:
            upload_files.append(file)

        if not upload_files:
            return _html_page("<h3>Error</h3><p>Please upload at least one .apkg file.</p>")

        if paths and len(paths) != len(upload_files):
            return _html_page("<h3>Error</h3><p>Number of paths does not match number of files.</p>")

        if new_per_day < 1 or new_per_day > 500:
            return _html_page("<h3>Error</h3><p>new_per_day must be 1..500.</p>")

        os.makedirs(settings.import_tmp_dir, exist_ok=True)
        prefix = title.strip()
        valid_uploads: list[tuple[UploadFile, str | None]] = []
        skipped_invalid: list[str] = []

        for idx, upload_file in enumerate(upload_files):
            rel = (paths[idx] if paths else None) or (upload_file.filename or "")
            filename = upload_file.filename or rel or ""
            if not filename.lower().endswith(".apkg"):
                skipped_invalid.append(filename or "(unnamed file)")
                continue
            valid_uploads.append((upload_file, rel))

        if not valid_uploads:
            msg = "<h3>Error</h3><p>No valid .apkg files found.</p>"
            if skipped_invalid:
                msg += f"<p>Skipped: {', '.join(skipped_invalid)}</p>"
            return _html_page(msg)

        multiple_files = len(valid_uploads) > 1
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

        async def _bg_import_one(dest: Path, deck_title: str, folder_path: str | None):
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
                    folder_path=folder_path,
                )
                folder_line = f"\nFolder: {res['folder_path']}" if res.get("folder_path") else ""
                await bot.send_message(
                    td.admin_id,
                    f"Imported: {res['imported']}, skipped: {res['skipped']}\n"
                    f"Deck: {deck_title}{folder_line}\n"
                    f"Anki mode: {res['links']['anki']}\n"
                    f"Watch mode: {res['links']['watch']}",
                )
            except Exception as e:
                await bot.send_message(td.admin_id, f"Import failed: {type(e).__name__}: {e}")
            finally:
                dest.unlink(missing_ok=True)

        tasks: list[asyncio.Task] = []

        for upload_file, rel_path in valid_uploads:
            deck_title = _make_deck_title(upload_file)
            folder_part = Path(rel_path or "").parent.as_posix()
            folder_path = None if folder_part in ("", ".") else folder_part
            dest = Path(settings.import_tmp_dir) / f"web_{uuid.uuid4().hex}.apkg"

            # Stream-save to disk (avoid holding whole file in memory)
            with dest.open("wb") as f:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

            folder_line = f"\nFolder: {folder_path}" if folder_path else ""
            await bot.send_message(td.admin_id, f"Web upload received: {deck_title}{folder_line}\nImporting...")
            tasks.append(asyncio.create_task(_bg_import_one(dest, deck_title, folder_path)))

        if multiple_files:
            summary = f"Queued {len(tasks)} deck(s) for import. You can close this page."
        else:
            summary = "You can close this page. Results will arrive in Telegram."

        if skipped_invalid:
            summary += f" Skipped non-.apkg files: {', '.join(skipped_invalid)}."

        return _html_page(f"<h3>Upload complete</h3><p>{summary}</p>")

    return app
