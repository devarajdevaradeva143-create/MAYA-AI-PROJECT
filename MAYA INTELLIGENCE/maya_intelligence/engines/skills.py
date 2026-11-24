"""Deterministic skills — accurate answers without asking the small model.

A 2B local model is good at conversation but unreliable at arithmetic, dates,
and self-description. These helpers answer those intents exactly, every time.
"""

from __future__ import annotations

import ast
import operator
import re
from datetime import datetime

_MAX_EXPR_LEN = 160
_MAX_EXPONENT = 1000

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_STRIP_PREFIX_RE = re.compile(
    r"^\s*(?:hey\s+)?(?:maya[,\s!]*)?"
    r"(?:what(?:'s| is)|whats|calculate|compute|solve|evaluate|"
    r"how much is|how much|tell me|enna|evlo|evalo)\s+",
    re.IGNORECASE,
)
_STRIP_SUFFIX_RE = re.compile(
    r"\s+(?:enna|sollu|please|pls|da|di|bro|macha|machi)\s*$",
    re.IGNORECASE,
)
_ALLOWED_EXPR_RE = re.compile(r"^[\s\d+\-*/%^().]+$")
_PERCENT_OF_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_DATE_LIKE_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_NUMBER_WORDS = {
    r"\bplus\b": "+",
    r"\bminus\b": "-",
    r"\btimes\b": "*",
    r"\bmultiplied by\b": "*",
    r"\bdivided by\b": "/",
    r"\bdivide by\b": "/",
}

_GREETING_RE = re.compile(
    r"^\s*(?:hi+|hello+|hey+|hai+|vanakkam|namaste|good (?:morning|afternoon|evening|night))"
    r"\s*(?:maya|da|di)?\s*[!?.]*\s*$",
    re.IGNORECASE,
)


def try_greeting(text: str, language: str = "english") -> str | None:
    """Short, natural replies for simple greetings."""
    if not _GREETING_RE.match(text.strip()):
        return None
    if language == "tamil":
        return "வணக்கம்! 😊 எப்படி இருக்கிறீர்கள்? என்ன வேண்டும்?"
    if language == "tanglish":
        return "Vanakkam! 😊 Epdi irukka? Enna venum?"
    return "Hi! 😊 How are you? What can I help you with?"

_TIME_RE = re.compile(
    r"\b(?:what(?:'s| is)?\s+(?:the\s+)?time|what time is it|current time|"
    r"time enna|ippo\s+time|time sollu)\b|(?:நேரம் என்ன|இப்போது நேரம்|நேரம் சொல்லு)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:what(?:'s| is)?\s+(?:today'?s?\s+)?(?:date|day)|today'?s date|"
    r"date enna|enna date|what day is (?:it|today)|date sollu|"
    r"what is today)\b|(?:தேதி என்ன|இன்றைய தேதி|இன்று என்ன தேதி)",
    re.IGNORECASE,
)
_IDENTITY_RE = re.compile(
    r"\b(?:who are you|what(?:'s| is)? your name|your name|nee yaaru|"
    r"un peru enna|maya yaaru|introduce yourself)\b|"
    r"(?:நீ யார்|நீங்கள் யார்|உன் பெயர் என்ன|உங்கள் பெயர் என்ன|மாயா யார்|"
    r"உன்னை அறிமுகப்படுத்து)",
    re.IGNORECASE,
)
_CAPABILITY_RE = re.compile(
    r"\b(?:what can you do|what are your capabilities|your capabilities|"
    r"enna panna mudiyum|neenga enna panna mudiyum|help me understand)\b|"
    r"(?:என்ன செய்ய முடியும்|உங்கள் திறன்கள்|உன்னால் என்ன செய்ய முடியும்)",
    re.IGNORECASE,
)


# ── Safe arithmetic ───────────────────────────────────────────────────────


