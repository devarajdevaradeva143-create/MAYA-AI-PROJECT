"""Emotional Intelligence (EQ) engine — tone detection + style directive."""

import re
from dataclasses import dataclass


@dataclass
class ToneResult:
    tone: str
    directive: str


class EQEngine:
    """Emotional Intelligence — detects tone and provides style directive."""

    # Tone keywords (English + Tamil script + Tanglish)
    TONE_PATTERNS = {
        "sad": [
            r"\b(sad|depressed|unhappy|down|blue|heartbroken|grief|sorrow|lonely|hurt)\b",
            r"\b(dukkham|manasu kashtam|manasu sari illa|azhudhu|azhuga|romba kastam)\b",
            r"(சோகம்|கவலை|அழுகை|மனசு சரி இல்லை|கஷ்டம்)",
        ],
        "stressed": [
            r"\b(stressed|overwhelmed|anxious|worried|tense|pressure|burnout|panic)\b",
            r"\b(tension|bayam|padapada|neram illa|romba pressure)\b",
            r"(பயம்|டென்ஷன்|அழுத்தம்)",
        ],
        "angry": [
            r"\b(angry|furious|mad|irritated|annoyed|frustrated|rage|hate)\b",
            r"\b(kobam|kopam|erichal|kadupethu|veri|pichu)\b",
            r"(கோபம்|எரிச்சல்|கடுப்பு)",
        ],
        "tired": [
            r"\b(tired|exhausted|drained|weary|fatigue|sleepy|burnt out|no energy)\b",
            r"\b(thookam|sorvu|romba tired|vela panni tired|soukiyam illa)\b",
            r"(தூக்கம்|சோர்வு|களைப்பு)",
        ],
        "happy": [
            r"\b(happy|joy|excited|great|wonderful|amazing|delighted|pleased|grateful)\b",
            r"\b(santhosham|magizhchi|semma|super|nalla irukku)\b",
            r"(சந்தோஷம்|மகிழ்ச்சி|நல்லா இருக்கு)",
        ],
        "confused": [
            r"\b(confused|lost|unsure|uncertain|puzzled|don't understand|no clue|stuck)\b",
            r"\b(puriyala|theriyala|enna solla|thiruthi)\b",
            r"(புரியல|தெரியல|குழப்பம்)",
        ],
    }

    #: Extra signals that do not need a keyword. "!!" is intentionally absent:
    #: excitement uses the same punctuation as shouting.
    PUNCTUATION_HINTS = {
        "confused": re.compile(r"\?{2,}"),
    }

    # Directive templates per tone
    DIRECTIVES = {
        "sad": "The user seems sad. Respond with gentle warmth and empathy. Be supportive without being overly dramatic. Offer practical help if appropriate.",
        "stressed": "The user seems stressed. Respond calmly and reassuringly. Keep responses concise. Offer to help break things down or prioritize.",
        "angry": "The user seems angry or frustrated. Stay calm and respectful. Acknowledge the frustration. Focus on solutions, not excuses.",
        "tired": "The user seems tired. Be gentle and concise. Don't overload with information. Offer to simplify or continue later.",
        "happy": "The user seems happy. Match the positive energy naturally. Be warm and engaging.",
        "confused": "The user seems confused. Be patient and clear. Break things down step by step. Avoid jargon.",
        "neutral": "",
    }

    def analyze(self, text: str) -> ToneResult:
        """Analyze tone of text and return tone + directive."""
        text_lower = text.lower()
        scores: dict[str, int] = {}

        for tone, patterns in self.TONE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
                score += matches
            if score > 0:
                scores[tone] = score

        # Punctuation signals count as a weak vote, never override strong words.
        for tone, pattern in self.PUNCTUATION_HINTS.items():
            if pattern.search(text):
                scores[tone] = scores.get(tone, 0) + 1

        # Exclamation marks after a happy word mean excitement, not anger.
        if "happy" in scores and not any(
            word in text_lower for word in ("angry", "furious", "mad", "kobam", "kopam", "erichal")
        ):
            scores.pop("angry", None)

        if not scores:
            return ToneResult(tone="neutral", directive=self.DIRECTIVES["neutral"])

        # Get highest scoring tone; ties resolve in declaration order.
        top_tone = max(scores, key=lambda tone: scores[tone])
        return ToneResult(tone=top_tone, directive=self.DIRECTIVES.get(top_tone, ""))

    def get_directive(self, tone: str) -> str:
        """Get directive for a known tone."""
        return self.DIRECTIVES.get(tone, "")
