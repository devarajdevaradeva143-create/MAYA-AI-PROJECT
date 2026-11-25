"""Maya AI Personal Knowledge Tools.

Provides local file search, PDF reading, and document analysis.
All operations are LOCAL only — nothing goes to the cloud.

Per AGENTS.md: Personal knowledge base laptop-la mattum, cloud-kku poagadhu.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


# ── File search ────────────────────────────────────────────────────────────

def search_files(query: str, root_path: str = ".") -> List[Dict[str, Any]]:
    """Search local files by name/query.

    Uses os.walk to find files matching the query.
    Returns list of matches with path, name, and match info.
    """
    matches = []
    query_lower = query.lower()

    try:
        for dirpath, _dirnames, filenames in os.walk(root_path):
            for filename in filenames:
                # Match by filename containing query
                if query_lower in filename.lower():
                    full_path = os.path.join(dirpath, filename)
                    rel_path = os.path.relpath(full_path, root_path)
                    matches.append({
                        "path": full_path,
                        "relative": rel_path,
                        "name": filename,
                        "match_type": "filename",
                    })
                # Also match by content in text files
                elif query_lower in _read_text_snippet(filename):
                    full_path = os.path.join(dirpath, filename)
                    rel_path = os.path.relpath(full_path, root_path)
                    matches.append({
                        "path": full_path,
                        "relative": rel_path,
                        "name": filename,
                        "match_type": "content",
                    })
    except Exception as e:
        return [{"error": f"search failed: {e}"}]

    # Deduplicate by path
    seen = set()
    deduped = []
    for m in matches:
        if m["path"] not in seen:
            seen.add(m["path"])
            deduped.append(m)
    return deduped


def _read_text_snippet(filename: str, max_chars: int = 500) -> str:
    """Read a snippet of a text file to check for query match.

    Reads the file from disk (relative to cwd or as an absolute path)
    and returns up to ``max_chars`` characters of its content.
    Only common text extensions are checked.
    """
    ext = Path(filename).suffix.lower()
    if ext not in (".txt", ".md", ".py", ".json", ".csv", ".html", ".css", ".js"):
        return ""
    try:
        content = read_text_file(filename)
        if content.startswith("[") and ("not found" in content or "Error" in content):
            return ""
        return content[:max_chars]
    except Exception:
        return ""


# ── PDF reading ────────────────────────────────────────────────────────────

def read_pdf(path: str) -> str:
    """Read PDF text and return content.

    Try pypyr first, then fall back.
    """
    if not HAS_PYPDF:
        return "[PDF reading not available — install pypdf: uv pip install pypdf]\n"

    try:
        reader = pypdf.PdfReader(path)
        text_parts = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            except Exception:
                continue
        if text_parts:
            return "\n".join(text_parts)
        return "[PDF had no extractable text]"
    except FileNotFoundError:
        return f"[PDF not found: {path}]"
    except Exception as e:
        return f"[Error reading PDF: {e}]"


# ── Text file reading ─────────────────────────────────────────────────────

def read_text_file(path: str) -> str:
    """Read a text file and return content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"[File not found: {path}]"
    except Exception as e:
        return f"[Error reading file: {e}]"


# ── Document indexing ─────────────────────────────────────────────────────

def index_documents(folder: str) -> Dict[str, Any]:
    """Scan a folder for .pdf, .txt, .md files and return index.

    Returns dict with file paths and their types.
    """
    index = {
        "pdf": [],
        "txt": [],
        "md": [],
        "other": [],
        "total": 0,
        # Absolute folder the relative paths belong to. Without this,
        # knowledge_search() cannot reopen the files from another cwd.
        "base": str(Path(folder).expanduser().resolve()),
    }

    try:
        folder_path = Path(folder)
        if not folder_path.exists():
            return {"error": f"Folder not found: {folder}"}

        for file_path in folder_path.rglob("*"):
            if not file_path.is_file():
                continue

            ext = file_path.suffix.lower()
            try:
                rel = file_path.relative_to(folder_path)
            except Exception:
                rel = file_path.name

            if ext == ".pdf":
                index["pdf"].append(str(rel))
                index["total"] += 1
            elif ext == ".txt":
                index["txt"].append(str(rel))
                index["total"] += 1
            elif ext == ".md":
                index["md"].append(str(rel))
                index["total"] += 1
            else:
                index["other"].append(str(rel))
    except Exception as e:
        return {"error": f"indexing failed: {e}"}

    return index


# ── Index persistence ────────────────────────────────────────────────────────

ENV_KNOWLEDGE_INDEX = "MAYA_KNOWLEDGE_INDEX"
DEFAULT_OFFLINE_MEMORY = "memory/offline"
KNOWLEDGE_INDEX_FILENAME = "knowledge_index.json"


def _knowledge_index_path() -> Path:
    """Resolve the knowledge index JSON path from settings.yaml (offline only)."""
    override = os.environ.get(ENV_KNOWLEDGE_INDEX, "").strip()
    if override:
        return Path(override).expanduser()

    from ..config import PROJECT_ROOT, load_settings

    settings = load_settings()
    memory = settings.get("memory", {}) if isinstance(settings, dict) else {}
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY)
    dir_path = Path(offline)
    if not dir_path.is_absolute():
        dir_path = PROJECT_ROOT / "MAYA AI" / dir_path
    return dir_path / KNOWLEDGE_INDEX_FILENAME


def save_index(index: Dict[str, Any], path: Optional[Path] = None) -> bool:
    """Persist a document index to a JSON file (offline memory only).

    Args:
        index: The index dict returned by :func:`index_documents`.
        path: Optional custom path. Defaults to
            ``MAYA AI/memory/offline/knowledge_index.json``.

    Returns:
        True if the write succeeded.
    """
    target = path if path is not None else _knowledge_index_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, target)
        return True
    except (OSError, ValueError, TypeError):
        return False


def load_index(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load a previously persisted document index.

    Args:
        path: Optional custom path. Defaults to
            ``MAYA AI/memory/offline/knowledge_index.json``.

    Returns:
        The index dict, or None if the file doesn't exist or is corrupt.
    """
    target = path if path is not None else _knowledge_index_path()
    try:
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None


# ── Knowledge search across indexed docs ───────────────────────────────────

def knowledge_search(query: str, index: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search within an already-indexed document set.

    Looks for query text in PDF and text file contents.
    """
    results = []

    # Search in listed PDFs
    for pdf_path in index.get("pdf", []):
        full_path = os.path.join(index.get("base", ""), pdf_path) if index.get("base") else pdf_path
        content = read_pdf(full_path)
        if "[Error" not in content and "[PDF not found" not in content:
            if query.lower() in content.lower():
                results.append({
                    "file": pdf_path,
                    "match_type": "pdf_content",
                    "preview": content[:200] + ("..." if len(content) > 200 else ""),
                })

    # Search in listed txt/md files
    for txt_path in index.get("txt", []) + index.get("md", []):
        full_path = os.path.join(index.get("base", ""), txt_path) if index.get("base") else txt_path
        content = read_text_file(full_path)
        if "[Error" not in content and "[File not found" not in content:
            if query.lower() in content.lower():
                results.append({
                    "file": txt_path,
                    "match_type": "text_content",
                    "preview": content[:200] + ("..." if len(content) > 200 else ""),
                })

    return results