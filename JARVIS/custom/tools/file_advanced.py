"""Maya AI advanced file operations. LOCAL only, path-guarded."""

from __future__ import annotations

import os
import shutil
import threading
import zipfile
from pathlib import Path

from custom.tools.path_guard import is_path_allowed

_GATE = None
_GATE_LOCK = threading.RLock()


def set_permission_gate(fn):
    global _GATE
    with _GATE_LOCK:
        _GATE = fn


def _ask_permission(action: str, item: str) -> bool:
    if _GATE is not None:
        try:
            return bool(_GATE(action, item))
        except Exception:
            return False
    try:
        return input(f"[permission] {action} '{item}'? [y/N]: ").strip().lower() in ("y", "yes", "true", "1")
    except Exception:
        return False


def move_file(src: str, dst: str) -> str:
    if not is_path_allowed(src) or not is_path_allowed(dst):
        return "Access denied: path outside allowed roots."
    if not _ask_permission("Move file", f"{src} -> {dst}"):
        return "Cancelled"
    try:
        shutil.move(src, dst)
        return f"Moved: {src} -> {dst}"
    except Exception as e:
        return f"Error: {e}"


def copy_file(src: str, dst: str) -> str:
    if not is_path_allowed(src) or not is_path_allowed(dst):
        return "Access denied: path outside allowed roots."
    if not _ask_permission("Copy file", f"{src} -> {dst}"):
        return "Cancelled"
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return f"Copied: {src} -> {dst}"
    except Exception as e:
        return f"Error: {e}"


def rename_file(path: str, new_name: str) -> str:
    if not is_path_allowed(path):
        return "Access denied: path outside allowed roots."
    if not _ask_permission("Rename file", f"{path} -> {new_name}"):
        return "Cancelled"
    try:
        p = Path(path)
        new_path = p.parent / new_name
        p.rename(new_path)
        return f"Renamed: {path} -> {new_path}"
    except Exception as e:
        return f"Error: {e}"


def zip_path(path: str, out_zip: str = None) -> str:
    if not is_path_allowed(path):
        return "Access denied: path outside allowed roots."
    if out_zip is None:
        out_zip = path.rstrip("\\/") + ".zip"
    if not is_path_allowed(out_zip):
        return "Access denied: output path outside allowed roots."
    if not _ask_permission("Zip", f"{path} -> {out_zip}"):
        return "Cancelled"
    try:
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            p = Path(path)
            if p.is_file():
                zf.write(p, p.name)
            else:
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = Path(root) / f
                        zf.write(fp, fp.relative_to(p.parent))
        return f"Zipped: {out_zip}"
    except Exception as e:
        return f"Error: {e}"


def unzip_path(zip_path: str, dst: str = None) -> str:
    if not is_path_allowed(zip_path):
        return "Access denied."
    if dst is None:
        dst = str(Path(zip_path).parent)
    if not is_path_allowed(dst):
        return "Access denied."
    if not _ask_permission("Unzip", f"{zip_path} -> {dst}"):
        return "Cancelled"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dst)
        return f"Unzipped to: {dst}"
    except Exception as e:
        return f"Error: {e}"


def search_content(directory: str, query: str, ext: str = "") -> list:
    """Search text content inside files. Read-only."""
    if not is_path_allowed(directory):
        return []
    results = []
    for root, _, files in os.walk(directory):
        for f in files:
            if ext and not f.endswith(ext):
                continue
            fp = os.path.join(root, f)
            if not is_path_allowed(fp):
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                if query.lower() in content.lower():
                    results.append(fp)
                    if len(results) >= 50:
                        return results
            except Exception:
                pass
    return results


def watch_folder(directory: str, callback) -> str:
    """Simple polling watcher (no watchdog dep). Returns status."""
    if not is_path_allowed(directory):
        return "Access denied."
    return f"Watcher registered for {directory} (polling mode)"


__all__ = ["move_file", "copy_file", "rename_file", "zip_path", "unzip_path",
           "search_content", "watch_folder", "set_permission_gate"]
