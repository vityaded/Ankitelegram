from __future__ import annotations

import asyncio
import html
import os
import uuid
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from aiogram import Bot

from app.db.repo import (
    count_enrolled_students,
    count_ungrouped_decks,
    compute_overall_progress,
    count_decks_in_folder,
    delete_folder,
    delete_folder_if_empty,
    get_deck_by_id,
    get_folder_by_id,
    list_admin_folders,
    list_all_folders,
    list_decks_in_folder,
    list_enrolled_students,
    list_ungrouped_decks,
    reassign_decks_from_folder,
    update_deck_folder,
    update_deck_title,
    update_folder_path,
)
from app.services.admin_auth import verify_upload_token
from app.services.import_service import import_apkg_from_path
from app.services.stats_service import admin_stats
from app.services.student_progress import get_deck_user_study_counts

def create_web_app(
    *,
    settings,
    bot: Bot,
    bot_username: str,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> FastAPI:
    app = FastAPI(title="anki_listen_bot uploader")
    import_sem = asyncio.Semaphore(max(1, int(getattr(settings, "import_concurrency", 1) or 1)))

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

    def _is_admin_id(admin_id: int) -> bool:
        return (not settings.admin_ids) or (admin_id in settings.admin_ids)

    def _escape(text: str | None) -> str:
        return html.escape(text or "")

    def _folder_label(folder) -> str:
        if settings.admin_ids:
            return f"{folder.admin_tg_id} · {folder.path}"
        return folder.path

    def _admin_required(token: str | None) -> tuple[int | None, HTMLResponse | None]:
        if not token:
            return None, _html_page("<h3>Unauthorized</h3><p>Missing token.</p>")
        td = verify_upload_token(settings.upload_secret, token)
        if not td or not _is_admin_id(td.admin_id):
            return None, _html_page("<h3>Unauthorized</h3><p>Invalid or expired link.</p>")
        return td.admin_id, None

    def _admin_nav(token: str) -> str:
        return f'<p><a href="/admin?token={token}">Admin home</a></p>'

    @app.get("/healthz")
    async def healthz():
        return PlainTextResponse("ok")

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_root(token: str = Query(None)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            if settings.admin_ids:
                folders = await list_all_folders(session)
                ungrouped_count = await count_ungrouped_decks(session, None)
            else:
                folders = await list_admin_folders(session, admin_id)
                ungrouped_count = await count_ungrouped_decks(session, admin_id)

        folder_items = "".join(
            f'<li><a href="/admin/folders/{folder.id}?token={token}">{_escape(_folder_label(folder))}</a></li>'
            for folder in folders
        )
        folder_html = f"<ul>{folder_items}</ul>" if folder_items else "<p>No folders found.</p>"

        ungrouped_link = ""
        if ungrouped_count:
            ungrouped_link = (
                f'<p><a href="/admin/ungrouped?token={token}">'
                f"Ungrouped decks ({ungrouped_count})</a></p>"
            )

        body = f"""
        <h2>Admin control panel</h2>
        <h3>Folders</h3>
        {folder_html}
        {ungrouped_link}
        <p><a href="/upload?token={token}">Upload decks</a></p>
        """
        return _html_page(body)

    @app.get("/admin/ungrouped", response_class=HTMLResponse)
    async def admin_ungrouped(token: str = Query(None)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            admin_filter = None if settings.admin_ids else admin_id
            decks = await list_ungrouped_decks(session, admin_filter)

        deck_items = "".join(
            f'<li><a href="/admin/decks/{deck.id}?token={token}">{_escape(deck.title)}</a></li>'
            for deck in decks
        )
        deck_html = f"<ul>{deck_items}</ul>" if deck_items else "<p>No ungrouped decks.</p>"
        body = f"""
        {_admin_nav(token)}
        <h2>Ungrouped decks</h2>
        {deck_html}
        """
        return _html_page(body)

    @app.get("/admin/folders/{folder_id}", response_class=HTMLResponse)
    async def admin_folder(folder_id: str, token: str = Query(None)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            folder = await get_folder_by_id(session, folder_id)
            if not folder:
                return _html_page("<h3>Not found</h3><p>Folder not found.</p>")
            if not settings.admin_ids and folder.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            decks = await list_decks_in_folder(session, folder_id)
            if settings.admin_ids:
                folders = await list_all_folders(session)
            else:
                folders = await list_admin_folders(session, admin_id)

        deck_items = "".join(
            f'<li><a href="/admin/decks/{deck.id}?token={token}">{_escape(deck.title)}</a></li>'
            for deck in decks
        )
        deck_html = f"<ul>{deck_items}</ul>" if deck_items else "<p>No decks in this folder.</p>"
        reassign_options = [
            '<option value="">Ungrouped</option>',
            *[
                f'<option value="{f.id}">{_escape(_folder_label(f))}</option>'
                for f in folders
                if f.id != folder.id
            ],
        ]
        reassign_select = f"<select name=\"new_folder_id\">{''.join(reassign_options)}</select>"
        body = f"""
        {_admin_nav(token)}
        <h2>Folder: {_escape(_folder_label(folder))}</h2>
        {deck_html}
        <h3>Rename folder</h3>
        <form method="post" action="/admin/folders/{folder.id}/rename">
          <input type="hidden" name="token" value="{token}"/>
          <input type="text" name="path" value="{_escape(folder.path)}" required/>
          <button type="submit">Rename</button>
        </form>
        <h3>Delete folder</h3>
        <form method="post" action="/admin/folders/{folder.id}/delete">
          <input type="hidden" name="token" value="{token}"/>
          <label><input type="radio" name="mode" value="prevent" checked/> Prevent delete if not empty</label><br/>
          <label><input type="radio" name="mode" value="reassign"/> Reassign decks to:</label>
          {reassign_select}
          <button type="submit">Delete folder</button>
        </form>
        """
        return _html_page(body)

    @app.post("/admin/folders/{folder_id}/rename", response_class=HTMLResponse)
    async def admin_folder_rename(folder_id: str, token: str = Form(...), path: str = Form(...)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            folder = await get_folder_by_id(session, folder_id)
            if not folder:
                return _html_page("<h3>Not found</h3><p>Folder not found.</p>")
            if not settings.admin_ids and folder.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            try:
                updated = await update_folder_path(session, folder_id, path)
            except ValueError as exc:
                return _html_page(
                    f"{_admin_nav(token)}<h3>Update failed</h3><p>{_escape(str(exc))}</p>"
                )
            if not updated:
                return _html_page("<h3>Not found</h3><p>Folder not found.</p>")

        body = f"""
        {_admin_nav(token)}
        <h3>Folder renamed</h3>
        <p><a href="/admin/folders/{folder_id}?token={token}">Back to folder</a></p>
        """
        return _html_page(body)

    @app.post("/admin/folders/{folder_id}/delete", response_class=HTMLResponse)
    async def admin_folder_delete(
        folder_id: str,
        token: str = Form(...),
        mode: str = Form("prevent"),
        new_folder_id: str | None = Form(None),
    ):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            folder = await get_folder_by_id(session, folder_id)
            if not folder:
                return _html_page("<h3>Not found</h3><p>Folder not found.</p>")
            if not settings.admin_ids and folder.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")

            if mode == "reassign":
                target_id = new_folder_id or None
                if target_id:
                    target_folder = await get_folder_by_id(session, target_id)
                    if not target_folder:
                        return _html_page("<h3>Not found</h3><p>Target folder not found.</p>")
                    if not settings.admin_ids and target_folder.admin_tg_id != admin_id:
                        return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
                await reassign_decks_from_folder(session, folder_id, target_id)
                await delete_folder(session, folder_id)
            else:
                deleted = await delete_folder_if_empty(session, folder_id)
                if not deleted:
                    deck_count = await count_decks_in_folder(session, folder_id)
                    return _html_page(
                        f"{_admin_nav(token)}<h3>Delete blocked</h3>"
                        f"<p>Folder still contains {deck_count} deck(s).</p>"
                    )

        body = f"""
        {_admin_nav(token)}
        <h3>Folder deleted</h3>
        <p><a href="/admin?token={token}">Back to admin home</a></p>
        """
        return _html_page(body)

    @app.get("/admin/decks/{deck_id}", response_class=HTMLResponse)
    async def admin_deck(deck_id: str, token: str = Query(None)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            deck = await get_deck_by_id(session, deck_id)
            if not deck:
                return _html_page("<h3>Not found</h3><p>Deck not found.</p>")
            if not settings.admin_ids and deck.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            if settings.admin_ids:
                folders = await list_all_folders(session)
            else:
                folders = await list_admin_folders(session, admin_id)

        folder_options = [
            '<option value="">Ungrouped</option>',
            *[
                f'<option value="{folder.id}" {"selected" if deck.folder_id == folder.id else ""}>'
                f"{_escape(_folder_label(folder))}</option>"
                for folder in folders
            ],
        ]
        folder_select = f"<select name=\"folder_id\">{''.join(folder_options)}</select>"
        body = f"""
        {_admin_nav(token)}
        <h2>{_escape(deck.title)}</h2>
        <ul>
          <li>Active: {bool(deck.is_active)}</li>
          <li>New per day: {deck.new_per_day}</li>
          <li>Owner: {deck.admin_tg_id}</li>
        </ul>
        <h3>Rename deck</h3>
        <form method="post" action="/admin/decks/{deck.id}/rename">
          <input type="hidden" name="token" value="{token}"/>
          <input type="text" name="title" value="{_escape(deck.title)}" required/>
          <button type="submit">Rename</button>
        </form>
        <h3>Move deck</h3>
        <form method="post" action="/admin/decks/{deck.id}/move">
          <input type="hidden" name="token" value="{token}"/>
          {folder_select}
          <button type="submit">Move</button>
        </form>
        <p><a href="/admin/decks/{deck.id}/stats?token={token}">Deck stats</a></p>
        <p><a href="/admin/decks/{deck.id}/students?token={token}">Enrolled users</a></p>
        """
        return _html_page(body)

    @app.post("/admin/decks/{deck_id}/rename", response_class=HTMLResponse)
    async def admin_deck_rename(deck_id: str, token: str = Form(...), title: str = Form(...)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            deck = await get_deck_by_id(session, deck_id)
            if not deck:
                return _html_page("<h3>Not found</h3><p>Deck not found.</p>")
            if not settings.admin_ids and deck.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            await update_deck_title(session, deck_id, title)

        body = f"""
        {_admin_nav(token)}
        <h3>Deck renamed</h3>
        <p><a href="/admin/decks/{deck_id}?token={token}">Back to deck</a></p>
        """
        return _html_page(body)

    @app.post("/admin/decks/{deck_id}/move", response_class=HTMLResponse)
    async def admin_deck_move(deck_id: str, token: str = Form(...), folder_id: str | None = Form(None)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            deck = await get_deck_by_id(session, deck_id)
            if not deck:
                return _html_page("<h3>Not found</h3><p>Deck not found.</p>")
            if not settings.admin_ids and deck.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            target_id = folder_id or None
            if target_id:
                folder = await get_folder_by_id(session, target_id)
                if not folder:
                    return _html_page("<h3>Not found</h3><p>Folder not found.</p>")
                if not settings.admin_ids and folder.admin_tg_id != admin_id:
                    return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            await update_deck_folder(session, deck_id, target_id)

        body = f"""
        {_admin_nav(token)}
        <h3>Deck moved</h3>
        <p><a href="/admin/decks/{deck_id}?token={token}">Back to deck</a></p>
        """
        return _html_page(body)

    @app.get("/admin/decks/{deck_id}/stats", response_class=HTMLResponse)
    async def admin_deck_stats(deck_id: str, token: str = Query(None)):
        admin_id, error = _admin_required(token)
        if error:
            return error

        async with sessionmaker() as session:
            deck = await get_deck_by_id(session, deck_id)
            if not deck:
                return _html_page("<h3>Not found</h3><p>Deck not found.</p>")
            if not settings.admin_ids and deck.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            stats_text = await admin_stats(session, deck_id)

        stats_lines = "".join(f"<li>{_escape(line)}</li>" for line in stats_text.splitlines() if line.strip())
        stats_html = f"<ul>{stats_lines}</ul>" if stats_lines else "<p>No stats available.</p>"
        body = f"""
        {_admin_nav(token)}
        <h2>Stats: {_escape(deck.title)}</h2>
        {stats_html}
        <p><a href="/admin/decks/{deck.id}?token={token}">Back to deck</a></p>
        """
        return _html_page(body)

    @app.get("/admin/decks/{deck_id}/students", response_class=HTMLResponse)
    async def admin_deck_students(
        deck_id: str,
        token: str = Query(None),
        offset: int = 0,
        limit: int = 50,
        study_date: str | None = None,
        tg_id: int | None = None,
    ):
        admin_id, error = _admin_required(token)
        if error:
            return error
        selected_date = date.today()
        if study_date:
            try:
                selected_date = date.fromisoformat(study_date)
            except ValueError:
                selected_date = date.today()

        async with sessionmaker() as session:
            deck = await get_deck_by_id(session, deck_id)
            if not deck:
                return _html_page("<h3>Not found</h3><p>Deck not found.</p>")
            if not settings.admin_ids and deck.admin_tg_id != admin_id:
                return _html_page("<h3>Unauthorized</h3><p>Not allowed.</p>")
            total = await count_enrolled_students(session, deck_id, tg_id=tg_id)
            students = await list_enrolled_students(session, deck_id, offset=offset, limit=limit, tg_id=tg_id)
            counts = await get_deck_user_study_counts(
                session,
                deck_id=deck_id,
                study_date=selected_date,
                user_ids=[student.id for student in students],
            )

            student_rows = []
            for student in students:
                progress = await compute_overall_progress(session, student.id, deck_id)
                states = ", ".join(f"{k}:{v}" for k, v in sorted(progress["states"].items()))
                counts_row = counts.get(student.id, {"daily_done": 0, "total_done": 0})
                student_rows.append(
                    "<tr>"
                    f"<td>{student.tg_id}</td>"
                    f"<td>{counts_row['daily_done']}</td>"
                    f"<td>{counts_row['total_done']}</td>"
                    f"<td>{progress['started']}/{progress['total_cards']}</td>"
                    f"<td>{progress['due']}</td>"
                    f"<td>{_escape(states) or 'n/a'}</td>"
                    "</tr>"
                )

        if student_rows:
            table = (
                "<table>"
                "<thead><tr>"
                "<th>User TG ID</th>"
                f"<th>Daily ({selected_date.isoformat()})</th>"
                "<th>Total studied</th>"
                "<th>Started</th><th>Due</th><th>States</th>"
                "</tr></thead>"
                f"<tbody>{''.join(student_rows)}</tbody></table>"
            )
        else:
            table = "<p>No enrolled users.</p>"

        nav = []
        if offset > 0:
            prev_offset = max(offset - limit, 0)
            nav.append(
                f'<a href="/admin/decks/{deck.id}/students?token={token}&offset={prev_offset}&limit={limit}'
                f'&study_date={selected_date.isoformat()}{f"&tg_id={tg_id}" if tg_id else ""}">Prev</a>'
            )
        if offset + limit < total:
            next_offset = offset + limit
            nav.append(
                f'<a href="/admin/decks/{deck.id}/students?token={token}&offset={next_offset}&limit={limit}'
                f'&study_date={selected_date.isoformat()}{f"&tg_id={tg_id}" if tg_id else ""}">Next</a>'
            )
        nav_html = " | ".join(nav)
        tg_id_value = "" if tg_id is None else tg_id
        body = f"""
        {_admin_nav(token)}
        <h2>Enrolled users: {_escape(deck.title)}</h2>
        <p>Total enrolled: {total}</p>
        <form method="get" action="/admin/decks/{deck.id}/students">
          <input type="hidden" name="token" value="{token}"/>
          <label>Study date (YYYY-MM-DD)</label>
          <input type="text" name="study_date" value="{selected_date.isoformat()}"/>
          <label>Filter by TG ID</label>
          <input type="number" name="tg_id" value="{tg_id_value}" min="1"/>
          <button type="submit">Apply</button>
        </form>
        {table}
        <p>{nav_html}</p>
        <p><a href="/admin/decks/{deck.id}?token={token}">Back to deck</a></p>
        """
        return _html_page(body)

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
                async with import_sem:
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