def _safe_eval(node: ast.AST):
    """Evaluate a tiny arithmetic AST. Raises ValueError on anything else."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError("exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _fmt_number(value) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        rounded = round(value, 6)
        return f"{rounded:g}"
    return str(value)


def _normalize_expr(text: str) -> str:
    expr = _STRIP_PREFIX_RE.sub("", text.strip())
    expr = _STRIP_SUFFIX_RE.sub("", expr).strip()
    expr = expr.rstrip("?.!; ")
    expr = (
        expr.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("–", "-")
        .replace("^", "**")
    )
    expr = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expr)
    for pattern, replacement in _NUMBER_WORDS.items():
        expr = re.sub(pattern, replacement, expr, flags=re.IGNORECASE)
    return expr.strip()


def try_math(text: str) -> str | None:
    """Return a precise arithmetic answer, or None if the text is not math."""
    if not text or not text.strip():
        return None

    percent = _PERCENT_OF_RE.search(text)
    if percent:
        pct = float(percent.group(1))
        value = float(percent.group(2))
        result = pct / 100.0 * value
        return f"{_fmt_number(pct)}% of {_fmt_number(value)} = {_fmt_number(result)}"

    expr = _normalize_expr(text)
    if not expr or len(expr) > _MAX_EXPR_LEN:
        return None
    if _DATE_LIKE_RE.search(expr):
        return None
    if not re.search(r"\d", expr):
        return None

    # Require a real operator. A spaced minus is allowed for "10 - 4"; a bare
    # hyphen inside a number ("2026-11-24") is not arithmetic.
    has_strong_op = bool(re.search(r"[*/+%^]", expr))
    has_spaced_minus = bool(re.search(r"\d\s+-\s+\d", expr))
    if not has_strong_op and not has_spaced_minus:
        return None
    if not _ALLOWED_EXPR_RE.match(expr):
        return None
    if re.search(r"[*/%]\s*0(?:\.0+)?\s*$", expr):
        # Show a friendly message for division/modulo by zero.
        return "That would be division by zero, so there is no answer."

    try:
        value = _safe_eval(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return "That would be division by zero, so there is no answer."
    except (SyntaxError, ValueError, OverflowError):
        return None
    except Exception:
        return None

    pretty = expr.replace("**", "^").replace("*", "×").replace("/", "÷")
    pretty = re.sub(r"\s+", " ", pretty).strip()
    return f"{pretty} = {_fmt_number(value)}"


# ── Date, time, identity ─────────────────────────────────────────────────


def _joined(parts: list[str]) -> str:
    return ", ".join(part for part in parts if part)


def try_datetime(text: str, language: str = "english") -> str | None:
    """Answer time/date questions using the real system clock."""
    wants_time = bool(_TIME_RE.search(text))
    wants_date = bool(_DATE_RE.search(text))
    if not wants_time and not wants_date:
        return None

    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip("0")
    date_str = now.strftime("%A, %d %B %Y").replace(" 0", " ")

    if language == "tamil":
        if wants_time and wants_date:
            return f"இப்போது {time_str}, {date_str}."
        if wants_time:
            return f"இப்போது மணி {time_str}."
        return f"இன்று {date_str}."
    if language == "tanglish":
        if wants_time and wants_date:
            return f"Ippo {time_str}, {date_str}."
        if wants_time:
            return f"Ippo {time_str}."
        return f"Innikku {date_str}."

    if wants_time and wants_date:
        return f"It's {time_str} on {date_str}."
    if wants_time:
        return f"It's {time_str}."
    return f"Today is {date_str}."


def try_identity(text: str, language: str = "english") -> str | None:
    """Answer identity/capability questions consistently."""
    if _IDENTITY_RE.search(text):
        if language == "tamil":
            return (
                "நான் மாயா — உங்கள் முழுமையான ஆஃப்லைன் AI உதவியாளர். "
                "பேசலாம், கேள்விக்கு பதில் சொல்லலாம், நினைவில் வைத்துக்கொள்ளலாம், "
                "Windows apps/files-ஐ உங்கள் அனுமதியுடன் கட்டுப்படுத்தலாம்."
            )
        if language == "tanglish":
            return (
                "Naan Maya — unga full offline AI assistant. Chat, questions, "
                "memory, and Windows control (permission kudutha) ellam pannuven."
            )
        return (
            "I'm Maya — your offline AI assistant. I can chat, answer questions, "
            "remember things you tell me, and control Windows apps and files "
            "with your permission."
        )

    if _CAPABILITY_RE.search(text):
        if language == "tamil":
            return (
                "நான் இவை செய்ய முடியும்:\n"
                "• கேள்விகளுக்கு பதில் மற்றும் விளக்கம்\n"
                "• கணக்கு, தேதி, நேரம் — துல்லியமாக\n"
                "• நீங்கள் சொல்வதை நினைவில் வைத்துக்கொள்வது\n"
                "• Windows apps/files கட்டுப்பாடு (அனுமதியுடன்)\n"
                "• To-do, reminder, system status"
            )
        if language == "tanglish":
            return (
                "Naan ivai ellam panna mudiyum:\n"
                "• Questions-ku answer and explanation\n"
                "• Math, date, time — accurate-a\n"
                "• Neenga solla facts-ai remember pannuven\n"
                "• Windows apps/files control (permission kudutha)\n"
                "• To-do, reminder, system status"
            )
        return (
            "Here's what I can do:\n"
            "• Answer questions and explain concepts\n"
            "• Do math, dates, and time accurately\n"
            "• Remember facts you tell me\n"
            "• Control Windows apps and files (with permission)\n"
            "• Manage to-dos, reminders, and system status"
        )

    return None


def resolve_skill(text: str, language: str = "english") -> tuple[str, str] | None:
    """Try all deterministic skills. Returns ``(answer, skill_name)``."""
    answer = try_greeting(text, language)
    if answer:
        return answer, "greeting"

    answer = try_math(text)
    if answer:
        return answer, "math"

    answer = try_datetime(text, language)
    if answer:
        return answer, "datetime"

    answer = try_identity(text, language)
    if answer:
        return answer, "identity"

    return None
