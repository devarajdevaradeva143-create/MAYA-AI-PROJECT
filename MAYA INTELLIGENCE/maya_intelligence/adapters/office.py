"""Office control adapter for MAYA INTELLIGENCE."""

from typing import Any


class MayaIntelError(Exception):
    pass


class OfficeAdapter:
    def __init__(self):
        from custom.tools import office_control
        self._oc = office_control

    def excel_write(self, path: str, cell: str, value: str) -> dict[str, Any]:
        res = self._oc.excel_write(path, cell, value)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def excel_read(self, path: str, cell_range: str) -> str:
        return self._oc.excel_read(path, cell_range)

    def word_create_doc(self, path: str, text: str = "") -> dict[str, Any]:
        res = self._oc.word_create_doc(path, text)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def word_add_text(self, path: str, text: str) -> dict[str, Any]:
        res = self._oc.word_add_text(path, text)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}
PYEOF