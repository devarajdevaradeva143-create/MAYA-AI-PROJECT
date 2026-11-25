"""`python -m app` entry point (`--headless` / `--tray`)."""

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
