"""Maya AI browser control tools. LOCAL only.

Basic browser control without heavy deps:
- open URL / search in default browser
- fetch page content (httpx)
- click/fill automation requires playwright (optional)
"""

from __future__ import annotations

import subprocess
import threading
import webbrowser
from typing import Callable, Optional

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import playwright  # noqa
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

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


def open_url(url: str) -> str:
    if not _ask_permission("Open URL", url):
        return "Cancelled"
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return f"Opened: {url}"
    except Exception as e:
        return f"Error: {e}"


def search_web(query: str) -> str:
    if not _ask_permission("Web search", query):
        return "Cancelled"
    try:
        import urllib.parse
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        webbrowser.open(url)
        return f"Searching: {query}"
    except Exception as e:
        return f"Error: {e}"


def fetch_page(url: str) -> str:
    """Fetch page content (text). Read-only, no permission needed."""
    if not HAS_HTTPX:
        return "httpx not available"
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        r = httpx.get(url, timeout=15, follow_redirects=True)
        text = r.text
        # strip tags roughly
        import re
        text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:3000]
    except Exception as e:
        return f"Fetch error: {e}"


def browser_click(selector: str) -> str:
    if not HAS_PLAYWRIGHT:
        return "Playwright not installed (pip install playwright)"
    return "Playwright automation not wired yet"


def browser_fill(selector: str, text: str) -> str:
    if not HAS_PLAYWRIGHT:
        return "Playwright not installed (pip install playwright)"
    return "Playwright automation not wired yet"


def browser_screenshot(url: str, path: str = None) -> str:
    if not HAS_PLAYWRIGHT:
        return "Playwright not installed (pip install playwright)"
    return "Playwright automation not wired yet"


__all__ = ["open_url", "search_web", "fetch_page", "browser_click", "browser_fill",
           "browser_screenshot", "set_permission_gate", "HAS_PLAYWRIGHT", "HAS_HTTPX"]
PYEOF