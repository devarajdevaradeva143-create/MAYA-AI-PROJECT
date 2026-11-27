"""Advanced file ops adapter for MAYA INTELLIGENCE."""

from typing import Any


class MayaIntelError(Exception):
    pass


class FilesAdapter:
    def __init__(self):
        from custom.tools import file_advanced
        self._fa = file_advanced

    def move_file(self, src: str, dst: str) -> dict[str, Any]:
        res = self._fa.move_file(src, dst)
        ok = str(res).startswith("Moved:")
        return {"success": ok, "result": res, "verified": ok}

    def copy_file(self, src: str, dst: str) -> dict[str, Any]:
        res = self._fa.copy_file(src, dst)
        ok = str(res).startswith("Copied:")
        return {"success": ok, "result": res, "verified": ok}

    def rename_file(self, path: str, new_name: str) -> dict[str, Any]:
        res = self._fa.rename_file(path, new_name)
        ok = str(res).startswith("Renamed:")
        return {"success": ok, "result": res, "verified": ok}

    def zip_path(self, path: str, out_zip: str = None) -> dict[str, Any]:
        res = self._fa.zip_path(path, out_zip)
        ok = str(res).startswith("Zipped:")
        return {"success": ok, "result": res, "verified": ok}

    def unzip_path(self, zip_path: str, dst: str = None) -> dict[str, Any]:
        res = self._fa.unzip_path(zip_path, dst)
        ok = str(res).startswith("Unzipped")
        return {"success": ok, "result": res, "verified": ok}

    def search_content(self, directory: str, query: str, ext: str = "") -> list:
        return self._fa.search_content(directory, query, ext)
PYEOF