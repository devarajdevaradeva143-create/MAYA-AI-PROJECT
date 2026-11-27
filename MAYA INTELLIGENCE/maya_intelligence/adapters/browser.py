"""Browser control adapter for MAYA INTELLIGENCE."""

from typing import Any


class MayaIntelError(Exception):
    pass


class BrowserAdapter:
    def __init__(self):
        from custom.tools import browser_control
        self._bc = browser_control

    def open_url(self, url: str) -> dict[str, Any]:
        res = self._bc.open_url(url)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def search_web(self, query: str) -> dict[str, Any]:
        res = self._bc.search_web(query)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def fetch_page(self, url: str) -> dict[str, Any]:
        content = self._bc.fetch_page(url)
        ok = not content.startswith(("httpx not available", "Fetch error"))
        return {"success": ok, "content": content, "verified": ok}

    def browser_click(self, selector: str) -> dict[str, Any]:
        res = self._bc.browser_click(selector)
        return {"success": False, "result": res, "verified": False}

    def browser_fill(self, selector: str, text: str) -> dict[str, Any]:
        res = self._bc.browser_fill(selector, text)
        return {"success": False, "result": res, "verified": False}
PYEOF