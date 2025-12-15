from __future__ import annotations
import os, zipfile, shutil
from pathlib import Path

def unpack_apkg(apkg_path: str, tmp_dir: str, job_id: str) -> Path:
    base = Path(tmp_dir) / job_id
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apkg_path, "r") as z:
        z.extractall(base)
    return base
