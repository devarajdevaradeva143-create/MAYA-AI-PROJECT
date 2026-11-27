"""Orchestrator — 10-step intelligence pipeline with fast paths.

Pipeline: Perception → Intent → Context → IQ → EQ → Plan → Tool Select →
Execute → Verify → Respond.

The LLM is used for open-ended conversation and explanations. Deterministic
skills (math, clock, identity), memory, and intent routing are handled in code
so a small local model cannot get them wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .adapters import (
    EngineAdapter,
    PCAdapter,
    AssistantAdapter,
    KnowledgeAdapter,
    LanguageAdapter,
    VoiceAdapter,
)
from .engines import IQEngine, EQEngine, AQEngine
from .engines.skills import resolve_skill
from .language import detect_language, language_directive, has_tamil_script
from .memory import MemoryStore
from .config import load_persona, get_db_path


#: Intents that must always go through the action/planning path.
ACTION_INTENTS = {
    "open_app",
    "close_app",
    "search_files",
    "read_file",
    "create_folder",
    "delete_file",
    "edit_file",
    "run_command",
    "todo",
    "reminder",
    "schedule",
    "monitor",
    "knowledge",
    "remember",
    "recall",
    "plan",
}

#: Intents the model can answer directly.
SIMPLE_INTENTS = {"question", "help", "chat", "greeting"}

#: Localised short messages.
_PHRASES = {
    "english": {
        "cancelled": "Okay, cancelled.",
        "ask_open": "Which app should I open?",
        "ask_close": "Which app should I close?",
        "ask_file": "Which file or folder do you mean?",
        "ask_command": "Which command should I run?",
        "failed": "I couldn't complete that: {detail}",
        "engine_down": (
            "My local engine isn't responding right now. Please check that "
            "Lemonade is running, then try again."
        ),
        "nothing_saved": "I couldn't save that — it looks like it may contain a secret.",
        "no_memory": "I don't have anything saved about you yet. Tell me something like “My name is …” and I'll remember it.",
        "not_remembered": "I don't have that saved yet.",
        "plan_header": "Here's a simple plan:",
        "sources": "Sources:",
        "search_none": "No matching files found.",
        "todo_none": "Your to-do list is empty.",
        "reminder_none": "You have no reminders.",
        "tone_sad": " I'm here if you want to talk.",
        "tone_stressed": " Take it one step at a time.",
        "tone_tired": " Take a short break if you can.",
        "tone_angry": " I'm happy to help fix it.",
    },
    "tanglish": {
        "cancelled": "Sari, cancel pannitten.",
        "ask_open": "Endha app open pannanum?",
        "ask_close": "Endha app close pannanum?",
        "ask_file": "Endha file or folder?",
        "ask_command": "Endha command run pannanum?",
        "failed": "Idhu mudiyala: {detail}",
        "engine_down": (
            "Local engine respond aagala. Lemonade running-a irukka check "
            "pannunga, appuram try pannunga."
        ),
        "nothing_saved": "Idha save panna mudiyala — secret irukkum pola.",
        "no_memory": "Ungalai pathi innum edhuvum save aagala. “En peru …” nu sollunga, naan remember pannuven.",
        "not_remembered": "Adhu innum save aagala.",
        "plan_header": "Idhu simple plan:",
        "sources": "Sources:",
        "search_none": "Match aana file edhuvum illa.",
        "todo_none": "Unga to-do list kazhi. 👍",
        "reminder_none": "Reminder edhuvum illa.",
        "tone_sad": " Naan irukken, pesalam.",
        "tone_stressed": " Konjam konjama pannalam.",
        "tone_tired": " Mudinja konjam rest eduthukonga.",
        "tone_angry": " Fix panna help pannuren.",
    },
    "tamil": {
        "cancelled": "சரி, ரத்து செய்துவிட்டேன்.",
        "ask_open": "எந்த app-ஐ திறக்க வேண்டும்?",
        "ask_close": "எந்த app-ஐ மூட வேண்டும்?",
        "ask_file": "எந்த file அல்லது folder?",
        "ask_command": "எந்த command இயக்க வேண்டும்?",
        "failed": "இதைச் செய்ய முடியவில்லை: {detail}",
        "engine_down": (
            "எனது லோக்கல் engine இப்போது பதில் சொல்லவில்லை. Lemonade "
            "இயங்குகிறதா பார்த்து மீண்டும் முயற்சிக்கவும்."
        ),
        "nothing_saved": "அதைச் சேமிக்க முடியவில்லை — secret இருக்கலாம்.",
        "no_memory": "உங்களைப் பற்றி இன்னும் எதுவும் சேமிக்கப்படவில்லை. “என் பெயர் …” என்று சொல்லுங்கள், நினைவில் வைத்துக்கொள்கிறேன்.",
        "not_remembered": "அது இன்னும் சேமிக்கப்படவில்லை.",
        "plan_header": "இதோ ஒரு திட்டம்:",
        "sources": "ஆதாரங்கள்:",
        "search_none": "பொருந்தும் file எதுவும் கிடைக்கவில்லை.",
        "todo_none": "உங்கள் to-do list காலியாக உள்ளது.",
        "reminder_none": "Reminder எதுவும் இல்லை.",
        "tone_sad": " நான் இருக்கிறேன், பேசலாம்.",
        "tone_stressed": " ஒவ்வொரு அடியாகச் செய்யலாம்.",
        "tone_tired": " முடிந்தால் கொஞ்சம் ஓய்வு எடுத்துக்கொள்ளுங்கள்.",
        "tone_angry": " சரிசெய்ய உதவுகிறேன்.",
    },
}


@dataclass
class OrchestratorResult:
    response: str
    intent: str
    action_taken: str
    verified: bool
    memory_updated: bool = False


class Orchestrator:
    """10-step orchestration pipeline."""

    def __init__(
        self,
        confirm_fn: Callable[[str], bool] = None,
        db_path: str = None,
        max_tokens: int = 512,
        temperature: float = 0.6,
        persona: str | None = None,
    ):
        # Adapters
        self._engine = EngineAdapter(max_tokens=max_tokens, temperature=temperature)
        self._pc = PCAdapter()
        self._assistant = AssistantAdapter()
        self._knowledge = KnowledgeAdapter()
        self._language = LanguageAdapter()
        self._voice = VoiceAdapter()
        try:
            from maya_intelligence.adapters.screen import ScreenAdapter
            from maya_intelligence.adapters.system import SystemAdapter
            from maya_intelligence.adapters.browser import BrowserAdapter
            from maya_intelligence.adapters.files import FilesAdapter
            from maya_intelligence.adapters.office import OfficeAdapter
            self._screen = ScreenAdapter()
            self._system = SystemAdapter()
            self._browser = BrowserAdapter()
            self._files = FilesAdapter()
            self._office = OfficeAdapter()
        except Exception:
            self._screen = None
            self._system = None
            self._browser = None
            self._files = None
            self._office = None

        # Wrap confirm_fn for pc_control gate (expects action, item)
        def gate_confirm(action: str, item: str) -> bool:
            if confirm_fn:
                return confirm_fn(f"{action} '{item}'?")
            return True

        # Engines
        self._persona = persona or load_persona()
        self._iq = IQEngine(self._engine, self._knowledge, self._persona)
        self._eq = EQEngine()
        # AQ uses original confirm_fn (single message), pc_control uses gate_confirm (action, item)
        self._aq = AQEngine(self._pc, self._assistant, self._knowledge,
                            monitor_adapter=None,
                            screen_adapter=self._screen,
                            system_adapter=self._system,
                            browser_adapter=self._browser,
                            files_adapter=self._files,
                            office_adapter=self._office,
                            confirm_fn=confirm_fn)

        # Wire permission gates (pc + screen + system + clipboard + window + process)
        try:
            from custom.tools import pc_control
            pc_control.set_permission_gate(gate_confirm)
        except Exception:
            pass
        for modname in ("screen_control", "system_control", "clipboard", "window_control",
                        "process_control", "browser_control", "file_advanced", "office_control"):
            try:
                mod = __import__("custom.tools." + modname, fromlist=[modname])
                if hasattr(mod, "set_permission_gate"):
                    mod.set_permission_gate(gate_confirm)
            except Exception:
                pass

        # Memory
        self._memory = MemoryStore(Path(db_path) if db_path else get_db_path())

        # Conversation history (in-memory)
        self._history: list[dict[str, str]] = []

    # ── Pipeline ─────────────────────────────────────────────────────
    def process(self, user_input: str, use_voice: bool = False) -> OrchestratorResult:
        """Run the full 10-step pipeline."""
        # STEP 1: PERCEPTION — already have text input
        text = user_input.strip()
        if not text:
            return OrchestratorResult("", "empty", "none", False, False)

        # Keep engines pointing at the current adapters (tests may swap them).
        self._sync_engines()

        language = self._detect_language(text)

        # STEP 2: INTENT — deterministic skills first (math, clock, identity)
        skill = resolve_skill(text, language)
        if skill:
            answer, skill_name = skill
            self._record_turn(text, answer)
            facts = self._maybe_save_conversation_memory(text, answer)
            return OrchestratorResult(answer, skill_name, skill_name, True, bool(facts))

        intent = self._classify_intent(text)

        # STEP 3: CONTEXT — personal facts + relevant memories
        context = self._build_context(text, intent)

        # STEP 5: EMOTIONAL ANALYSIS (EQ) — detect tone
        tone_result = self._eq.analyze(text)
        eq_directive = tone_result.directive

        # Memory write path
        if intent == "remember":
            saved, secret_blocked = self._save_explicit_memory(text)
            response = self._ack_memory(saved, language, secret_blocked)
            self._record_turn(text, response)
            return OrchestratorResult(response, intent, "memory_saved", True, bool(saved))

        # Memory read path
        if intent == "recall":
            answer = self._recall_memory(text, language)
            if answer:
                self._record_turn(text, answer)
                return OrchestratorResult(answer, intent, "memory_recall", True, False)

        # Agent mode: multi-step autonomous execution
        if intent == "agent":
            response = self._run_agent(text, language)
            self._record_turn(text, response)
            facts = self._maybe_save_conversation_memory(text, response)
            return OrchestratorResult(response, intent, "agent_run", True, bool(facts))

        # STEP 6: PLANNING
        if intent == "plan":
            steps = self._iq.plan(text, context, language_directive(language))
            response = self._format_plan(steps, language)
            self._record_turn(text, response)
            self._maybe_save_conversation_memory(text, response)
            return OrchestratorResult(response, intent, "planned", True, False)

        # Knowledge (RAG) — answer with local sources, don't just dump chunks
        if intent == "knowledge" and "index" not in text.lower():
            iq_result = self._iq.answer(
                text,
                context=context,
                eq_directive=eq_directive,
                use_rag=True,
                history=self._history,
                language_directive=language_directive(language),
            )
            response = self._clean_response(iq_result.text)
            if not self._engine_ok(response):
                response = _PHRASES[language]["engine_down"]
            elif iq_result.used_rag and iq_result.sources:
                unique = [s for s in dict.fromkeys(iq_result.sources) if s]
                if unique:
                    response += f"\n\n{_PHRASES[language]['sources']} " + ", ".join(unique[:3])
            self._record_turn(text, response)
            return OrchestratorResult(response, intent, "rag_answer", True, False)

        # Fast path: simple conversation
        if self._is_simple_query(text, intent):
            response = self._simple_response(text, context, eq_directive, language)
            self._record_turn(text, response)
            facts = self._maybe_save_conversation_memory(text, response)
            return OrchestratorResult(response, intent, "iq_simple", True, bool(facts))

        # STEP 7-9: TOOL SELECT → EXECUTE → VERIFY
        params = self._extract_params(text, intent)
        aq_result = self._aq.execute(intent, params)

        # STEP 10: RESPONSE
        if aq_result.success:
            response = self._format_action_response(
                intent, aq_result, tone_result.tone, language, params
            )
        else:
            response = self._action_failure_response(intent, aq_result.message, language)

        self._record_turn(text, response)
        facts = self._maybe_save_conversation_memory(text, response)

        return OrchestratorResult(
            response=response,
            intent=intent,
            action_taken=aq_result.message if aq_result.success else "failed",
            verified=aq_result.verified,
            memory_updated=bool(facts),
        )

    # ── Intent classification ────────────────────────────────────────
    def _classify_intent(self, text: str) -> str:
        """Classify user intent using heuristics (English + Tanglish)."""
        t = text.lower().strip()

        # ── Memory first: don't let "what is my name" become a general question
        if self._looks_like_recall(t):
            return "recall"
        if re.search(
            r"\b(remind me|set (?:a )?reminder|reminder|nyabagam paduthu)\b", t
        ):
            return "reminder"
        if re.search(
            r"\b(remember|note that|don'?t forget|keep in mind|nyabagam vai|ninaivul vai)\b",
            t,
        ):
            return "remember"

        # ── Meta questions must not trigger actions ("how do I open X?")
        if re.search(
            r"\b(tell me|explain|teach me|how (?:do|can|should|to)|"
            r"what is the command|what does)\b",
            t,
        ):
            if re.search(r"\b(how (?:do|can|should) i|how to|plan|steps?)\b", t):
                return "plan"
            return "question"
        if re.match(r"^(?:what|why|when|where|who|which|how)\b", t):
            return "question"

        # ── Explicit plan request
        if re.match(r"^(?:plan|make a plan|give me \d+ steps?|steps? to)\b", t):
            return "plan"

        # Agentic: explicit agent keyword or multi-step chain
        if re.search(r"\b(agent|automate|step by step|do this for me|chain)\b", t):
            return "agent"
        if re.search(r"\b(open|create|delete|edit|run|search|read|move|copy|zip|type|press|click|scroll)\b.*\b(and|then|,)\b.*(open|create|delete|edit|run|search|read|move|copy|zip|type|press|click|scroll)\b", t):
            return "agent"

        # ── File operations before app operations ("open file X" is a read)
        if re.search(r"\b(search|find|thedu)\b", t) and re.search(
            r"\b(file|files|folder|folders|document|documents)\b", t
        ):
            return "search_files"
        if re.search(r"\b(file|folder)\b.*\b(search|find|thedu)\b", t):
            return "search_files"
        if re.search(r"\b(read|show|view|display|cat)\b", t) and re.search(
            r"\bfiles?\b", t
        ):
            return "read_file"
        if re.search(r"\bfiles?\b.*\b(open|read|show|view)\b", t):
            return "read_file"
        if re.search(r"\b(create|make|new)\b.*\b(folder|directory)\b", t):
            return "create_folder"
        if re.search(r"\b(folder|directory)\b.*\b(create|make|venum)\b", t):
            return "create_folder"
        if re.search(r"\b(delete|remove|rm)\b.*\b(file|folder)\b", t):
            return "delete_file"
        if re.search(r"\b(file|folder)\b.*\b(delete|remove)\b", t):
            return "delete_file"
        if re.search(r"\b(edit|modify|change|update)\b.*\bfile\b", t):
            return "edit_file"
        if re.search(r"\b(run|execute)\b.*\b(command|cmd|shell|terminal)\b", t):
            return "run_command"

        # ── "open file X" reads the file instead of launching an app
        if re.search(r"\bopen\b", t) and re.search(r"\bfiles?\b", t) and \
                "explorer" not in t and "folder" not in t:
            return "read_file"

        # ── open_url should win over open_app
        if re.search(r"\bopen (?:url|link)\b", t) or re.search(r"\bvisit\b", t):
            return "open_url"

        # App actions (English + "X open pannu")
        if re.search(r"\b(open|launch|start)\b", t) or re.search(
            r"\b(open|launch)\s+(pannu|pannunga|pannuda)\b", t
        ):
            return "open_app"
        # Kill process must be detected before generic close_app
        if re.search(r"\bkill (?:process|task)\b", t):
            return "kill_process"

        if re.search(r"\b(close|quit|kill)\b", t) or re.search(
            r"\b(close|quit)\s+(pannu|pannunga|pannuda)\b", t
        ):
            return "close_app"

        # Screen control
        if re.search(r"\bscreenshot\b|\bscreen shot\b|\bcapture screen\b", t):
            return "screenshot"
        if re.search(r"\bscreen size\b|\bdisplay (?:size|resolution)\b", t):
            return "screen_size"
        if re.search(r"\bmouse (?:move|cursor)\b", t):
            return "mouse_move"
        if re.search(r"\b(click|double click|right click)\b", t) and re.search(r"\b(mouse|screen|at \d)\b", t):
            return "mouse_click"
        if re.search(r"\btype (?:text|this|on screen)\b", t) or re.search(r"\bkeyboard type\b", t):
            return "keyboard_type"
        if re.search(r"\bpress (?:key|enter|tab|esc|escape)\b", t):
            return "press_key"
        if re.search(r"\bscroll\b", t) and re.search(r"\b(mouse|screen|up|down)\b", t):
            return "mouse_scroll"

        # System control
        if re.search(r"\b(volume|mute)\b", t):
            if re.search(r"\b(set|change|increase|decrease|raise|lower)\b", t) or re.search(r"\d", t):
                return "set_volume"
            if re.search(r"\bmute\b", t):
                return "mute_toggle"
            return "get_volume"
        if re.search(r"\bbrightness\b", t):
            if re.search(r"\b(set|change)\b", t) or re.search(r"\d", t):
                return "set_brightness"
            return "get_brightness"
        if re.search(r"\block (?:screen|pc|workstation|computer)\b", t):
            return "lock_screen"
        if re.search(r"\bsleep\b", t) and re.search(r"\b(pc|computer|system|laptop)\b", t):
            return "sleep_pc"
        if re.search(r"\b(shutdown|shut down|power off)\b", t):
            return "shutdown_pc"
        if re.search(r"\brestart\b", t) or re.search(r"\breboot\b", t):
            return "restart_pc"
        if re.search(r"\bcancel shutdown\b", t):
            return "cancel_shutdown"

        # Clipboard
        if re.search(r"\bclipboard\b", t):
            if re.search(r"\b(write|copy|set|put)\b", t):
                return "write_clipboard"
            return "read_clipboard"

        # Window management
        if re.search(r"\blist windows\b|\bshow windows\b|\bopen windows\b", t):
            return "list_windows"
        if re.search(r"\bfocus window\b|\bactivate window\b", t):
            return "focus_window"
        if re.search(r"\bminimize all\b|\bshow desktop\b", t):
            return "minimize_all"
        if re.search(r"\bclose window\b", t):
            return "close_window"

        # Process management
        if re.search(r"\blist processes\b|\bshow processes\b|\brunning processes\b", t):
            return "list_processes"
        if re.search(r"\bkill (?:process|task)\b", t):
            return "kill_process"
        if re.search(r"\bset priority\b", t):
            return "set_priority"

        # Browser control
        if re.search(r"\bopen url\b|\bopen link\b|\bvisit\b", t):
            return "open_url"
        if re.search(r"\bsearch (?:web|google|online)\b", t):
            return "search_web"
        if re.search(r"\bfetch (?:page|url|website)\b|\bscrape\b", t):
            return "fetch_page"

        # Advanced file ops
        if re.search(r"\bmove file\b|\bmove folder\b", t):
            return "move_file"
        if re.search(r"\bcopy file\b|\bcopy folder\b", t):
            return "copy_file"
        if re.search(r"\brename (?:file|folder)\b", t):
            return "rename_file"
        if re.search(r"\bzip\b", t) and re.search(r"\b(file|folder)\b", t):
            return "zip_path"
        if re.search(r"\bunzip\b", t):
            return "unzip_path"
        if re.search(r"\bsearch (?:content|inside files|text in files)\b", t):
            return "search_content"

        # Office control
        if re.search(r"\bexcel (?:write|set)\b", t):
            return "excel_write"
        if re.search(r"\bexcel (?:read|get)\b", t):
            return "excel_read"
        if re.search(r"\bword (?:create|new|make)\b", t):
            return "word_create_doc"
        if re.search(r"\bword (?:add|append)\b", t):
            return "word_add_text"

        # ── Productivity
        if re.search(r"\b(to-?do|task)\b", t) and re.search(
            r"\b(add|create|list|show|complete|done|finish|mark|delete)\b", t
        ):
            return "todo"
        if re.search(r"\b(schedule|calendar|appointment)\b", t):
            return "schedule"
        if re.search(
            r"\b(cpu|ram|disk|battery|system (?:status|info|report)|monitor)\b", t
        ):
            return "monitor"
        if re.search(r"\b(index|rag|knowledge base)\b", t):
            return "knowledge"

        # ── Conversational
        if re.search(r"\b(help|assist|support)\b", t):
            return "help"
        return "chat"

    @staticmethod
    def _looks_like_recall(t: str) -> bool:
        patterns = (
            r"\bwhat(?:'s| is) my name\b",
            r"\bwhat(?:'s| is) my (?:age|city|birthday|favourite|favorite)\b",
            r"\bwho am i\b",
            r"\bwhat do you (?:know|remember) about me\b",
            r"\bdo you remember\b",
            r"\ben peru enna\b",
            r"\ben peyar enna\b",
            r"\bennoda peru enna\b",
            r"\ben pathi enna theriyum\b",
            r"\bnaan enna learn\b",
            r"\bnaan enna kathukiren\b",
            r"\ben course enna\b",
            r"என் பெயர் என்ன",
            r"என்னோட பெயர் என்ன",
            r"நான் யார்",
            r"என்னை பற்றி",
            r"நான் என்ன கற்கிறேன்",
            r"என்ன படிக்கிறேன்",
        )
        return any(re.search(p, t) for p in patterns)

    def _is_simple_query(self, text: str, intent: str) -> bool:
        """Simple intents skip tools. Action intents are never simple."""
        return intent in SIMPLE_INTENTS

    def _needs_planning(self, intent: str) -> bool:
        """Kept for compatibility; planning is handled explicitly."""
        return intent == "plan"

    # ── Context & prompts ────────────────────────────────────────────
    def _build_context(self, text: str, intent: str) -> str:
        """Build context from personal memory, relevant memories, and notes."""
        parts: list[str] = []
        seen: set[int] = set()

        personal = self._memory.list("personal", limit=8)
        if personal:
            lines = []
            for entry in personal:
                value = entry.value.strip().replace("\n", " ")[:200]
                lines.append(f"- {entry.key}: {value}")
                seen.add(entry.id)
            parts.append("[What you know about the user]\n" + "\n".join(lines))

        try:
            relevant = self._memory.search(text, limit=5)
        except Exception:
            relevant = []
        relevant = [entry for entry in relevant if entry.id not in seen]
        if relevant:
            lines = []
            for entry in relevant:
                value = entry.value.strip().replace("\n", " ")[:200]
                lines.append(f"- [{entry.category}] {entry.key}: {value}")
                seen.add(entry.id)
            parts.append("[Relevant memories]\n" + "\n".join(lines))

        notes = [entry for entry in self._memory.list("conversation", limit=3) if entry.id not in seen]
        if notes:
            lines = []
            for entry in notes:
                value = entry.value.strip().replace("\n", " ")[:200]
                lines.append(f"- {value}")
            parts.append("[Recent notes]\n" + "\n".join(lines))

        return "\n\n".join(parts)[:1800]

    def _build_messages(
        self,
        text: str,
        context: str,
        eq_directive: str,
        language: str,
        strict_language: bool = False,
    ) -> list[dict[str, str]]:
        system_parts = [self._persona]
        system_parts.append(f"[Response language] {language_directive(language)}")
        if eq_directive:
            system_parts.append(f"[EQ Directive] {eq_directive}")
        if context:
            system_parts.append(f"[Context — facts you may rely on]\n{context}")
        if strict_language:
            if language == "english":
                system_parts.append(
                    "[STRICT LANGUAGE] The user wrote in English. Your entire reply "
                    "must be in English. Do not use Tamil script or Tanglish words."
                )
            elif language == "tanglish":
                system_parts.append(
                    "[STRICT LANGUAGE] Reply in Tanglish exactly like the user: "
                    "Tamil words in Tamil script, English/technical words in "
                    "Latin letters. Do not write the whole reply in Tamil script."
                )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(system_parts)}
        ]
        messages.extend(self._history_messages())
        messages.append({"role": "user", "content": text})
        return messages

    def _simple_response(
        self, text: str, context: str, eq_directive: str, language: str
    ) -> str:
        """Generate a conversational response via the engine."""
        messages = self._build_messages(text, context, eq_directive, language)
        result = self._engine.chat(messages)
        if not result.ok:
            return _PHRASES[language]["engine_down"]

        response = self._clean_response(result.text)

        # Small models sometimes ignore the language rule. Retry once for the
        # worst case: an English question answered in Tamil script, or a
        # Tanglish question answered entirely in Tamil script.
        needs_retry = False
        if language == "english" and has_tamil_script(response):
            needs_retry = True
        elif language == "tanglish" and response and not any(
            ch.isascii() and ch.isalpha() for ch in response
        ):
            needs_retry = True

        if needs_retry:
            retry = self._engine.chat(
                self._build_messages(
                    text, context, eq_directive, language, strict_language=True
                )
            )
            if retry.ok:
                retry_text = self._clean_response(retry.text)
                if language == "english" and not has_tamil_script(retry_text):
                    response = retry_text
                elif language == "tanglish" and any(
                    ch.isascii() and ch.isalpha() for ch in retry_text
                ):
                    response = retry_text
        return response or _PHRASES[language]["engine_down"]

    @staticmethod
    def _clean_response(text: str) -> str:
        """Normalise model output: no role prefix, no LaTeX, tidy spacing."""
        text = (text or "").strip()
        text = re.sub(r"^\s*(?:maya|assistant)\s*:\s*", "", text, flags=re.I)
        text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.S | re.I)
        text = text.replace("\\times", "×").replace("\\div", "÷")
        text = text.replace("\\(", "").replace("\\)", "")
        text = text.replace("\\[", "").replace("\\]", "")
        text = re.sub(r"\$([^$\n]{1,120})\$", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _engine_ok(text: str) -> bool:
        return not (text or "").startswith("[engine error]")

    def _history_messages(self) -> list[dict[str, str]]:
        """Last few turns as real chat messages (better than prompt stuffing)."""
        messages = []
        for message in self._history[-6:]:
            role = message.get("role", "user")
            content = str(message.get("content", ""))[:400]
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        return messages

    # ── Memory ───────────────────────────────────────────────────────
    _NAME_PATTERNS = (
        r"\bmy name is\s+([A-Za-z][A-Za-z'’.-]{0,30})",
        r"\ben\s+(?:peru|peyar)\s+([A-Za-z][A-Za-z'’.-]{0,30})",
        r"\bennoda\s+(?:peru|peyar)\s+([A-Za-z][A-Za-z'’.-]{0,30})",
    )
    _LEARNING_PATTERNS = (
        r"\bi(?:'m| am)\s+learning\s+([A-Za-z0-9+#. ]{1,40})",
        r"\bnaan\s+([A-Za-z0-9+#.]+)\s+(?:learn(?:ing)?|kathukiren|kathukkiren|padikkiren)\b",
    )

    def _extract_facts(self, text: str) -> list[tuple[str, str, str]]:
        """Extract durable personal facts from a message."""
        facts: list[tuple[str, str, str]] = []

        for pattern in self._NAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip(" .,!?")
                if name and name.lower() not in {"a", "the", "my"}:
                    facts.append(("personal", "name", name))
                break

        for pattern in self._LEARNING_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                topic = match.group(1).strip(" .,!?")
                if topic:
                    facts.append(("personal", "learning", topic))
                break

        match = re.search(r"\bi like\s+([^.,!?\n]{1,80})", text, re.IGNORECASE)
        if match:
            facts.append(("personal", "likes", match.group(1).strip()))
        match = re.search(r"\benakku\s+([^.,!?\n]{1,80}?)\s+pidikkum\b", text, re.IGNORECASE)
        if match:
            facts.append(("personal", "likes", match.group(1).strip()))

        match = re.search(
            r"\bmy\s+(age|birthday|city|hometown|college|school|job|goal|language|"
            r"colour|color|food|hobby)\s+is\s+([^.,!?\n]{1,80})",
            text,
            re.IGNORECASE,
        )
        if match:
            facts.append(("personal", match.group(1).lower(), match.group(2).strip()))

        match = re.search(
            r"\bmy\s+(?:favourite|favorite|preferred)\s+(\w+)\s+is\s+([^.,!?\n]{1,80})",
            text,
            re.IGNORECASE,
        )
        if match:
            facts.append(("personal", match.group(1).lower(), match.group(2).strip()))

        match = re.search(
            r"\bi(?:'m| am)\s+(?:building|working on)\s+([^.,!?\n]{1,80})",
            text,
            re.IGNORECASE,
        )
        if match:
            facts.append(("project", "current", match.group(1).strip()))

        # De-duplicate within one message (keys are unique per category).
        unique: dict[tuple[str, str], str] = {}
        for category, key, value in facts:
            if value:
                unique[(category, key)] = value
        return [(category, key, value) for (category, key), value in unique.items()]

    def _save_facts(self, facts: list[tuple[str, str, str]]) -> tuple[list[tuple[str, str]], bool]:
        """Persist facts. Returns (saved, secret_blocked)."""
        saved: list[tuple[str, str]] = []
        secret_blocked = False
        for category, key, value in facts:
            value = value.strip()
            if not value:
                continue
            try:
                existing = self._memory.get(category, key)
                if existing and existing.value.strip() == value:
                    saved.append((key, value))
                    continue
                self._memory.add(category, key, value, sensitivity="low")
                saved.append((key, value))
            except Exception as exc:
                if "secret" in str(exc).lower():
                    secret_blocked = True
        return saved, secret_blocked

    def _save_explicit_memory(self, text: str) -> tuple[list[tuple[str, str]], bool]:
        """Handle "remember ..." — save structured facts and/or a note."""
        facts = self._extract_facts(text)
        saved, secret_blocked = self._save_facts(facts)

        if not saved and not secret_blocked:
            note = self._extract_note(text)
            if note:
                try:
                    key = "note_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    self._memory.add("conversation", key, note, sensitivity="low")
                    saved.append(("note", note))
                except Exception as exc:
                    if "secret" in str(exc).lower():
                        secret_blocked = True
        return saved, secret_blocked

    @staticmethod
    def _extract_note(text: str) -> str:
        note = re.sub(
            r"^\s*(?:please\s+)?(?:remember(?: that)?|note that|keep in mind|"
            r"don'?t forget(?: that)?|nyabagam vai|ninaivul vai)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip(" .,!?")
        if note.lower() in {"", "this", "that", "it", "this one"}:
            return ""
        return note[:500]

    def _maybe_save_conversation_memory(self, user_text: str, assistant_text: str) -> bool:
        """Save durable facts from normal conversation (not only "remember")."""
        if user_text.strip().endswith("?"):
            # Questions rarely state facts; leave them alone.
            return False
        facts = self._extract_facts(user_text)
        if not facts:
            return False
        saved, _ = self._save_facts(facts)
        return bool(saved)

    def _recall_memory(self, text: str, language: str) -> str | None:
        lower = text.lower()
        personal = {e.key: e.value.strip() for e in self._memory.list("personal", limit=20)}
        notes = self._memory.list("conversation", limit=3)
        if not personal and not notes:
            return _PHRASES[language]["no_memory"]

        answers: list[str] = []

        asks_name = bool(
            re.search(
                r"\b(what(?:'s| is) my name|who am i|en peru enna|en peyar enna|"
                r"ennoda peru enna)\b|(?:என் பெயர் என்ன|என்னோட பெயர் என்ன|நான் யார்)",
                lower,
            )
        )
        asks_learning = bool(
            re.search(
                r"\b(what am i learning|what am i studying|naan enna learn|"
                r"naan enna kathukiren|en course enna)\b|"
                r"(?:நான் என்ன கற்கிறேன்|என்ன படிக்கிறேன்)",
                lower,
            )
        )
        asks_likes = bool(
            re.search(
                r"\b(what do i like|enakku enna pidikkum)\b|(?:எனக்கு என்ன பிடிக்கும்)",
                lower,
            )
        )

        if asks_name:
            name = personal.get("name")
            if name:
                answers.append(
                    {
                        "english": f"Your name is {name}.",
                        "tanglish": f"Unga peru {name}.",
                        "tamil": f"உங்கள் பெயர் {name}.",
                    }[language]
                )
            else:
                answers.append(_PHRASES[language]["not_remembered"])

        if asks_learning:
            topic = personal.get("learning") or personal.get("course")
            if topic:
                answers.append(
                    {
                        "english": f"You're learning {topic}.",
                        "tanglish": f"Neenga {topic} learn panreenga.",
                        "tamil": f"நீங்கள் {topic} கற்கிறீர்கள்.",
                    }[language]
                )
            else:
                answers.append(_PHRASES[language]["not_remembered"])

        if asks_likes:
            likes = personal.get("likes")
            if likes:
                answers.append(
                    {
                        "english": f"You like {likes}.",
                        "tanglish": f"Ungalukku {likes} pidikkum.",
                        "tamil": f"உங்களுக்கு {likes} பிடிக்கும்.",
                    }[language]
                )
            else:
                answers.append(_PHRASES[language]["not_remembered"])

        if answers:
            return " ".join(answers)

        # General "what do you know about me?"
        entries = []
        for key, value in personal.items():
            entries.append(f"{key} — {value}")
        for note in notes:
            entries.append(note.value.strip()[:200])
        if not entries:
            return _PHRASES[language]["no_memory"]

        joined = "; ".join(entries[:8])
        return {
            "english": f"Here's what I remember about you: {joined}.",
            "tanglish": f"Ungalai pathi idhu theriyum: {joined}.",
            "tamil": f"உங்களைப் பற்றி இவை நினைவில் உள்ளன: {joined}.",
        }[language]

    @staticmethod
    def _ack_memory(
        saved: list[tuple[str, str]], language: str, secret_blocked: bool
    ) -> str:
        if secret_blocked and not saved:
            return _PHRASES[language]["nothing_saved"]

        facts = dict(saved)
        name = facts.get("name")
        learning = facts.get("learning")
        likes = facts.get("likes")

        if language == "tanglish":
            parts = []
            if name:
                parts.append(f"Sari {name}, note pannitten.")
            else:
                parts.append("Sari, note pannitten.")
            if learning:
                parts.append(f"Neenga {learning} learn panreenga.")
            if likes:
                parts.append(f"Ungalukku {likes} pidikkum.")
            if len(parts) == 1 and "note" not in facts:
                parts.append("Adha remember pannuven.")
            return " ".join(parts)

        if language == "tamil":
            parts = []
            if name:
                parts.append(f"சரி {name}, நினைவில் வைத்துக்கொள்கிறேன்.")
            else:
                parts.append("சரி, நினைவில் வைத்துக்கொள்கிறேன்.")
            if learning:
                parts.append(f"நீங்கள் {learning} கற்கிறீர்கள்.")
            if likes:
                parts.append(f"உங்களுக்கு {likes} பிடிக்கும்.")
            return " ".join(parts)

        parts = []
        if name:
            parts.append(f"Got it, {name}.")
        else:
            parts.append("Got it.")
        clauses = []
        if learning:
            clauses.append(f"you're learning {learning}")
        if likes:
            clauses.append(f"you like {likes}")
        if clauses:
            parts.append("I'll remember that " + " and ".join(clauses) + ".")
        else:
            parts.append("I'll remember that.")
        return " ".join(parts)

    # ── Action parameters ────────────────────────────────────────────
    def _extract_params(self, text: str, intent: str) -> dict:
        """Extract parameters from text for the intent."""
        params: dict[str, Any] = {}
        lower = text.lower()

        def clean(value: str) -> str:
            value = value.strip(" \t\"'`.,!?")
            value = re.sub(r"\s+", " ", value)
            return value.strip()

        # Screen control params
        if intent == "mouse_move":
            m = re.search(r"(\d+)\s*[,\s]+\s*(\d+)", text)
            if m:
                params["x"] = int(m.group(1))
                params["y"] = int(m.group(2))
        elif intent == "mouse_click":
            m = re.search(r"(\d+)\s*[,\s]+\s*(\d+)", text)
            if m:
                params["x"] = int(m.group(1))
                params["y"] = int(m.group(2))
            if re.search(r"right", text, re.I):
                params["button"] = "right"
            elif re.search(r"middle", text, re.I):
                params["button"] = "middle"
            else:
                params["button"] = "left"
        elif intent == "mouse_scroll":
            m = re.search(r"(-?\d+)", text)
            if m:
                params["amount"] = int(m.group(1))
        elif intent == "keyboard_type":
            val = re.sub(r"^.*?(?:type|keyboard type)\s*", "", text, flags=re.I).strip()
            params["text"] = val or text
        elif intent == "press_key":
            m = re.search(r"press\s+(?:key\s+)?(.+)", text, re.I)
            params["key"] = (m.group(1).strip() if m else text).strip(" .,!?'")
        elif intent == "set_volume":
            m = re.search(r"(\d+)", text)
            if m:
                params["level"] = int(m.group(1))
        elif intent == "set_brightness":
            m = re.search(r"(\d+)", text)
            if m:
                params["level"] = int(m.group(1))
        elif intent == "focus_window" or intent == "close_window":
            val = re.sub(r"^.*?(?:focus|activate|close)\s+window\s*", "", text, flags=re.I).strip()
            params["title"] = val or text
        elif intent == "write_clipboard":
            val = re.sub(r"^.*?(?:write|copy|set|put)\s+(?:to\s+)?clipboard\s*", "", text, flags=re.I).strip()
            params["text"] = val or text
        elif intent == "list_processes":
            val = re.sub(r"^.*?(?:list|show|running)\s+processes?\s*", "", text, flags=re.I).strip()
            if val:
                params["filter"] = val
        elif intent == "kill_process":
            val = re.sub(r"^.*?kill\s+(?:process|task)\s*", "", text, flags=re.I).strip()
            params["target"] = val or text
        elif intent == "set_priority":
            m = re.search(r"priority\s+(\w+)", text, re.I)
            if m:
                params["priority"] = m.group(1)
            val = re.sub(r"^.*?set priority\s*", "", text, flags=re.I).strip()
            params["target"] = val or text

        # Browser params
        if intent == "open_url":
            m = re.search(r"(?:open url|open link|visit)\s+(.+)", text, re.I)
            params["url"] = (m.group(1).strip() if m else text).strip(" .,!?'\"")
        elif intent == "search_web":
            m = re.search(r"search (?:web|google|online)\s+(.+)", text, re.I)
            params["query"] = (m.group(1).strip() if m else text).strip(" .,!?'\"")
        elif intent == "fetch_page":
            m = re.search(r"fetch (?:page|url|website)\s+(.+)", text, re.I)
            params["url"] = (m.group(1).strip() if m else text).strip(" .,!?'\"")

        # Advanced file params
        elif intent == "move_file":
            m = re.search(r"move (?:file|folder)\s+(.+?)\s+(?:to)\s+(.+)", text, re.I)
            if m:
                params["src"] = m.group(1).strip()
                params["dst"] = m.group(2).strip()
        elif intent == "copy_file":
            m = re.search(r"copy (?:file|folder)\s+(.+?)\s+(?:to)\s+(.+)", text, re.I)
            if m:
                params["src"] = m.group(1).strip()
                params["dst"] = m.group(2).strip()
        elif intent == "rename_file":
            m = re.search(r"rename (?:file|folder)\s+(.+?)\s+(?:to|as)\s+(.+)", text, re.I)
            if m:
                params["path"] = m.group(1).strip()
                params["new_name"] = m.group(2).strip()
        elif intent == "zip_path":
            m = re.search(r"zip\s+(.+)", text, re.I)
            if m:
                params["path"] = m.group(1).strip()
        elif intent == "unzip_path":
            m = re.search(r"unzip\s+(.+)", text, re.I)
            if m:
                params["zip_path"] = m.group(1).strip()
        elif intent == "search_content":
            m = re.search(r"search (?:content|inside files|text in files)\s+(.+)", text, re.I)
            if m:
                params["query"] = m.group(1).strip()
            params["directory"] = "."

        # Office params
        elif intent == "excel_write":
            m = re.search(r"excel (?:write|set)\s+(\S+)\s+(\S+)\s+(.+)", text, re.I)
            if m:
                params["path"] = m.group(1).strip()
                params["cell"] = m.group(2).strip()
                params["value"] = m.group(3).strip()
        elif intent == "excel_read":
            m = re.search(r"excel (?:read|get)\s+(\S+)(?:\s+(\S+))?", text, re.I)
            if m:
                params["path"] = m.group(1).strip()
                params["range"] = (m.group(2) or "A1").strip()
        elif intent == "word_create_doc":
            m = re.search(r"word (?:create|new|make)\s+(\S+)(?:\s+(.+))?", text, re.I)
            if m:
                params["path"] = m.group(1).strip()
                params["text"] = (m.group(2) or "").strip()
        elif intent == "word_add_text":
            m = re.search(r"word (?:add|append)\s+(\S+)\s+(.+)", text, re.I)
            if m:
                params["path"] = m.group(1).strip()
                params["text"] = m.group(2).strip()

        if intent in {"open_app", "close_app"}:
            verbs = "open|launch|start|close|quit|kill"
            # "notepad open pannu"
            match = re.search(
                rf"^(.+?)\s+(?:{verbs})(?:\s+(?:pannu|pannunga|pannuda))?\s*[.!?]*$",
                text,
                re.IGNORECASE,
            )
            if match:
                candidate = re.sub(
                    r"^(?:please|can you|could you|would you|maya[,\s]+)\s*",
                    "",
                    match.group(1),
                    flags=re.IGNORECASE,
                )
                candidate = clean(candidate)
                if candidate and candidate.lower() not in {"maya", "please"}:
                    params["name"] = candidate
            if "name" not in params:
                match = re.search(
                    rf"\b(?:{verbs})\b\s+(?:the\s+|a\s+)?(.+)", text, re.IGNORECASE
                )
                if match:
                    candidate = re.sub(
                        r"^(?:pannu|pannunga|pannuda)\s+", "", match.group(1), flags=re.I
                    )
                    candidate = re.sub(
                        r"\s+(?:app|application|program|software)$", "", candidate, flags=re.I
                    )
                    candidate = clean(candidate)
                    if candidate:
                        params["name"] = candidate

        elif intent == "search_files":
            query = re.sub(
                r"^\s*(?:search|find|look for|thedu)\s+(?:for\s+)?",
                "",
                text,
                flags=re.IGNORECASE,
            )
            query = re.sub(
                r"\b(?:file|files|folder|folders|document|documents)\b",
                " ",
                query,
                flags=re.IGNORECASE,
            )
            query = re.sub(r"\b(?:named|called)\b", " ", query, flags=re.IGNORECASE)
            query = re.sub(r"^\s*(?:for|in)\s+", "", query, flags=re.IGNORECASE)
            params["query"] = clean(query) or clean(text)

        elif intent == "read_file":
            match = re.search(
                r"\b(?:read|show|view|display|cat|open)\b.*?\bfiles?\b\s+"
                r"(?:named\s+|called\s+)?(.+)",
                text,
                re.IGNORECASE,
            )
            if match:
                params["path"] = clean(match.group(1))

        elif intent == "create_folder":
            match = re.search(
                r"\b(?:create|make|new)\b.*?\b(?:folder|directory)\b\s+"
                r"(?:named\s+|called\s+)?(.+)",
                text,
                re.IGNORECASE,
            )
            if match:
                params["path"] = clean(match.group(1))
            else:
                match = re.search(
                    r"^(.+?)\s+(?:folder|directory)\s+(?:create|make)\s+"
                    r"(?:pannu|pannunga|pannuda)?\s*[.!?]*$",
                    text,
                    re.IGNORECASE,
                )
                if match:
                    params["path"] = clean(match.group(1))

        elif intent == "delete_file":
            match = re.search(
                r"\b(?:delete|remove|rm)\b.*?\b(?:file|folder)\b\s+(.+)",
                text,
                re.IGNORECASE,
            )
            if match:
                params["path"] = clean(match.group(1))
            else:
                match = re.search(
                    r"^(.+?)\s+(?:file|folder)\s+(?:delete|remove)\s+"
                    r"(?:pannu|pannunga|pannuda)?\s*[.!?]*$",
                    text,
                    re.IGNORECASE,
                )
                if match:
                    params["path"] = clean(match.group(1))

        elif intent == "run_command":
            match = re.search(
                r"\b(?:run|execute)\b.*?\b(?:command|cmd|shell|terminal)\b\s+(.+)",
                text,
                re.IGNORECASE,
            )
            if match:
                params["command"] = clean(match.group(1))

        elif intent == "todo":
            if re.search(r"\b(list|show)\b", lower) or re.search(
                r"\b(todo|task)\s+list\b", lower
            ):
                params["action"] = "list"
            elif re.search(r"\b(complete|done|finish|mark)\b", lower):
                params["action"] = "complete"
                match = re.search(r"\b(\d+)\b", text)
                if match:
                    params["index"] = int(match.group(1))
            else:
                params["action"] = "add"
                match = re.search(
                    r"\b(?:add|create)\b.*?\b(?:to-?do|task)\b\s*(?:to\s+)?(.+)",
                    text,
                    re.IGNORECASE,
                )
                if not match:
                    match = re.search(
                        r"\b(?:to-?do|task)\b\s+(?:add\s+)?(?:pannu\s+)?(.+)",
                        text,
                        re.IGNORECASE,
                    )
                if match:
                    item = re.sub(
                        r"^(?:pannu|pannunga)\s+", "", match.group(1), flags=re.I
                    )
                    params["text"] = clean(item)

        elif intent == "reminder":
            if re.search(r"\b(list|show)\b", lower):
                params["action"] = "list"
            else:
                params["action"] = "add"
                when = "soon"
                time_match = re.search(
                    r"\b(?:at|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
                    text,
                    re.IGNORECASE,
                )
                in_match = re.search(
                    r"\bin\s+(\d+)\s+(minutes?|hours?|mins?)\b", text, re.IGNORECASE
                )
                if time_match:
                    when = time_match.group(1).strip()
                elif in_match:
                    when = f"in {in_match.group(1)} {in_match.group(2)}"
                elif re.search(r"\b(tomorrow|naalai)\b", lower):
                    when = "tomorrow"
                elif re.search(r"\b(today|innikku|tonight)\b", lower):
                    when = "today"
                params["when"] = when
                body = re.sub(
                    r"^\s*(?:please\s+)?(?:remind me(?: to)?|set (?:a )?reminder(?: to)?|"
                    r"reminder[:\s]+|nyabagam paduthu)\s*",
                    "",
                    text,
                    flags=re.IGNORECASE,
                )
                body = re.sub(
                    r"\b(?:at|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
                    "",
                    body,
                    flags=re.IGNORECASE,
                )
                body = re.sub(
                    r"\b(?:tomorrow|today|tonight|naalai|innikku)\b",
                    "",
                    body,
                    flags=re.IGNORECASE,
                )
                params["text"] = clean(body) or clean(text)

        elif intent == "schedule":
            params["text"] = clean(text)
            time_match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
            params["time"] = (
                time_match.group(1) if time_match else datetime.now().strftime("%H:%M")
            )

        elif intent == "knowledge":
            if "index" in lower:
                params["action"] = "index"
            else:
                params["action"] = "search"
                params["query"] = clean(text)

        return params

    # ── Response formatting ──────────────────────────────────────────
    def _format_plan(self, steps: list[str], language: str) -> str:
        header = _PHRASES[language]["plan_header"]
        lines = [header]
        for index, step in enumerate(steps[:7], start=1):
            lines.append(f"{index}. {step}")
        return "\n".join(lines)

    def _format_action_response(
        self,
        intent: str,
        aq_result: Any,
        tone: str,
        language: str,
        params: dict | None = None,
    ) -> str:
        params = params or {}
        base = self._localize_action_message(intent, aq_result, language, params)
        data = self._format_action_data(intent, aq_result.result, language)
        response = base
        if data:
            response = f"{response}\n{data}" if response else data

        suffix = _PHRASES[language].get(f"tone_{tone}", "")
        if suffix and tone in {"sad", "stressed", "tired", "angry"}:
            response += suffix
        return response

    def _localize_action_message(
        self, intent: str, aq_result: Any, language: str, params: dict
    ) -> str:
        if language == "english":
            message = (aq_result.message or "").strip()
            if message and not message.endswith((".", "!", "?")):
                message += "."
            return message

        name = str(params.get("name", "")).strip()
        path = str(params.get("path", "")).strip()

        if language == "tanglish":
            mapping = {
                "open_app": f"{name} open pannitten." if name else "App open pannitten.",
                "close_app": f"{name} close pannitten." if name else "App close pannitten.",
                "create_folder": f"Folder create pannitten: {path}" if path else "Folder create pannitten.",
                "delete_file": f"Delete pannitten: {path}" if path else "Delete pannitten.",
                "run_command": "Command run pannitten.",
                "todo": "Done.",
                "reminder": "Reminder set pannitten.",
                "schedule": "Schedule set pannitten.",
                "monitor": "System report idhu:",
                "knowledge": "Idhu dhaan kandadhu:",
                "search_files": "Idhu dhaan kandadhu:",
                "read_file": "File content idhu:",
            }
            return mapping.get(intent, aq_result.message)

        mapping = {
            "open_app": f"{name} திறந்துவிட்டேன்." if name else "App திறந்துவிட்டேன்.",
            "close_app": f"{name} மூடிவிட்டேன்." if name else "App மூடிவிட்டேன்.",
            "create_folder": f"Folder உருவாக்கிவிட்டேன்: {path}" if path else "Folder உருவாக்கிவிட்டேன்.",
            "delete_file": f"நீக்கிவிட்டேன்: {path}" if path else "நீக்கிவிட்டேன்.",
            "run_command": "Command இயக்கிவிட்டேன்.",
            "todo": "முடிந்தது.",
            "reminder": "Reminder அமைத்துவிட்டேன்.",
            "schedule": "Schedule அமைத்துவிட்டேன்.",
            "monitor": "System report:",
            "knowledge": "கிடைத்தவை:",
            "search_files": "கிடைத்தவை:",
            "read_file": "File உள்ளடக்கம்:",
        }
        return mapping.get(intent, aq_result.message)

    def _format_action_data(self, intent: str, result: Any, language: str) -> str:
        if result is None:
            return ""

        if intent == "read_file" and isinstance(result, str):
            content = result.strip()
            if not content:
                return ""
            return content[:1500]

        if intent == "monitor" and isinstance(result, str):
            return result.strip()[:1500]

        if isinstance(result, list):
            if not result:
                if intent == "todo":
                    return _PHRASES[language]["todo_none"]
                if intent == "reminder":
                    return _PHRASES[language]["reminder_none"]
                if intent in {"search_files", "knowledge"}:
                    return _PHRASES[language]["search_none"]
                return ""
            lines = []
            for item in result[:10]:
                if isinstance(item, dict):
                    if "task" in item:
                        mark = "x" if item.get("done") else " "
                        lines.append(f"- [{mark}] {item.get('task')}")
                    elif "text" in item and "time" in item:
                        lines.append(f"- {item.get('text')} — {item.get('time')}")
                    elif "path" in item:
                        lines.append(f"- {item.get('path')}")
                    else:
                        lines.append("- " + ", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)

        if isinstance(result, dict):
            lines = [
                f"- {key}: {value}"
                for key, value in result.items()
                if value not in (None, "", [], {})
            ]
            return "\n".join(lines[:15])

        if isinstance(result, str) and result.strip():
            if intent in {"read_file", "monitor"}:
                return result.strip()[:1500]
            return ""
        return ""

    def _action_failure_response(self, intent: str, message: str, language: str) -> str:
        lowered = (message or "").lower()
        phrases = _PHRASES[language]
        if "cancelled" in lowered:
            return phrases["cancelled"]
        if "app name required" in lowered:
            return phrases["ask_open"] if intent == "open_app" else phrases["ask_close"]
        if "path" in lowered and "required" in lowered:
            return phrases["ask_file"]
        if "file path required" in lowered:
            return phrases["ask_file"]
        if "command required" in lowered:
            return phrases["ask_command"]
        return phrases["failed"].format(detail=message)

    # ── Misc ─────────────────────────────────────────────────────────
    def _sync_engines(self) -> None:
        """Keep engines wired to the current adapters (test/DI friendliness)."""
        self._iq._engine = self._engine
        self._iq._knowledge = self._knowledge
        self._aq._pc = self._pc
        self._aq._assistant = self._assistant
        self._aq._knowledge = self._knowledge
        self._aq._screen = self._screen
        self._aq._system = self._system
        self._aq._browser = self._browser
        self._aq._files = self._files
        self._aq._office = self._office

    def _detect_language(self, text: str) -> str:
        try:
            return self._language.detect(text)
        except Exception:
            return detect_language(text)

    def _add_to_history(self, role: str, content: str) -> None:
        """Add message to conversation history."""
        self._history.append({"role": role, "content": content})
        if len(self._history) > 20:
            self._history = self._history[-20:]

    def _record_turn(self, user_text: str, assistant_text: str) -> None:
        self._add_to_history("user", user_text)
        self._add_to_history("assistant", assistant_text)

    def chat(self, user_input: str) -> str:
        """Simple chat interface."""
        result = self.process(user_input)
        return result.response

    def set_persona(self, prompt: str) -> None:
        """Swap the system prompt (used by the laptop CLI's /persona)."""
        if prompt:
            self._persona = prompt
            self._iq._persona = prompt

    def clear_history(self) -> None:
        """Forget the in-memory conversation (persistent memory is kept)."""
        self._history.clear()

    def get_memory_stats(self) -> dict:
        """Get memory statistics."""
        return self._memory.stats()

    def health_check(self) -> dict:
        """Check health of all components."""
        engine_health = self._engine.health()
        return {
            "engine": "ok" if engine_health.ok else f"error: {engine_health.text}",
            "memory": "ok",
            "memory_stats": self.get_memory_stats(),
        }

    def _run_agent(self, goal: str, language: str) -> str:
        """Execute a multi-step goal autonomously with verification."""
        context = self._build_context(goal, "agent")
        lang_dir = language_directive(language)
        actions = self._iq.plan_actions(goal, context, lang_dir)

        if not actions:
            # Fallback: text plan only, no execution
            steps = self._iq.plan(goal, context, lang_dir)
            return self._format_plan(steps, language) + "\n\n(Auto-execution unavailable; plan shown only.)"

        lines = ["Agent plan:"]
        for i, a in enumerate(actions, start=1):
            lines.append(f"{i}. {a.get('description') or a['intent']} ({a['intent']})")
        lines.append("")
        lines.append("Executing...")

        results = []
        for idx, action in enumerate(actions, start=1):
            intent = action["intent"]
            params = action.get("params", {}) or {}
            lines.append(f"Step {idx}: {intent} ...")
            try:
                aq = self._aq.execute(intent, params)
            except Exception as e:
                aq = None
                err = str(e)
                lines.append(f"  -> error: {err}")
                results.append((intent, False, err))
                break
            if aq is None:
                lines.append("  -> no result")
                break
            ok = bool(getattr(aq, "success", False))
            msg = getattr(aq, "message", "") or ""
            lines.append(f"  -> {'OK' if ok else 'FAIL'}: {msg}")
            results.append((intent, ok, msg))
            if not ok:
                # one replan attempt for this step
                try:
                    alt_actions = self._iq.plan_actions(
                        f"Alternative for failed step: {intent} {params}. Goal: {goal}",
                        context, lang_dir)
                    if alt_actions:
                        alt = alt_actions[0]
                        lines.append(f"  -> retrying with {alt['intent']} ...")
                        aq2 = self._aq.execute(alt["intent"], alt.get("params", {}) or {})
                        ok2 = bool(getattr(aq2, "success", False))
                        lines.append(f"  -> retry {'OK' if ok2 else 'FAIL'}: {getattr(aq2,'message','')}")
                        results.append((alt["intent"], ok2, getattr(aq2, "message", "")))
                        if not ok2:
                            break
                        continue
                except Exception:
                    pass
                break

        # Summary
        done = sum(1 for r in results if r[1])
        lines.append("")
        lines.append(f"Completed {done}/{len(results)} steps.")
        return "\n".join(lines)

    def close(self) -> None:
        """Clean up resources."""
        self._engine.close()
