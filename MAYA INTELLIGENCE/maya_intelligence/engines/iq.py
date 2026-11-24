"""Cognitive Intelligence (IQ) engine — answers and plans via engine + RAG."""

from dataclasses import dataclass
from typing import Any


@dataclass
class IQResult:
    text: str
    used_rag: bool = False
    sources: list[str] = None


class IQEngine:
    """Cognitive Intelligence — logical reasoning, problem solving, planning."""

    #: A compact style block that measurably improves small local models.
    ANSWER_RULES = (
        "[Answer rules]\n"
        "- Answer the question first, directly.\n"
        "- Be concise: 1-4 sentences for simple questions.\n"
        "- Use plain text. No LaTeX, no $...$ math.\n"
        "- If you are unsure, say so instead of guessing.\n"
        "- Do not invent memories or facts about the user."
    )

    def __init__(self, engine_adapter, knowledge_adapter, persona_prompt: str):
        self._engine = engine_adapter
        self._knowledge = knowledge_adapter
        self._persona = persona_prompt

    def answer(
        self,
        query: str,
        context: str = "",
        eq_directive: str = "",
        use_rag: bool = False,
        history: list[dict[str, str]] | None = None,
        language_directive: str = "",
    ) -> IQResult:
        """Answer a query using the engine, optionally grounded via RAG."""
        system_parts = [self._persona, self.ANSWER_RULES]
        if language_directive:
            system_parts.append(f"[Response language] {language_directive}")
        if eq_directive:
            system_parts.append(f"[EQ Directive] {eq_directive}")
        if context:
            system_parts.append(f"[Context]\n{context}")
        system_prompt = "\n\n".join(system_parts)

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(self._trim_history(history))
        messages.append({"role": "user", "content": query})

        if use_rag:
            results = self._knowledge.knowledge_search(query, top_k=3)
            if results:
                rag_context = "\n\n".join(
                    f"Source: {r.get('path', 'unknown')}\n{r.get('content', '')[:500]}"
                    for r in results
                )
                messages.insert(1, {"role": "system", "content": f"[Knowledge Context]\n{rag_context}"})
                return IQResult(
                    text=self._engine.chat(messages).text,
                    used_rag=True,
                    sources=[r.get("path", "") for r in results],
                )

        result = self._engine.chat(messages)
        return IQResult(text=result.text, used_rag=False, sources=[])

    def plan(
        self,
        task: str,
        context: str = "",
        language_directive: str = "",
    ) -> list[str]:
        """Break a complex task into steps using the engine."""
        system_parts = [
            self._persona,
            "You are a planner. Break the task into clear, actionable steps.",
            "Return ONLY a numbered list of steps, one per line. No extra text.",
            "Maximum 7 steps. Each step should be one concrete action.",
        ]
        if language_directive:
            system_parts.append(f"[Response language] {language_directive}")
        if context:
            system_parts.append(f"[Context]\n{context}")
        system_prompt = "\n\n".join(system_parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        result = self._engine.chat(messages)
        # Parse numbered list
        lines = result.text.strip().split("\n")
        steps = []
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                # Remove leading number/bullet
                cleaned = line.lstrip("0123456789.-* ").strip()
                if cleaned:
                    steps.append(cleaned)
        return steps if steps else [task]

    @staticmethod
    def _trim_history(history: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
        """Keep the last few turns and bound each message's size."""
        trimmed = []
        for message in history[-limit:]:
            content = str(message.get("content", ""))[:400]
            role = message.get("role", "user")
            if role in ("user", "assistant") and content:
                trimmed.append({"role": role, "content": content})
        return trimmed
