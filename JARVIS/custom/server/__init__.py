"""Maya phone server (Windows, headless).

`custom.server` must never import PySide6. See docs/API-CONTRACT.md.
"""

from custom.server.app import create_app
from custom.server.contracts import ServerServices, ServerSettings

__all__ = ["create_app", "ServerServices", "ServerSettings"]
