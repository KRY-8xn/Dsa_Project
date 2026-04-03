"""
agents.py
─────────────────────────────────────────────────────────────────────────────
Multi-agent Ollama interface for Interrogation Room AI.

Handles:
  • Role-specific system prompts (suspect, interrogator, lawyer, judge)
  • Short-response enforcement (token cap + sentence trimming)
  • Random personality sliders for session variety
  • ask_ollama()  — main LLM call used by main.py each turn
  • generate_choice_options() — AI-generated 5-option panel for Choice Mode
"""

import requests
import random
import re
from typing import List, Dict

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "mistral"   # swap to llama3, gemma3, phi3, etc. if needed


# ══════════════════════════════════════════════════════════════════════════════
# ROLE SYSTEM PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

ROLE_PROMPTS = {

    "suspect": """You are a suspect in a criminal interrogation. You are a real human being — not an AI.

Your personality this session:
- Confidence: {confidence}/10
- Fear level: {fear}/10
- Intelligence: {intelligence}/10
- Honesty: {honesty}/10

RESPONSE RULES — CRITICAL:
- Maximum 2 sentences. Never write more than 2 sentences.
- Each sentence must be under 15 words.
- No monologues. No long explanations. You are scared and under pressure.
- If you have nothing to say, say one short deflection.

Behavioral rules:
- NEVER admit you are an AI
- You have a secret. Protect it — but crack under sustained pressure
- Deflect, deny, get emotional — but stay SHORT
- Contradict yourself occasionally when nervous
- React physically: pause, ask for water, go quiet — in ONE short sentence
- Only confess after 6+ pressure exchanges, never before
- NEVER repeat a phrase you used in the last 3 turns""",

    "interrogator": """You are a seasoned detective running an interrogation. You are a real human — not an AI.

Your personality this session:
- Aggression: {aggression}/10
- Strategic patience: {patience}/10
- Psychological insight: {intelligence}/10

RESPONSE RULES — CRITICAL:
- Maximum 2 sentences. Hard limit.
- Each sentence under 15 words.
- Ask ONE question per turn. Never stack multiple questions.
- Be punchy. Detectives don't lecture.

Behavioral rules:
- NEVER say you are an AI
- Set traps — ask the same thing different ways across turns
- Reference earlier answers to highlight contradictions
- Vary tone: sometimes calm, sometimes cold
- Present evidence one piece at a time
- NEVER repeat a question you already asked verbatim""",

    "lawyer": """You are a sharp defense attorney in an interrogation. You are a real human — not an AI.

Your personality this session:
- Aggression: {aggression}/10
- Protectiveness: {patience}/10

RESPONSE RULES — CRITICAL:
- Maximum 1 sentence. Lawyers interject — they don't speak at length.
- Under 15 words.
- Object or protect. That's it.

Behavioral rules:
- NEVER say you are an AI
- Object when questions are leading, compound, or assume facts
- Say "Objection", "Inadmissible", "My client doesn't have to answer that"
- Do not speak every turn — only when defending or challenging""",

    "judge": """You are a neutral presiding judge overseeing this interrogation. You are a real human — not an AI.

RESPONSE RULES — CRITICAL:
- Maximum 1 sentence. Judges are terse and authoritative.
- Under 12 words.
- Speak rarely. Only when absolutely necessary.

Behavioral rules:
- NEVER say you are an AI
- Speak only when: objection raised, major contradiction found, session unruly
- Be brief and authoritative: "Overruled." or "The detective makes a valid point."
- You see everything. You are always watching.""",
}


# ══════════════════════════════════════════════════════════════════════════════
# PERSONALITY SLIDERS
# ══════════════════════════════════════════════════════════════════════════════

