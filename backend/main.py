"""
main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI backend for Interrogation Room AI.

Endpoints:
  GET  /ping              — health check
  POST /session/init      — start a session, get personality + opening line
  POST /chat              — main turn endpoint (multi-agent + CIDS scoring)
  POST /choices           — generate 5 AI-powered Choice Mode options
  POST /chat/legacy       — simple single-agent endpoint (backward compat)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
import time

from agents import (
    ask_ollama, build_system_prompt, get_personality,
    generate_choice_options,
)
from judge import (
    check_win, score_session, get_judge_trigger,
    explain_verdict, check_session_limits,
    SESSION_TIME_LIMIT_SECONDS, SESSION_ROUND_LIMIT,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ══════════════════════════════════════════════════════════════════════════════

class Message(BaseModel):
    role:    str
    content: str


class ChatRequest(BaseModel):
    user_role:     str
    user_message:  str
    history:       List[Message]
    case_id:       Optional[str]        = "CASE-0047"
    case_title:    Optional[str]        = "Corporate Espionage — GovTech Industries"
    personality:   Optional[dict]       = None
    session_start_ts:  Optional[float]        = None   # unix timestamp of session start
    rounds_played:     Optional[int]          = 0
    score_history:     Optional[List[float]]  = []     # interrogator score per round


class ChatResponse(BaseModel):
    replies:             List[Message]
    status:              str
    scores:              dict
    contradiction_found: bool
    judge_spoke:         bool
    algo_breakdown:      dict
    session_limits:      dict
    forced_verdict:      Optional[dict] = None


class SessionInitResponse(BaseModel):
    personality:        dict
    opening_line:       str
    opening_role:       str
    session_start_ts:   float
    time_limit_seconds: int
    round_limit:        int


# ── Choice Mode models ────────────────────────────────────────────────────────

class ChoiceRequest(BaseModel):
    """
    Sent by the frontend each turn when the player is in Choice Mode.
    The backend uses conversation history + live scores to generate
    5 contextually accurate options.
    """
    user_role:      str
    case_title:     Optional[str]  = "Unknown Case"
    history:        List[Message]
    int_score:      Optional[float] = 0.0
    sus_score:      Optional[float] = 70.0
    def_score:      Optional[float] = 20.0
    rounds_played:  Optional[int]   = 1


class ChoiceOption(BaseModel):
    text:    str     # the dialogue text shown to the player
    quality: str     # "best" | "decent" | "weak" | "damaging" — hidden during selection


class ChoiceResponse(BaseModel):
    options: List[ChoiceOption]   # always exactly 5, shuffled


class LegacyRequest(BaseModel):
    role:    str
    message: str
    history: str


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def history_to_text(history: List[Message]) -> str:
    """Convert last 14 messages to the ROLE: text format Ollama expects."""
    return "\n".join(
        f"{m.role.upper()}: {m.content}" for m in history[-14:]
    )


def should_lawyer_respond(last_msg: str) -> bool:
    triggers = [
        "did you", "were you", "why did", "admit", "confess",
        "evidence", "prove", "lied", "lying", "contradict", "you said",
    ]
    return any(w in last_msg.lower() for w in triggers)


def should_judge_respond(history: List[Message], last_msg: str) -> bool:
    if get_judge_trigger(" ".join(m.content for m in history), last_msg):
        return True
    return len(history) > 0 and len(history) % 5 == 0


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.post("/session/init", response_model=SessionInitResponse)
def init_session(
    case_title: str = "Corporate Espionage",
    user_role:  str = "interrogator",
):
    """
    Called once at session start.
    Returns personality sliders, AI opening line, and session start timestamp.
    The client must store session_start_ts and send it back with every /chat call.
    """
    personality = get_personality()

    if user_role == "interrogator":
        opening_role = "suspect"
        cue = (
            f"You are seated alone in the interrogation room. The detective has not entered yet. "
            f"Show your state of mind in one short sentence. Case: {case_title}"
        )
    else:
        opening_role = "interrogator"
        cue = (
            f"You enter the interrogation room. The suspect is seated across the table. "
            f"Open with your first calculated question. Case: {case_title}"
        )

    system_prompt = build_system_prompt(opening_role, personality, case_title)
    opening_line  = ask_ollama(system_prompt, cue, opening_role)

    return SessionInitResponse(
        personality=personality,
        opening_line=opening_line,
        opening_role=opening_role,
        session_start_ts=time.time(),
        time_limit_seconds=SESSION_TIME_LIMIT_SECONDS,
        round_limit=SESSION_ROUND_LIMIT,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Main turn endpoint. Orchestrates 1–3 AI agents per turn.
    Runs CIDS scoring after every turn.
    Checks session time limit, round limit, and stalemate each turn.
    Returns forced_verdict if any limit is hit.
    """
    personality     = req.personality or get_personality()
    running_context = history_to_text(req.history) + f"\n{req.user_role.upper()}: {req.user_message}"
    replies: List[Message] = []
    judge_spoke = False

    # ── Elapsed time ──────────────────────────────────────────────────────────
    session_start = req.session_start_ts or time.time()
    elapsed       = int(time.time() - session_start)
    rounds_played = (req.rounds_played or 0) + 1
    score_history = list(req.score_history or [])

    # ── Determine AI response order ───────────────────────────────────────────
    if req.user_role == "interrogator":
        order = ["suspect"]
        if should_lawyer_respond(req.user_message):                   order.append("lawyer")
        if should_judge_respond(req.history, req.user_message):       order.append("judge")
    elif req.user_role == "lawyer":
        order = ["interrogator", "suspect"]
        if should_judge_respond(req.history, req.user_message):       order.append("judge")
    elif req.user_role == "suspect":
        order = ["interrogator"]
        if should_lawyer_respond(req.user_message):                   order.append("lawyer")
        if should_judge_respond(req.history, req.user_message):       order.append("judge")
    else:
        order = ["suspect"]

    # ── Call Ollama for each AI role ──────────────────────────────────────────
    for role in order:
        reply_text = ask_ollama(
            build_system_prompt(role, personality, req.case_title),
            running_context,
            role,
        )
        replies.append(Message(role=role, content=reply_text))
        running_context += f"\n{role.upper()}: {reply_text}"
        if role == "judge":
            judge_spoke = True

    # ── CIDS scoring ──────────────────────────────────────────────────────────
    result = score_session(running_context)

    int_score = result["interrogator_score"]
    sus_score = result["suspect_score"]
    def_score = result["defense_score"]

    score_history.append(int_score)

    # ── Session limit check ───────────────────────────────────────────────────
    limits = check_session_limits(
        rounds_played      = rounds_played,
        elapsed_seconds    = elapsed,
        score_history      = score_history,
        interrogator_score = int_score,
        suspect_score      = sus_score,
        defense_score      = def_score,
    )

    status = result["status"]
    forced = None

    if limits["limit_hit"]:
        forced = limits["verdict"]
        status = forced["status"]
        if not judge_spoke:
            verdict_line = (
                f"[TIME/ROUND LIMIT] {forced['summary']} "
                f"Final scores — Interrogator: {int_score}, Suspect: {sus_score}, Defense: {def_score}."
            )
            replies.append(Message(role="judge", content=verdict_line))
            judge_spoke = True

    elif limits.get("warning") and not judge_spoke:
        replies.append(Message(
            role="judge",
            content=f"⚠ {limits['warning']}",
        ))
        judge_spoke = True

    return ChatResponse(
        replies=replies,
        status=status,
        scores={
            "interrogator": int_score,
            "suspect":      sus_score,
            "defense":      def_score,
        },
        contradiction_found=result["contradictions"] > 0,
        judge_spoke=judge_spoke,
        algo_breakdown={
            "lia": result["lia"],
            "cde": result["cde"],
            "prs": result["prs"],
            "verdict_explanation": explain_verdict(result),
        },
        session_limits={
            "time_remaining":   limits["time_remaining"],
            "rounds_remaining": limits["rounds_remaining"],
            "warning":          limits.get("warning"),
            "limit_hit":        limits["limit_hit"],
            "reason":           limits.get("reason"),
            "elapsed_seconds":  elapsed,
            "rounds_played":    rounds_played,
        },
        forced_verdict=forced,
    )


