"""Cognitive Intelligence (IQ) engine — answers and plans via engine + RAG."""

import json
import re
from dataclasses import dataclass

#: Intents the agent is allowed to execute autonomously.
AGENT_ALLOWED_INTENTS = {
    "open_app", "close_app", "search_files", "read_file", "create_folder",
    "delete_file", "edit_file", "run_command", "todo", "reminder", "schedule",
    "monitor", "knowledge", "screenshot", "screen_size", "mouse_move",
    "mouse_click", "mouse_scroll", "keyboard_type", "press_key", "get_volume",
    "set_volume", "mute_toggle", "get_brightness", "set_brightness",
    "lock_screen", "sleep_pc", "shutdown_pc", "restart_pc", "cancel_shutdown",
    "read_clipboard", "write_clipboard", "list_windows", "focus_window",
    "minimize_all", "close_window", "list_processes", "kill_process",
    "set_priority", "open_url", "search_web", "fetch_page", "move_file",
    "copy_file", "rename_file", "zip_path", "unzip_path", "search_content",
    "excel_write", "excel_read", "word_create_doc", "word_add_text",
}


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

    def plan_actions(self, goal: str, context: str = "", language_directive: str = "") -> list[dict]:
        """Plan a multi-step task as executable actions (JSON)."""
        allowed = ", ".join(sorted(AGENT_ALLOWED_INTENTS))
        system_parts = [
            self._persona,
            "You are an action planner for a PC-control assistant.",
            "Break the user's goal into concrete, executable steps.",
            "Each step must be one of these intents: " + allowed + ".",
            "Respond with ONLY a JSON array. No markdown, no prose, no code fences.",
            'Each element: {"intent": "<intent>", "params": {<params>}, "description": "<short>"}',
            "Maximum 8 steps.",
        ]
        if language_directive:
            system_parts.append(f"[Response language] {language_directive}")
        if context:
            system_parts.append(f"[Context]\n{context}")
        system_prompt = "\n\n".join(system_parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": goal},
        ]
        result = self._engine.chat(messages)
        text = (result.text or "").strip()

        parsed = None
        candidates = [text]
        m = re.search(r"\[.*\]", text, re.S)
        if m:
            candidates.append(m.group(0))
        for cand in candidates:
            try:
                parsed = json.loads(cand)
                break
            except (json.JSONDecodeError, ValueError):
                continue
        if not isinstance(parsed, list):
            return []

        actions = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            intent = str(item.get("intent", "")).strip().lower()
            if intent not in AGENT_ALLOWED_INTENTS:
                continue
            params = item.get("params", {})
            if not isinstance(params, dict):
                params = {}
            desc = str(item.get("description", "")).strip()
            actions.append({"intent": intent, "params": params, "description": desc})
        return actions[:8]

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