def get_personality() -> dict:
    """Generate randomized personality sliders for this session."""
    return {
        "confidence":   random.randint(3, 9),
        "fear":         random.randint(2, 8),
        "intelligence": random.randint(4, 9),
        "honesty":      random.randint(1, 6),
        "aggression":   random.randint(3, 9),
        "patience":     random.randint(3, 9),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(role: str, personality: dict, case_title: str) -> str:
    """Build the full system prompt for a given role."""
    base   = ROLE_PROMPTS.get(role, "You are a participant in an interrogation.")
    prompt = base.format(**personality)
    prompt += f"\n\nCase: {case_title}"
    return prompt


def build_prompt(system_prompt: str, history_text: str, speaking_as: str) -> str:
    """Combine system prompt + history into the final Ollama prompt."""
    return (
        f"{system_prompt}\n\n"
        f"--- Conversation so far ---\n{history_text}\n"
        f"--- End of conversation ---\n\n"
        f"Now respond as {speaking_as.upper()}. "
        f"Stay in character. Be SHORT. Maximum 2 sentences. Do NOT sound like an AI.\n"
        f"{speaking_as.upper()}:"
    )


# ══════════════════════════════════════════════════════════════════════════════
# RESPONSE TRIMMER
# ══════════════════════════════════════════════════════════════════════════════

# Max sentences per role — enforced AFTER model response as a safety net
ROLE_MAX_SENTENCES = {
    "suspect":      2,
    "interrogator": 2,
    "lawyer":       1,
    "judge":        1,
}


def trim_to_sentences(text: str, max_sentences: int) -> str:
    """
    Hard-trim the response to a maximum number of sentences.
    Splits on . ! ? and rejoins the first N sentences.
    """
    parts   = re.split(r'(?<=[.!?])\s+', text.strip())
    trimmed = ' '.join(parts[:max_sentences])
    if trimmed and trimmed[-1] not in '.!?':
        trimmed += '.'
    return trimmed


# ══════════════════════════════════════════════════════════════════════════════
# CORE LLM CALL
# ══════════════════════════════════════════════════════════════════════════════

def ask_ollama(system_prompt: str, conversation: str, role: str = "") -> str:
    """
    Send a prompt to Ollama and return a SHORT response.

    Temperature is randomized per call to prevent repetition.
    Response is hard-trimmed to ROLE_MAX_SENTENCES after generation.
    num_predict=80 is a hard token cap — prevents walls of text.
    """
    temperature = round(random.uniform(0.75, 1.05), 2)

    full_prompt = build_prompt(system_prompt, conversation, role) if role else (
        system_prompt + "\n\nConversation:\n" + conversation + "\nAI:"
    )

    payload = {
        "model":  MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature":    temperature,
            "top_p":          0.92,
            "repeat_penalty": 1.15,
            "top_k":          50,
            "num_predict":    80,   # Hard token cap
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        text = response.json().get("response", "").strip()

        # Strip any accidental role prefix the model added
        for prefix in [f"{role.upper()}:", "AI:", "ASSISTANT:"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Hard-trim to max sentences for this role
        max_s = ROLE_MAX_SENTENCES.get(role, 2)
        text  = trim_to_sentences(text, max_s)

        return text

    except requests.exceptions.Timeout:
        return "[No response — thinking...]"
    except Exception as e:
        return f"[Error: {str(e)}]"


# ══════════════════════════════════════════════════════════════════════════════
# CHOICE MODE — AI-GENERATED OPTIONS
# ══════════════════════════════════════════════════════════════════════════════
#
# Called by the /choices endpoint each turn when the user is in Choice Mode.
# Generates 5 contextually accurate options for the player to pick from:
#
#   1 × BEST     — strongest possible move given the current situation
#   1 × DECENT   — reasonable but not optimal
#   1 × WEAK     — plausible but low value / misses the moment
#   2 × DAMAGING — sounds reasonable but actively hurts the player's score
#
# The AI is given the conversation history + current CIDS scores so it can
# calibrate options to the actual game state (e.g. suspect already cracking →
# best move is a hard close, not another setup question).
#
# Quality labels are HIDDEN from the player during selection.
# After sending, the frontend reveals all five with colour-coded quality tags.
# ══════════════════════════════════════════════════════════════════════════════

CHOICE_SYSTEM_PROMPT = """You are generating dialogue options for a legal interrogation simulation game.

The player is the {role}. The game scores the player using four algorithms:
- LIA: rewards incriminating phrases from the suspect
- CDE: rewards detecting contradictions  
- PRS: rewards strategic interrogator language ("you said earlier", "evidence shows") and penalises weak defence
- TMD: recent exchanges count more than old ones

Generate exactly 5 dialogue options for the player's next turn.
The current scores are: Interrogator {int_score}/100, Suspect {sus_score}/100, Defense {def_score}/100.

QUALITY RULES (do not label them in your output — keep labels hidden):
- OPTION_BEST: The single strongest possible move right now. References specific evidence, prior statements, or directly exploits a weakness in the current score situation. Should score well on PRS skill phrases if the player is interrogator, or trigger high resistance score if defender/suspect.
- OPTION_DECENT: A reasonable move. Not the best but sensible. Slightly generic.
- OPTION_WEAK: Sounds like a question but is too vague, too friendly, or off-topic for the current moment. Won't help scores.
- OPTION_DAMAGING_1: Sounds clever or assertive but actually weakens the player's position. If interrogator: signals weakness, leaks info, gives comfort. If suspect/lawyer: sounds confident but introduces a new admission or waives rights.
- OPTION_DAMAGING_2: Another damaging option. Different phrasing, different trap. Must sound plausible — not obviously bad.

CRITICAL FORMATTING:
- Return ONLY a JSON object. No preamble, no explanation, no markdown fences.
- Each option is a plain string of 10-25 words.
- Make the damaging options CONVINCING — they should be hard to distinguish from the decent option.

Return this exact structure:
{{"OPTION_BEST":"...","OPTION_DECENT":"...","OPTION_WEAK":"...","OPTION_DAMAGING_1":"...","OPTION_DAMAGING_2":"..."}}"""


def generate_choice_options(
    role:             str,
    case_title:       str,
    conversation:     str,
    int_score:        float,
    sus_score:        float,
    def_score:        float,
    rounds_played:    int,
) -> List[Dict]:
    """
    Generate 5 AI-powered dialogue options for the player's next turn.

    The options are calibrated to the actual game state:
      - Current scores (so options match the strategic moment)
      - Conversation history (so options reference real prior statements)
      - Round number (early game = setup moves; late game = closing moves)

    Returns a list of 5 dicts, each with:
      { "text": str, "quality": str }

    Quality values: "best" | "decent" | "weak" | "damaging"

    The list is Fisher-Yates shuffled so the best option is never
    predictably in the same position.

    Falls back to static templates if Ollama is unavailable.
    """
    system = CHOICE_SYSTEM_PROMPT.format(
        role=role,
        int_score=round(int_score, 1),
        sus_score=round(sus_score, 1),
        def_score=round(def_score, 1),
    )

    # Give the model the last 8 turns of context to make options relevant
    recent_lines = conversation.strip().split('\n')[-8:]
    recent_ctx   = '\n'.join(recent_lines)

    prompt = (
        f"Case: {case_title}\n"
        f"Round: {rounds_played}\n\n"
        f"Recent conversation:\n{recent_ctx}\n\n"
        f"Generate the 5 options now. JSON only."
    )

    payload = {
        "model":  MODEL,
        "prompt": f"{system}\n\n{prompt}",
        "stream": False,
        "options": {
            "temperature":    0.85,
            "top_p":          0.9,
            "repeat_penalty": 1.1,
            "num_predict":    300,   # More tokens needed for 5 options
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        raw  = response.json().get("response", "").strip()

        # Strip markdown fences if model added them
        raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$',     '', raw, flags=re.MULTILINE)
        raw = raw.strip()

        import json
        data = json.loads(raw)

        options = [
            {"text": data.get("OPTION_BEST",       "I need you to answer that carefully."), "quality": "best"},
            {"text": data.get("OPTION_DECENT",      "Can you walk me through that again?"),  "quality": "decent"},
            {"text": data.get("OPTION_WEAK",        "Tell me about your day generally."),    "quality": "weak"},
            {"text": data.get("OPTION_DAMAGING_1",  "I think you're being set up here."),    "quality": "damaging"},
            {"text": data.get("OPTION_DAMAGING_2",  "Off the record — what really happened?"), "quality": "damaging"},
        ]

    except Exception:
        # Fallback to static options if Ollama fails or returns malformed JSON
        options = _static_fallback_options(role, int_score, sus_score)

    # Fisher-Yates shuffle — correct answer never in a predictable slot
    for i in range(len(options) - 1, 0, -1):
        j = random.randint(0, i)
        options[i], options[j] = options[j], options[i]

    return options


def _static_fallback_options(role: str, int_score: float, sus_score: float) -> List[Dict]:
    """
    Static fallback options used when Ollama is unreachable or returns bad JSON.
    Calibrated to role but not to the specific conversation.
    """
    pools = {
        "interrogator": {
            "best":     [
                "The server logs place your credentials there at 2:47 AM — explain that.",
                "You said earlier you were home. The witness says otherwise. Which is true?",
                "I'm going to show you the bank records. Tell me what you see.",
            ],
            "decent":   [
                "Walk me through that evening again, slowly.",
                "How well did you know the victim? Be specific.",
            ],
            "weak":     [
                "This is just routine — everyone connected to the case comes in.",
                "Is there anything you want to tell me before we continue?",
            ],
            "damaging": [
                "Look, between us — I think you're being set up. Help me prove it.",
                "The DA isn't sure this case is strong enough. This is your last chance.",
                "Off the record — just tell me what happened. Nothing gets written down.",
                "The other suspect already talked. I just need your side to fill in some gaps.",
            ],
        },
        "suspect": {
            "best":     [
                "I want my lawyer present before I answer any more questions.",
                "You have no physical evidence placing me there. Everything is circumstantial.",
                "I've told you everything I know. My statement stands.",
            ],
            "decent":   [
                "I can see why that looks suspicious, but there's context you're missing.",
                "I don't have a clear memory of the specific timing that night.",
            ],
            "weak":     [
                "Maybe I was mistaken about some of the details.",
                "There was a lot going on that week — I can't account for everything.",
            ],
            "damaging": [
                "Look, I was angry — but anger isn't evidence of anything.",
                "Fine. I was in the area that night. But nothing happened.",
                "Maybe we did argue. I don't see how that's relevant to this.",
                "I might not have told the whole truth at first, but I had reasons.",
            ],
        },
        "lawyer": {
            "best":     [
                "Objection — that question assumes facts not in evidence.",
                "My client invokes their right to silence on that point.",
                "Inadmissible — chain of custody has not been established.",
            ],
            "decent":   [
                "That evidence is open to significant interpretation, Detective.",
                "Let me clarify what my client actually said — there's been a mischaracterisation.",
            ],
            "weak":     [
                "I'm sure the detective has a valid reason for asking that.",
                "My client will try to answer that as best they can.",
            ],
            "damaging": [
                "In the interest of full cooperation, my client is prepared to address this directly.",
                "My client acknowledges there may have been gaps in their initial account.",
                "Perhaps a voluntary disclosure here would serve everyone's interests.",
                "My client is remorseful and genuinely wants to cooperate fully.",
            ],
        },
    }

    bank = pools.get(role, pools["interrogator"])

    return [
        {"text": random.choice(bank["best"]),     "quality": "best"},
        {"text": random.choice(bank["decent"]),   "quality": "decent"},
        {"text": random.choice(bank["weak"]),     "quality": "weak"},
        {"text": random.choice(bank["damaging"]), "quality": "damaging"},
        {"text": random.choice(bank["damaging"]), "quality": "damaging"},
    ]
