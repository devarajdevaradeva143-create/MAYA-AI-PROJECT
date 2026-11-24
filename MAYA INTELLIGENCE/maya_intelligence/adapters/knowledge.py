"""Knowledge/RAG adapter — wraps custom.tools.knowledge and custom.tools.rag."""

from typing import Any


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE adapters."""


class KnowledgeAdapter:
    """Thin wrapper over custom.tools.knowledge and custom.tools.rag."""

    def __init__(self):
        from custom.tools import knowledge
        from custom.tools import rag

        self._knowledge = knowledge
        self._rag = rag

    def search_files(self, query: str, root: str = None) -> list[dict[str, Any]]:
        """Search files by query."""
        return self._knowledge.search_files(query, root)

    def read_pdf(self, path: str) -> str:
        """Read a PDF file."""
        return self._knowledge.read_pdf(path)

    def read_text_file(self, path: str) -> str:
        """Read a text file."""
        return self._knowledge.read_text_file(path)

    def index_documents(self, paths: list[str]) -> dict[str, Any]:
        """Index documents for RAG."""
        self._knowledge.index_documents(paths)
        return {"success": True}

    def save_index(self, path: str) -> dict[str, Any]:
        """Save RAG index."""
        self._knowledge.save_index(path)
        return {"success": True}

    def load_index(self, path: str) -> dict[str, Any]:
        """Load RAG index."""
        self._knowledge.load_index(path)
        return {"success": True}

    def knowledge_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search knowledge base."""
        return self._knowledge.knowledge_search(query, top_k)

    def rag_build(self, documents: list[str]) -> Any:
        """Build a RagIndex from documents."""
        index = self._rag.RagIndex()
        index.build(documents)
        return index

    def rag_search(self, index: Any, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search a RagIndex."""
        return index.search(query, top_k)

    def rag_answer_prompt(self, index: Any, query: str) -> str:
        """Get answer prompt from RagIndex."""
        return index.answer_prompt(query)

    def rag_save(self, index: Any, path: str) -> dict[str, Any]:
        """Save RagIndex."""
        index.save(path)
        return {"success": True}

    def rag_load(self, path: str) -> Any:
        """Load RagIndex."""
        index = self._rag.RagIndex()
        index.load(path)
        return index