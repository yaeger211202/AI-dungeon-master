"""
AI Dungeon Master — FastAPI Backend
Step 4: Validation Layer integrated.

Flow per /action:
    1. Load (or create) session from StateManager
    2. Build prompts (prompts.py)
    3. Call LLM (llm.py)
    4. Run Validator over the proposed state vs current state
    5. Persist VALIDATED state via StateManager.set_player_state
    6. Append turn to conversation history
    7. Return narrative + state + choices (+ violations, for transparency)

Endpoints:
  GET  /health                              -> sanity check
  POST /action                              -> player action; returns narrative + state
  POST /reset                               -> reset a session to defaults
  GET  /session/{session_id}                -> inspect a session's current state
  GET  /session/{session_id}/violations     -> read this session's validation log
  GET  /sessions                            -> list all session ids (debug)
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from prompts import get_system_prompt, build_turn_prompt
from llm import generate_structured
from state_manager import StateManager
from validator import Validator, LOGS_DIR
from memory import MemoryManager
from baseline import BaselineEngine

app = FastAPI(title="AI Dungeon Master API", version="0.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_manager = StateManager()
validator = Validator()
memory = MemoryManager(state_manager)
baseline_engine = BaselineEngine()


# ---------- Request / Response models ----------

class ActionRequest(BaseModel):
    action: str
    session_id: Optional[str] = None


class ResetRequest(BaseModel):
    session_id: Optional[str] = None


class PlayerState(BaseModel):
    health: int
    inventory: List[str]
    quest: str
    location: str


class ActionResponse(BaseModel):
    session_id: str
    narrative: str
    player_state: PlayerState
    npc_dialogue: Optional[str] = None
    choices: List[str]
    violations: List[Dict[str, Any]] = []  # surfaced for transparency / Step 8 metrics


# ---------- Routes ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-dungeon-master", "version": "0.6.0"}


@app.post("/action", response_model=ActionResponse)
def action(req: ActionRequest):
    user_action = req.action.strip()
    if not user_action:
        raise HTTPException(status_code=400, detail="action cannot be empty")

    session = state_manager.get_or_create(req.session_id)
    session_id = session["session_id"]
    current_state = session["player_state"]
    turn_number = len(session["conversation_history"]) // 2 + 1

    system_prompt = get_system_prompt("base")
    user_prompt = build_turn_prompt(
        current_state,
        session["conversation_history"],
        user_action,
        summaries=session.get("summaries", []),
    )

    try:
        llm_output = generate_structured(system_prompt, user_prompt)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"LLM produced invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    # ---- Validation Layer ----
    validated_output, violations = validator.validate(
        session_id=session_id,
        turn_number=turn_number,
        player_action=user_action,
        current_state=current_state,
        llm_output=llm_output,
    )

    narrative = validated_output["narrative"]
    npc_dialogue = validated_output.get("npc_dialogue") or None
    choices = validated_output["choices"]

    # Persist validated state
    session = state_manager.set_player_state(session_id, validated_output["player_state"])
    state_manager.add_turn_to_history(session_id, user_action, narrative)

    # If we just crossed a summary boundary, fold those turns into a summary.
    memory.maybe_summarize(session_id)

    return ActionResponse(
        session_id=session_id,
        narrative=narrative,
        player_state=PlayerState(**session["player_state"]),
        npc_dialogue=npc_dialogue,
        choices=choices,
        violations=[v.to_dict() for v in violations],
    )


@app.post("/reset")
def reset(req: ResetRequest):
    session_id = req.session_id
    if not session_id:
        session = state_manager.get_or_create(None)
    else:
        session = state_manager.reset(session_id)
    return {
        "status": "reset",
        "session_id": session["session_id"],
        "player_state": session["player_state"],
    }


@app.get("/session/{session_id}")
def get_session(session_id: str):
    session = state_manager._load(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@app.get("/session/{session_id}/violations")
def get_violations(session_id: str):
    """Read this session's validation log. Used for debugging + Step 8 metrics."""
    path = Path(LOGS_DIR) / f"{session_id}.jsonl"
    if not path.exists():
        return {"session_id": session_id, "turns": [], "total_violations": 0}
    turns = []
    total = 0
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            turns.append(entry)
            total += entry.get("violation_count", 0)
    return {
        "session_id": session_id,
        "turns": turns,
        "total_violations": total,
        "turn_count": len(turns),
        "violation_rate": (total / len(turns)) if turns else 0.0,
    }


@app.get("/sessions")
def list_sessions():
    return {"sessions": state_manager.list_sessions()}


# ---------- Baseline (free-form) endpoints — Step 6 ----------

class BaselineActionResponse(BaseModel):
    session_id: str
    narrative: str
    mode: str = "baseline"


@app.post("/baseline/action", response_model=BaselineActionResponse)
def baseline_action(req: ActionRequest):
    user_action = req.action.strip()
    if not user_action:
        raise HTTPException(status_code=400, detail="action cannot be empty")
    try:
        result = baseline_engine.generate_turn(req.session_id, user_action)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")
    return BaselineActionResponse(**result)


@app.post("/baseline/reset")
def baseline_reset(req: ResetRequest):
    session_id = req.session_id
    if not session_id:
        session = baseline_engine.get_or_create(None)
    else:
        session = baseline_engine.reset(session_id)
    return {"status": "reset", "session_id": session["session_id"]}


@app.get("/baseline/session/{session_id}")
def get_baseline_session(session_id: str):
    session = baseline_engine._load(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session
