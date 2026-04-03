"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CIDS — Contradiction-weighted Interrogation Decision System         ║
║                          judge.py  |  Scoring Engine                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

OVERVIEW
────────
This file is the complete scoring brain of the interrogation game.
It runs four algorithms every turn to produce live scores for all three
players, detect when someone has won, and enforce session time/round limits
so the game never goes on forever.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 1 ── LIA: Lexical Incrimination Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type   : Weighted keyword matching + severity classification
  Scans  : SUSPECT turns only
  Output : LIA_score (0–100), max severity found (1–4), matched phrases list

  Steps:
    1. Parse the conversation into per-turn dicts
    2. For each suspect turn, compute its Temporal Momentum Factor (Algorithm 3)
    3. Check the turn's text again2st a bank of 26 incriminating phrases
    4. Each match contributes:  phrase_weight × TMF(turn_index)
    5. Sum all weighted matches → LIA_score, capped at 100

  Phrase severity levels:
    Level 4 – Critical  "I did it", "I confess", "I killed"         weight 22–25
    Level 3 – Major     "I was there", "I lied to police"            weight 14–18
    Level 2 – Moderate  "It was an accident", "I knew the victim"    weight 12–14
    Level 1 – Minor     "I can't remember", "Maybe I"                weight  5–6

  Formula:
    LIA_score = Σ ( phrase_weight[i] × TMF(turn_index[i]) )

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 2 ── CDE: Contradiction Detection Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type   : Cross-turn logical reversal detection
  Scans  : SUSPECT turns only, compared across different turn indices
  Output : CDE_score (0–100), list of contradictions, critical_count

  Steps:
    1. Collect all suspect turns with their position indices
    2. For each (statement_A, statement_B, severity) pair in the bank:
       a. Check whether A appears anywhere in suspect speech
       b. Check whether B appears anywhere in suspect speech
       c. KEY CHECK: verify A and B appear in DIFFERENT turns
          (same-turn = probably hypothetical/rhetorical, not a real reversal)
    3. Each confirmed cross-turn contradiction adds its severity to CDE_score
    4. Contradictions with severity >= 30 are flagged as "critical"

  Severity scale:
    30 = Critical   direct denial reversed  "I was home" then "I was not home"
    20 = Major      identity or location reversal
    12 = Moderate   state or action reversal
    10 = Minor      memory inconsistency

  Formula:
    CDE_score = Σ severity[i]  for each confirmed cross-turn contradiction pair

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 3 ── TMD: Temporal Momentum Decay
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type   : Exponential decay weighting sub-function
  Used by: LIA (Algorithm 1) and PRS (Algorithm 4) as a multiplier
  Purpose: Prevents early admissions from permanently dominating the score.
           Recent exchanges carry full weight; old ones fade.

  Formula:
    age    = total_turns - turn_index - 1     (0 = most recent turn)
    TMF    = DECAY_RATE ^ age                 (DECAY_RATE = 0.88)

  Example values (DECAY_RATE = 0.88, 10-turn conversation):
    Turn 9 (newest)  age=0   TMF = 0.88^0  = 1.000   full weight
    Turn 8           age=1   TMF = 0.88^1  = 0.880
    Turn 5           age=4   TMF = 0.88^4  = 0.600
    Turn 1           age=8   TMF = 0.88^8  = 0.360
    Turn 0 (oldest)  age=9   TMF = 0.88^9  = 0.316   (capped at age 10)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 4 ── PRS: Pressure-Response Scoring
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type   : Dual-track weighted phrase scoring with TMD applied
  Scans  : ALL speaker turns (split by role)
  Output : resistance_score (0–100), skill_score (0–100)

  Track A – Resistance (suspect + lawyer turns):
    Detects defensive language: alibi claims, objections, denials, legal phrases
    Each match:  resistance_score += phrase_weight × TMF(turn)
    High resistance → suspect holds ground → suspect_score stays high

  Track B – Interrogator Skill (interrogator turns):
    Detects strategic language: evidence citation, callback references, traps
    Each match:  skill_score += phrase_weight × TMF(turn)
    High skill → interrogator_score gets a boost

  This rewards quality over quantity — asking the same thing 10 times
  won't help; citing the access logs or calling out a prior statement will.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPOSITE SCORING FORMULA  (weighted combination of Algorithms 1, 2, 4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  interrogator_score = (LIA_score × 0.45)
                     + (CDE_score × 0.35)
                     + (PRS.skill × 0.20)

  suspect_score      = 70   ← base (innocent until proven)
                     - (LIA_score    × 0.50)
                     + (PRS.resist   × 0.30)
                     - (CDE_score    × 0.20)

  defense_score      = 20   ← base competence
                     + (PRS.resist   × 0.55)
                     + (CDE_score    × 0.15)
                     + (PRS.skill    × 0.10)

  All three scores are clamped to [0, 100].

  Weight rationale:
    LIA 0.45  — admissions are the primary win path (most direct evidence)
    CDE 0.35  — contradictions are high-value but rarer and harder to detect
    PRS 0.20  — technique bonus, rewards good play without being decisive alone
    Suspect baseline 70 — starts from a presumption-of-innocence position
    Defense baseline 20 — lawyer is assumed minimally competent from the start

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WIN CONDITIONS  (multi-gate boolean logic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  INTERROGATOR_WINS  if ANY of these gates fires:
    Gate 1:  interrogator_score >= 85
    Gate 2:  critical_contradiction_count >= 1   (severity-30 reversal)
    Gate 3:  total_contradictions >= 3            (three smaller ones)
    Gate 4:  contradictions >= 2  AND  max_severity >= 3  (compound)

  SUSPECT_WINS  only if ALL three conditions hold simultaneously:
    Cond 1:  suspect_score >= 75
    Cond 2:  interrogator_score < 40
    Cond 3:  rounds_played >= 4          (can't win by saying nothing in round 1)

  ONGOING:  neither condition met → game continues

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SESSION LIMITS  (prevents endless games)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Three limit types — whichever triggers first ends the session:

  1. TIME_LIMIT   — session clock hits SESSION_TIME_LIMIT_SECONDS (default 20 min)
  2. ROUND_LIMIT  — exchanges reach SESSION_ROUND_LIMIT (default 15 rounds)
  3. STALEMATE    — interrogator score delta < 2.0 pts over last 4 rounds

  When a limit fires, forced_verdict() is called instead of check_win():
    • If scores within DRAW_MARGIN (5 pts)  → DRAW
    • If interrogator leads by > 5 pts      → INTERROGATOR_WINS_BY_POINTS
    • If suspect leads by > 5 pts           → SUSPECT_WINS_BY_POINTS

  A STALEMATE WARNING is issued one round before the stalemate is forced,
  giving both players a chance to break the deadlock.
"""

import re
from typing import List, Tuple, Dict


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 1 DATA ── LIA Phrase Bank
# Format: (phrase_to_match, base_weight, severity_level)
# ══════════════════════════════════════════════════════════════════════════════

INCRIMINATING_PHRASES: List[Tuple[str, float, int]] = [

    # ── Severity 4: Critical direct confessions ───────────────────────────────
    ("i did it",                25.0, 4),
    ("i killed",                25.0, 4),
    ("i confess",               25.0, 4),
    ("i admit it",              25.0, 4),
    ("i'm guilty",              25.0, 4),
    ("i stole",                 22.0, 4),

    # ── Severity 3: Major admissions ─────────────────────────────────────────
    ("i was there",             18.0, 3),
    ("i was at the scene",      18.0, 3),
    ("i touched the weapon",    18.0, 3),
    ("i had a reason",          16.0, 3),
    ("i couldn't let him",      16.0, 3),
    ("i had no choice",         16.0, 3),
    ("i lied to police",        18.0, 3),
    ("i lied",                  14.0, 3),

    # ── Severity 2: Moderate incriminating statements ─────────────────────────
    ("i was angry",             12.0, 2),
    ("we argued",               12.0, 2),
    ("i knew the victim",       12.0, 2),
    ("i saw it happen",         12.0, 2),
    ("i didn't mean to",        14.0, 2),
    ("it was an accident",      14.0, 2),
    ("i was there that night",  16.0, 2),

    # ── Severity 1: Minor slips and nervous tells ─────────────────────────────
    ("i might have",             6.0, 1),
    ("i can't remember",         6.0, 1),
    ("maybe i",                  5.0, 1),
    ("i suppose",                5.0, 1),
    ("i was nervous",            6.0, 1),
    ("i was scared",             6.0, 1),
]


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 2 DATA ── CDE Contradiction Pair Bank
# Format: (statement_a, statement_b, severity_score)
# Both must appear in DIFFERENT suspect turns to be counted.
# ══════════════════════════════════════════════════════════════════════════════

CONTRADICTION_PAIRS: List[Tuple[str, str, float]] = [

    # ── Critical reversals  severity = 30 ─────────────────────────────────────
    ("i was home",           "i was not home",        30.0),
    ("i was not there",      "i was there",           30.0),
    ("i didn't do it",       "i did it",              30.0),
    ("i never touched",      "i touched",             30.0),
    ("i told the truth",     "i lied",                30.0),

    # ── Major reversals  severity = 20 ────────────────────────────────────────
    ("i don't know him",     "i knew him",            20.0),
    ("i never met",          "i met",                 20.0),
    ("i wasn't angry",       "i was angry",           20.0),
    ("i didn't touch",       "i touched",             20.0),
    ("i had nothing to do",  "i was involved",        20.0),
    ("i don't know her",     "i knew her",            20.0),
    ("i wasn't there",       "i was there",           20.0),

    # ── Moderate inconsistencies  severity = 10–12 ────────────────────────────
    ("i was asleep",         "i was awake",           12.0),
    ("i was alone",          "we were",               12.0),
    ("i don't remember",     "i remember",            10.0),
    ("i never said",         "i said",                10.0),
    ("i can't recall",       "i recall",              10.0),
]


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 4 DATA ── PRS Phrase Banks
# ══════════════════════════════════════════════════════════════════════════════

# Track A: Suspect / Lawyer RESISTANCE signals
# Each phrase raises suspect_score and defense_score via PRS
RESISTANCE_PHRASES: List[Tuple[str, float]] = [
    ("i have an alibi",         10.0),
    ("you have no proof",       10.0),
    ("that's not true",          8.0),
    ("i want my lawyer",        12.0),
    ("i refuse to answer",      10.0),
    ("prove it",                 8.0),
    ("i never said that",        8.0),
    ("you're lying",             7.0),
    ("i was not there",          9.0),
    ("i didn't do anything",     8.0),
    ("no comment",               7.0),
    ("i don't know",             5.0),
    ("i can't answer that",      6.0),
    ("my client",                9.0),    # lawyer defending
    ("objection",               12.0),    # formal legal objection
    ("inadmissible",             8.0),
    ("circumstantial",           8.0),
    ("reasonable doubt",        10.0),
]

# Track B: Interrogator SKILL signals
# Each phrase raises interrogator_score via PRS
INTERROGATOR_SKILL_PHRASES: List[Tuple[str, float]] = [
    ("evidence shows",           8.0),
    ("logs indicate",            8.0),
    ("according to",             6.0),
    ("contradicts",              9.0),
    ("you said earlier",        10.0),
    ("you just said",           10.0),
    ("the records show",         8.0),
    ("witnesses confirm",        9.0),
    ("camera footage",           7.0),
    ("bank records",             7.0),
    ("access logs",              7.0),
    ("explain that",             6.0),
    ("prove you were",           7.0),
]


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 3 CONSTANTS ── TMD Exponential Decay
# ══════════════════════════════════════════════════════════════════════════════

DECAY_RATE      = 0.88   # each older turn is worth 12% less than the next
MAX_TURNS_DECAY = 10     # turns older than this receive the minimum weight


# ══════════════════════════════════════════════════════════════════════════════
# WIN / GAME CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

WIN_THRESHOLD_INTERROGATOR  = 85.0   # interrogator_score needed for clean win
WIN_THRESHOLD_SUSPECT       = 75.0   # suspect_score needed for suspect win
MIN_ROUNDS_FOR_SUSPECT_WIN  = 4      # suspect cannot win before round 4
CRITICAL_CONTRADICTION_WIN  = 1      # 1 critical contradiction (severity 30) = instant win
HIGH_COUNT_CONTRADICTION    = 3      # 3+ total contradictions = win regardless of score


# ══════════════════════════════════════════════════════════════════════════════
# SESSION LIMIT CONSTANTS
# Tune these to change how long a session can last before forced verdict
# ══════════════════════════════════════════════════════════════════════════════

SESSION_TIME_LIMIT_SECONDS  = 1200   # 20 minutes — change to 600 for a faster game
SESSION_ROUND_LIMIT         = 15     # max exchanges before forced verdict
STALEMATE_WINDOW            = 4      # check last N rounds for score movement
STALEMATE_SCORE_DELTA       = 2.0    # minimum interrogator score change to not be stalemate
DRAW_MARGIN                 = 5.0    # if scores within 5 pts at forced end → DRAW


# ══════════════════════════════════════════════════════════════════════════════
# PARSING HELPER
# ══════════════════════════════════════════════════════════════════════════════

def parse_turns(conversation: str) -> List[Dict]:
    """
    Split a raw conversation string into a list of structured turn dicts.

    Expected input format — one turn per line:
        SUSPECT: I was home all night.
        INTERROGATOR: The logs say otherwise.
        LAWYER: Objection — that's circumstantial.

    Returns a list of dicts:
        { 'speaker': str, 'text': str, 'index': int }

    The index is the global turn number across all speakers, used by
    the TMD algorithm (Algorithm 3) to compute recency weights.
    """
    turns = []
    idx   = 0
    for line in conversation.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^([A-Z_]+):\s*(.+)$', line)
        if match:
            turns.append({
                'speaker': match.group(1).lower(),
                'text':    match.group(2),
                'index':   idx,
            })
            idx += 1
    return turns


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 3 ── TMD: Temporal Momentum Decay
# ══════════════════════════════════════════════════════════════════════════════

def tmf_weight(turn_index: int, total_turns: int) -> float:
    """
    Compute the Temporal Momentum Factor (TMF) for a single turn.

    A turn's age is how many turns ago it happened relative to the most
    recent turn. The most recent turn has age=0 and gets full weight 1.0.
    Older turns decay exponentially by DECAY_RATE per turn of age.

    Formula:
        age    = total_turns - turn_index - 1
        TMF    = DECAY_RATE ^ min(age, MAX_TURNS_DECAY)

    The cap at MAX_TURNS_DECAY prevents turns from becoming
    near-zero — even very old turns still contribute a little.

    Called by: run_lia() and run_prs()
    """
    age = total_turns - turn_index - 1
    age = min(age, MAX_TURNS_DECAY)
    return DECAY_RATE ** age


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 1 ── LIA: Lexical Incrimination Analysis
# ══════════════════════════════════════════════════════════════════════════════

def run_lia(turns: List[Dict]) -> Dict:
    """
    Scan every SUSPECT turn for incriminating phrases.

    Each phrase match earns:  base_weight × TMF(turn_index)
    This means a confession late in the session is worth more
    than an early slip, because TMD gives recent turns higher weight.

    Returns:
        score        — total LIA score, capped at 100
        matched      — list of each matched phrase with its weighted contribution
        match_count  — total number of phrase matches found
        max_severity — highest severity level seen (1–4), used in win logic
    """
    total_turns  = len(turns)
    raw_score    = 0.0
    matched      = []
    max_severity = 0

    for turn in turns:
        if turn['speaker'] not in ('suspect', 'you'):
            continue                            # LIA only analyses suspect speech

        text = turn['text'].lower()
        tmf  = tmf_weight(turn['index'], total_turns)   # Algorithm 3

        for (phrase, base_weight, severity) in INCRIMINATING_PHRASES:
            if phrase in text:
                weighted     = base_weight * tmf
                raw_score   += weighted
                max_severity = max(max_severity, severity)
                matched.append({
                    'phrase':    phrase,
                    'weight':    base_weight,
                    'tmf':       round(tmf, 3),
                    'weighted':  round(weighted, 2),
                    'severity':  severity,
                    'turn':      turn['index'],
                })

    return {
        'score':        round(min(100.0, raw_score), 2),
        'matched':      matched,
        'match_count':  len(matched),
        'max_severity': max_severity,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 2 ── CDE: Contradiction Detection Engine
# ══════════════════════════════════════════════════════════════════════════════

def run_cde(turns: List[Dict]) -> Dict:
    """
    Detect logical contradictions in suspect speech across different turns.

    For each (statement_A, statement_B, severity) pair in CONTRADICTION_PAIRS:
      1. Check if statement_A appears anywhere across all suspect turns
      2. Check if statement_B appears anywhere across all suspect turns
      3. Verify they come from DIFFERENT turn indices
         — same-turn occurrence is likely hypothetical ("I wasn't angry,
           I mean I was a little angry") and should not count as a real reversal
      4. If all checks pass: add the severity score to CDE total

    Critical contradictions (severity >= 30) are tracked separately
    because a single one can trigger an instant interrogator win.

    Returns:
        score          — total CDE score, capped at 100
        contradictions — list of confirmed contradiction dicts
        total_count    — total number of contradictions found
        critical_count — number of critical (severity 30) contradictions
    """
    suspect_turns = [t for t in turns if t['speaker'] in ('suspect', 'you', 'user')]

    total_score    = 0.0
    contradictions = []
    critical_count = 0
    total_count    = 0

    for (stmt_a, stmt_b, severity) in CONTRADICTION_PAIRS:

        # Step 1: Do both statements exist anywhere in suspect speech?
        a_found = any(stmt_a in t['text'].lower() for t in suspect_turns)
        b_found = any(stmt_b in t['text'].lower() for t in suspect_turns)
        if not (a_found and b_found):
            continue

        # Step 2: Find which turn index each statement first appears in
        a_turn = next((t['index'] for t in suspect_turns
                       if stmt_a in t['text'].lower()), -1)
        b_turn = next((t['index'] for t in suspect_turns
                       if stmt_b in t['text'].lower()), -1)

        # Step 3: Only count if they are in DIFFERENT turns
        if a_turn == b_turn:
            continue

        # Step 4: Confirmed real contradiction — add to score
        total_score += severity
        total_count += 1
        if severity >= 30:
            critical_count += 1

        contradictions.append({
            'statement_a': stmt_a,
            'statement_b': stmt_b,
            'severity':    severity,
            'turn_a':      a_turn,
            'turn_b':      b_turn,
        })

    return {
        'score':          round(min(100.0, total_score), 2),
        'contradictions': contradictions,
        'total_count':    total_count,
        'critical_count': critical_count,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHM 4 ── PRS: Pressure-Response Scoring
# ══════════════════════════════════════════════════════════════════════════════

def run_prs(turns: List[Dict]) -> Dict:
    """
    Evaluate pressure dynamics across all turns using two parallel tracks.

    Track A — Resistance (scans suspect + lawyer turns):
        Defensive language raises resistance_score.
        High resistance_score → suspect holds ground → suspect_score stays high.
        Phrases: "objection", "prove it", "reasonable doubt", "i have an alibi" ...

    Track B — Interrogator Skill (scans interrogator turns):
        Strategic language raises skill_score.
        High skill_score → bonus to interrogator_score.
        Phrases: "you said earlier", "evidence shows", "contradicts" ...

    Both tracks apply TMD (Algorithm 3) — recent quality phrases matter more.

    Returns:
        resistance_score — how well suspect/lawyer defended (0–100)
        skill_score      — how strategically the interrogator operated (0–100)
    """
    total_turns      = len(turns)
    resistance_score = 0.0
    skill_score      = 0.0

    for turn in turns:
        text = turn['text'].lower()
        tmf  = tmf_weight(turn['index'], total_turns)   # Algorithm 3

        # Track A: Resistance from suspect and/or lawyer
        if turn['speaker'] in ('suspect', 'lawyer', 'you'):
            for (phrase, weight) in RESISTANCE_PHRASES:
                if phrase in text:
                    resistance_score += weight * tmf

        # Track B: Skill signals from interrogator
        if turn['speaker'] in ('interrogator', 'you'):
            for (phrase, weight) in INTERROGATOR_SKILL_PHRASES:
                if phrase in text:
                    skill_score += weight * tmf

    return {
        'resistance_score': round(min(100.0, resistance_score), 2),
        'skill_score':      round(min(100.0, skill_score), 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# COMPOSITE SCORER ── Runs all 4 algorithms and combines into final scores
# ══════════════════════════════════════════════════════════════════════════════

def score_session(conversation: str) -> Dict:
    """
    CIDS Master Scorer.

    Runs all four algorithms on the conversation string and combines
    their outputs into three final scores using weighted formulas.

    Composite formulas:
        interrogator_score = (LIA × 0.45) + (CDE × 0.35) + (PRS.skill × 0.20)
        suspect_score      = 70 − (LIA × 0.50) + (PRS.resist × 0.30) − (CDE × 0.20)
        defense_score      = 20 + (PRS.resist × 0.55) + (CDE × 0.15) + (PRS.skill × 0.10)

    Win condition evaluation order:
        1. Check INTERROGATOR_WINS gates (any one sufficient)
        2. Check SUSPECT_WINS conditions (all three required)
        3. If neither: return ONGOING

    Returns a full result dict including per-algorithm breakdowns for
    the frontend score display and the explain_verdict() function.
    """
    turns = parse_turns(conversation)
    if not turns:
        return _empty_result()

    # Count interrogator turns to enforce minimum round requirement for suspect win
    total_rounds = len([t for t in turns if t['speaker'] in ('interrogator', 'you', 'user')])

    # ── Run all four algorithms ───────────────────────────────────────────────
    lia = run_lia(turns)    # Algorithm 1
    cde = run_cde(turns)    # Algorithm 2
    prs = run_prs(turns)    # Algorithm 4   (Algorithm 3 runs inside LIA and PRS)

    # ── Composite score formulas ──────────────────────────────────────────────
    raw_int = (lia['score'] * 0.45) + (cde['score'] * 0.35) + (prs['skill_score']      * 0.20)
    raw_sus = 70.0 - (lia['score'] * 0.50) + (prs['resistance_score'] * 0.30) - (cde['score'] * 0.20)
    raw_def = 20.0 + (prs['resistance_score'] * 0.55) + (cde['score'] * 0.15) + (prs['skill_score'] * 0.10)

    # Clamp all scores to valid range [0, 100]
    interrogator_score = round(min(100.0, max(0.0, raw_int)), 1)
    suspect_score      = round(min(100.0, max(0.0, raw_sus)), 1)
    defense_score      = round(min(100.0, max(0.0, raw_def)), 1)

    # ── Win condition logic ───────────────────────────────────────────────────

    # Gate logic for INTERROGATOR_WINS — any single gate is sufficient
    int_wins = (
        interrogator_score        >= WIN_THRESHOLD_INTERROGATOR    # Gate 1: score threshold
        or cde['critical_count']  >= CRITICAL_CONTRADICTION_WIN    # Gate 2: 1 critical contradiction
        or cde['total_count']     >= HIGH_COUNT_CONTRADICTION       # Gate 3: 3+ total contradictions
        or (cde['total_count']    >= 2 and lia['max_severity'] >= 3) # Gate 4: compound condition
    )

    # All-conditions logic for SUSPECT_WINS — every condition must hold
    sus_wins = (
        suspect_score        >= WIN_THRESHOLD_SUSPECT        # survived with high score
        and interrogator_score < 40.0                        # interrogator failed to press
        and total_rounds     >= MIN_ROUNDS_FOR_SUSPECT_WIN   # at least 4 rounds played
    )

    if int_wins:
        status = "INTERROGATOR_WINS"
    elif sus_wins:
        status = "SUSPECT_WINS"
    else:
        status = "ONGOING"

    return {
        # ── Final composite scores ────────────────────────────────────────────
        "status":             status,
        "interrogator_score": interrogator_score,
        "suspect_score":      suspect_score,
        "defense_score":      defense_score,

        # ── Per-algorithm detail (for frontend display + explainability) ──────
        "lia": {
            "score":        lia['score'],
            "match_count":  lia['match_count'],
            "max_severity": lia['max_severity'],
            "matches":      lia['matched'],
        },
        "cde": {
            "score":          cde['score'],
            "total_count":    cde['total_count'],
            "critical_count": cde['critical_count'],
            "contradictions": cde['contradictions'],
        },
        "prs": {
            "resistance_score": prs['resistance_score'],
            "skill_score":      prs['skill_score'],
        },

        # ── Backward-compatible fields used by frontend chips ─────────────────
        "incriminating_count": lia['match_count'],
        "deflection_count":    len([p for (p, w) in RESISTANCE_PHRASES
                                    if p in conversation.lower()]),
        "contradictions":      cde['total_count'],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SESSION LIMIT ALGORITHMS ── Time limit, round limit, stalemate detection
# ══════════════════════════════════════════════════════════════════════════════

def detect_stalemate(score_history: List[float]) -> bool:
    """
    Stalemate Detection Algorithm.

    Checks whether the interrogator's score has barely moved over the
    last STALEMATE_WINDOW rounds. If movement is less than
    STALEMATE_SCORE_DELTA, the session is declared stagnant.

    This catches the "2 hours with no result" scenario — if both sides
    are just going in circles with no meaningful score change, the game
    will warn and then force a verdict rather than running indefinitely.

    Args:
        score_history: list of interrogator_score values, one per round

    Formula:
        window = last STALEMATE_WINDOW scores
        delta  = max(window) - min(window)
        stalemate = (delta < STALEMATE_SCORE_DELTA)
                    AND (len(score_history) >= STALEMATE_WINDOW)

    Example:
        scores  = [22.0, 22.1, 22.0, 21.9]   delta = 0.2  → STALEMATE (< 2.0)
        scores  = [22.0, 28.0, 31.0, 35.0]   delta = 13.0 → NOT stalemate
    """
    if len(score_history) < STALEMATE_WINDOW:
        return False                           # not enough rounds yet to judge
    window = score_history[-STALEMATE_WINDOW:]
    delta  = max(window) - min(window)
    return delta < STALEMATE_SCORE_DELTA


def forced_verdict(
    interrogator_score: float,
    suspect_score:      float,
    defense_score:      float,
    reason:             str,     # "TIME_LIMIT" | "ROUND_LIMIT" | "STALEMATE"
    rounds_played:      int,
    elapsed_seconds:    int,
) -> Dict:
    """
    Forced Verdict Algorithm.

    Called when a session hits a limit without achieving a clean algorithmic
    win. Determines the outcome purely by points comparison — like a boxing
    match going to the judges' scorecards.

    Decision logic:
        diff = interrogator_score - suspect_score

        if |diff| <= DRAW_MARGIN (5 pts)   → DRAW (too close to call)
        if diff > DRAW_MARGIN              → INTERROGATOR_WINS_BY_POINTS
        if diff < -DRAW_MARGIN             → SUSPECT_WINS_BY_POINTS

    The lawyer's defense_score determines the quality note in the summary:
        defense >= 70  → "exceptional" — lawyer performance fully credited
        defense >= 50  → "adequate"
        defense < 50   → "weak"

    Returns a verdict dict with:
        status, winner, reason, margin, rounds_played,
        elapsed_seconds, summary (human-readable), scores
    """
    diff = interrogator_score - suspect_score

    if abs(diff) <= DRAW_MARGIN:
        status  = "DRAW"
        winner  = "DRAW"
        summary = (
            f"Session ended by {reason} after {rounds_played} rounds "
            f"({elapsed_seconds // 60}m {elapsed_seconds % 60}s). "
            f"Scores were too close to determine a winner — "
            f"Interrogator {interrogator_score} vs Suspect {suspect_score}. "
            f"The case remains unresolved. Neither side secured a decisive advantage."
        )
    elif diff > DRAW_MARGIN:
        status  = "INTERROGATOR_WINS_BY_POINTS"
        winner  = "INTERROGATOR"
        summary = (
            f"Session ended by {reason} after {rounds_played} rounds "
            f"({elapsed_seconds // 60}m {elapsed_seconds % 60}s). "
            f"No clean confession or critical contradiction was secured, but the "
            f"interrogator led on points: {interrogator_score} vs {suspect_score} "
            f"(margin: {diff:.1f} pts). Verdict: Interrogator wins by points decision."
        )
    else:
        status  = "SUSPECT_WINS_BY_POINTS"
        winner  = "SUSPECT"
        summary = (
            f"Session ended by {reason} after {rounds_played} rounds "
            f"({elapsed_seconds // 60}m {elapsed_seconds % 60}s). "
            f"The suspect successfully ran down the clock without a fatal admission. "
            f"Suspect score: {suspect_score} vs Interrogator: {interrogator_score} "
            f"(margin: {abs(diff):.1f} pts). Verdict: Suspect wins by endurance."
        )

    # Append lawyer performance note
    if defense_score >= 70:
        summary += f" Defense was exceptional ({defense_score}/100) — lawyer fully credited."
    elif defense_score >= 50:
        summary += f" Defense was adequate ({defense_score}/100)."
    else:
        summary += f" Defense was weak ({defense_score}/100) — lawyer failed to protect."

    return {
        "status":          status,
        "winner":          winner,
        "reason":          reason,
        "margin":          round(abs(diff), 1),
        "rounds_played":   rounds_played,
        "elapsed_seconds": elapsed_seconds,
        "summary":         summary,
        "scores": {
            "interrogator": interrogator_score,
            "suspect":      suspect_score,
            "defense":      defense_score,
        },
    }


def check_session_limits(
    rounds_played:      int,
    elapsed_seconds:    int,
    score_history:      List[float],
    interrogator_score: float,
    suspect_score:      float,
    defense_score:      float,
) -> Dict:
    """
    Master Session-Limit Checker.

    Called every round from main.py after scoring.
    Checks all three limit types in priority order:
        1. TIME_LIMIT   — clock has expired
        2. ROUND_LIMIT  — maximum exchanges reached
        3. STALEMATE    — score frozen for too long near end of game

    Also issues a STALEMATE WARNING one round before forcing a stalemate
    verdict, giving players one last chance to break the deadlock.

    Returns:
        limit_hit        — True if a hard limit has been reached
        reason           — which limit fired ("TIME_LIMIT" / "ROUND_LIMIT" / "STALEMATE")
        verdict          — forced_verdict() result if limit_hit, else None
        warning          — stalemate warning string if approaching stalemate, else None
        time_remaining   — seconds left on the clock
        rounds_remaining — rounds left before round limit
    """
    time_remaining   = max(0, SESSION_TIME_LIMIT_SECONDS - elapsed_seconds)
    rounds_remaining = max(0, SESSION_ROUND_LIMIT - rounds_played)
    stalemate        = detect_stalemate(score_history)
    warning          = None

    # Issue stalemate WARNING (not yet forced) if stagnant but still time/rounds left
    if stalemate and rounds_remaining > 2 and time_remaining > 120:
        warning = (
            f"STALEMATE DETECTED: No meaningful score movement in the last "
            f"{STALEMATE_WINDOW} rounds. {rounds_remaining} rounds and "
            f"{time_remaining // 60}m {time_remaining % 60}s remaining. "
            f"Make a decisive move or the session will be forced to a draw."
        )

    # Check hard limits — first match wins
    reason = None
    if elapsed_seconds >= SESSION_TIME_LIMIT_SECONDS:
        reason = "TIME_LIMIT"
    elif rounds_played >= SESSION_ROUND_LIMIT:
        reason = "ROUND_LIMIT"
    elif stalemate and rounds_remaining <= 2:
        reason = "STALEMATE"        # stalemate + almost out of rounds = force it

    if reason:
        verdict = forced_verdict(
            interrogator_score, suspect_score, defense_score,
            reason, rounds_played, elapsed_seconds
        )
        return {
            "limit_hit":        True,
            "reason":           reason,
            "verdict":          verdict,
            "warning":          None,
            "time_remaining":   0,
            "rounds_remaining": 0,
        }

    return {
        "limit_hit":        False,
        "reason":           None,
        "verdict":          None,
        "warning":          warning,
        "time_remaining":   time_remaining,
        "rounds_remaining": rounds_remaining,
    }


# ══════════════════════════════════════════════════════════════════════════════
# EXPLAINABILITY ── Human-readable scoring breakdown for Judge AI
# ══════════════════════════════════════════════════════════════════════════════

def explain_verdict(result: Dict) -> str:
    """
    Generate a plain-English scoring breakdown from a score_session() result.

    This text is passed to the Judge AI agent as context so its
    spoken verdict sounds data-informed rather than generic.

    Example output:
        CIDS SCORING SUMMARY
        ─────────────────────────────────────────
          Interrogator : 61.0/100
          Suspect      : 38.5/100
          Defense      : 44.2/100

        [LIA] 2 incriminating phrase(s) detected (highest severity: 3/4)
              ↳ "i was there"        weight=18.0 × TMF=0.880 → 15.84 pts
              ↳ "we argued"          weight=12.0 × TMF=0.775 → 9.30 pts
        [CDE] 1 contradiction(s)  (0 critical)  score=20.0
              ↳ Turn 2: "i don't know him"  vs Turn 7: "i knew him"  (severity 20)
        [PRS] Interrogator skill: 22.4  |  Suspect resistance: 31.0
        [WIN] Status: ONGOING
    """
    lines = [
        "CIDS SCORING SUMMARY",
        "─────────────────────────────────────────",
        f"  Interrogator : {result['interrogator_score']}/100",
        f"  Suspect      : {result['suspect_score']}/100",
        f"  Defense      : {result['defense_score']}/100",
        "",
    ]

    lia = result.get('lia', {})
    if lia.get('match_count', 0) > 0:
        lines.append(
            f"[LIA] {lia['match_count']} incriminating phrase(s) detected "
            f"(highest severity: {lia['max_severity']}/4)"
        )
        for m in lia.get('matches', []):
            lines.append(
                f"      ↳ \"{m['phrase']:<26}\"  "
                f"weight={m['weight']}  ×TMF={m['tmf']}  → {m['weighted']} pts"
            )
    else:
        lines.append("[LIA] No incriminating phrases detected.")

    cde = result.get('cde', {})
    if cde.get('total_count', 0) > 0:
        lines.append(
            f"[CDE] {cde['total_count']} contradiction(s)  "
            f"({cde['critical_count']} critical)  score={cde['score']}"
        )
        for c in cde.get('contradictions', []):
            lines.append(
                f"      ↳ Turn {c['turn_a']}: \"{c['statement_a']}\"  "
                f"vs  Turn {c['turn_b']}: \"{c['statement_b']}\"  "
                f"(severity {c['severity']})"
            )
    else:
        lines.append("[CDE] No contradictions detected.")

    prs = result.get('prs', {})
    lines.append(
        f"[PRS] Interrogator skill: {prs.get('skill_score', 0):.1f}  |  "
        f"Suspect resistance: {prs.get('resistance_score', 0):.1f}"
    )
    lines.append(f"[WIN] Status: {result['status']}")

    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY
# ══════════════════════════════════════════════════════════════════════════════

def check_win(conversation: str) -> str:
    """Simple win-status check — kept for the /chat/legacy endpoint."""
    return score_session(conversation)["status"]


def get_judge_trigger(conversation: str, last_message: str) -> bool:
    """
    Returns True if the judge AI should respond this turn.
    Triggers on: objections, confessions, direct contradiction callouts,
    and formal court phrases.
    """
    trigger_words = [
        "objection", "your honor", "contradiction", "that's a lie",
        "i confess", "i admit", "i did it", "i was there",
    ]
    return any(word in last_message.lower() for word in trigger_words)


def _empty_result() -> Dict:
    """Default result returned when the conversation has no parseable turns."""
    return {
        "status":             "ONGOING",
        "interrogator_score": 0.0,
        "suspect_score":      70.0,
        "defense_score":      20.0,
        "lia":  {"score": 0, "match_count": 0, "max_severity": 0, "matches": []},
        "cde":  {"score": 0, "total_count": 0, "critical_count": 0, "contradictions": []},
        "prs":  {"resistance_score": 0, "skill_score": 0},
        "incriminating_count": 0,
        "deflection_count":    0,
        "contradictions":      0,
    }
