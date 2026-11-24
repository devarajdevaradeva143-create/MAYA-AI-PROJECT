"""Desktop app services (adapters between the UI, existing `custom` code and
the headless phone server).

Nothing in this package imports PySide6 at module level: the server must run
headless. UI-only imports stay inside Phase 1+ page modules.
"""
