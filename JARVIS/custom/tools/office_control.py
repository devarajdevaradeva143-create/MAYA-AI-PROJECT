"""Maya AI Office (Excel/Word) control via PowerShell COM. LOCAL only."""

from __future__ import annotations

import subprocess
import threading
from typing import Callable, Optional

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


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=30)
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:
        return str(e)


def excel_write(path: str, cell: str, value: str) -> str:
    if not _ask_permission("Excel write", f"{path}!{cell} = {value}"):
        return "Cancelled"
    cmd = (
        "$e=New-Object -ComObject Excel.Application; $e.Visible=$false; "
        "$wb=$e.Workbooks.Open('%s'); $ws=$wb.Sheets(1); "
        "$ws.Range('%s').Value2='%s'; $wb.Save(); $wb.Close(); $e.Quit()" % (
            path.replace("\\", "\\\\"), cell, str(value).replace("'", "''"))
    )
    return _ps(cmd)


def excel_read(path: str, cell_range: str) -> str:
    cmd = (
        "$e=New-Object -ComObject Excel.Application; $e.Visible=$false; "
        "$wb=$e.Workbooks.Open('%s'); $ws=$wb.Sheets(1); "
        "$v=$ws.Range('%s').Value2; $wb.Close($false); $e.Quit(); $v" % (
            path.replace("\\", "\\\\"), cell_range)
    )
    return _ps(cmd)


def word_create_doc(path: str, text: str = "") -> str:
    if not _ask_permission("Create Word doc", path):
        return "Cancelled"
    cmd = (
        "$w=New-Object -ComObject Word.Application; $w.Visible=$false; "
        "$d=$w.Documents.Add(); "
        "$d.Content.Text='%s'; $d.SaveAs('%s'); $d.Close(); $w.Quit()" % (
            text.replace("'", "''"), path.replace("\\", "\\\\"))
    )
    return _ps(cmd)


def word_add_text(path: str, text: str) -> str:
    if not _ask_permission("Add text to Word doc", path):
        return "Cancelled"
    cmd = (
        "$w=New-Object -ComObject Word.Application; $w.Visible=$false; "
        "$d=$w.Documents.Open('%s'); $d.Content.InsertAfter('%s'); $d.Save(); $d.Close(); $w.Quit()" % (
            path.replace("\\", "\\\\"), text.replace("'", "''"))
    )
    return _ps(cmd)


__all__ = ["excel_write", "excel_read", "word_create_doc", "word_add_text", "set_permission_gate"]
PYEOF