@app.post("/choices", response_model=ChoiceResponse)
def get_choices(req: ChoiceRequest):
    """
    Choice Mode endpoint.

    Called by the frontend each turn when the player is in Choice Mode.
    Uses the current conversation history and live CIDS scores to generate
    5 contextually calibrated dialogue options via Ollama.

    Option composition (shuffled before returning):
      1 × BEST     — strongest move given current game state
      1 × DECENT   — reasonable but not optimal
      1 × WEAK     — plausible but low scoring value
      2 × DAMAGING — sound convincing but hurt the player's score

    Quality labels are included in the response but the frontend
    hides them during selection — they are only revealed after the
    player has chosen and sent their message.

    Falls back to static templates if Ollama is unavailable.
    """
    conversation = history_to_text(req.history)

    raw_options = generate_choice_options(
        role          = req.user_role,
        case_title    = req.case_title,
        conversation  = conversation,
        int_score     = req.int_score,
        sus_score     = req.sus_score,
        def_score     = req.def_score,
        rounds_played = req.rounds_played,
    )

    return ChoiceResponse(
        options=[ChoiceOption(text=o["text"], quality=o["quality"]) for o in raw_options]
    )


@app.post("/chat/legacy")
def chat_legacy(req: LegacyRequest):
    """Simple single-agent fallback — kept for backward compatibility."""
    system_prompt = (
        f"You are an AI in an interrogation game.\n"
        f"Role: {req.role}\n"
        f"Rules:\n- Stay in character\n- Be realistic\n- No AI mention"
    )
    conversation = req.history.strip() + f"\n{req.role.upper()}: {req.message}\nAI:"
    return {
        "reply":  ask_ollama(system_prompt, conversation),
        "status": check_win(conversation),
    }


# ── Static files — MUST be last ───────────────────────────────────────────────
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
