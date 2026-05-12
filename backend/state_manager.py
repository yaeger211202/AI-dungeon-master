"""
State Manager — AI Dungeon Master
Step 3: Server-side persistent state, independent of the LLM.

Design:
- Each game session has a unique session_id (uuid4).
- State is persisted to backend/sessions/{session_id}.json after every change.
- The LLM PROPOSES new state in its JSON response. The StateManager APPLIES
  those proposals with minimal sanity rules (full validation is Step 4).

Per the capstone proposal: "State Manager: Maintains persistent player
attributes ... independent of the LLM's internal memory."
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock
from typing import Optional


SESSIONS_DIR = Path(__file__).parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


DEFAULT_PLAYER_STATE = {
    "health": 100,
    "inventory": ["Torch", "Dagger"],
    "quest": "Find the lost sword of Eldoria",
    "location": "Village entrance",
}


class StateManager:
    """Disk-backed per-session state. Single global lock keeps file writes safe."""

    def __init__(self, sessions_dir: Path = SESSIONS_DIR):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(exist_ok=True)
        self._lock = Lock()

    # ---------- file helpers ----------

    def _session_path(self, session_id: str) -> Path:
        # session_id is a uuid4 we generated, but be defensive about path traversal anyway.
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.sessions_dir / f"{safe_id}.json"

    def _load(self, session_id: str) -> Optional[dict]:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        with path.open() as f:
            return json.load(f)

    def _save(self, session: dict) -> None:
        path = self._session_path(session["session_id"])
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(session, f, indent=2)
        tmp.replace(path)  # atomic on POSIX — no half-written files

    # ---------- public API ----------

    def get_or_create(self, session_id: Optional[str] = None) -> dict:
        """Return the session dict, creating a new one if needed."""
        with self._lock:
            if session_id:
                existing = self._load(session_id)
                if existing:
                    # Backfill 'summaries' for older sessions created before Step 5.
                    if "summaries" not in existing:
                        existing["summaries"] = []
                        self._save(existing)
                    return existing

            new_id = session_id or str(uuid.uuid4())
            session = {
                "session_id": new_id,
                "player_state": dict(DEFAULT_PLAYER_STATE),
                "conversation_history": [],
                "summaries": [],
            }
            session["player_state"]["inventory"] = list(DEFAULT_PLAYER_STATE["inventory"])
            self._save(session)
            return session

    def apply_llm_proposal(self, session_id: str, proposed: dict) -> dict:
        """
        Update state based on the LLM's proposed player_state.
        Minimal sanity rules only (Step 4 will layer real validation on top):
          - health is an int, clamped to [0, 100]
          - inventory is a list of strings
          - quest and location are strings
          - missing/None fields fall back to current state
        """
        with self._lock:
            session = self._load(session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")

            current = session["player_state"]
            proposed = proposed or {}

            # health
            try:
                health = int(proposed.get("health", current["health"]))
            except (TypeError, ValueError):
                health = current["health"]
            health = max(0, min(100, health))

            # inventory
            inv = proposed.get("inventory", current["inventory"])
            if not isinstance(inv, list):
                inv = current["inventory"]
            inv = [str(x) for x in inv if x is not None]

            # quest
            quest = proposed.get("quest", current["quest"])
            if not isinstance(quest, str) or not quest.strip():
                quest = current["quest"]

            # location
            location = proposed.get("location", current["location"])
            if not isinstance(location, str) or not location.strip():
                location = current["location"]

            session["player_state"] = {
                "health": health,
                "inventory": inv,
                "quest": quest,
                "location": location,
            }
            self._save(session)
            return session

    def set_player_state(self, session_id: str, validated_state: dict) -> dict:
        """
        Write a fully-validated player_state directly. Used by the structured
        path in main.py — the Validator (Step 4) has already enforced all rules,
        so this is a pure persistence call.
        """
        with self._lock:
            session = self._load(session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")
            session["player_state"] = {
                "health": int(validated_state["health"]),
                "inventory": list(validated_state["inventory"]),
                "quest": str(validated_state["quest"]),
                "location": str(validated_state["location"]),
            }
            self._save(session)
            return session

    def add_turn_to_history(self, session_id: str, player_line: str, dm_line: str) -> None:
        with self._lock:
            session = self._load(session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")
            session["conversation_history"].append(f"Player: {player_line}")
            session["conversation_history"].append(f"DM: {dm_line}")
            self._save(session)

    def add_summary(self, session_id: str, summary_text: str) -> dict:
        """Append a compressed-memory summary to this session."""
        with self._lock:
            session = self._load(session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")
            session.setdefault("summaries", []).append(summary_text)
            self._save(session)
            return session

    def reset(self, session_id: str) -> dict:
        with self._lock:
            session = {
                "session_id": session_id,
                "player_state": dict(DEFAULT_PLAYER_STATE),
                "conversation_history": [],
                "summaries": [],
            }
            session["player_state"]["inventory"] = list(DEFAULT_PLAYER_STATE["inventory"])
            self._save(session)
            return session

    def list_sessions(self) -> list[str]:
        return [p.stem for p in self.sessions_dir.glob("*.json")]
