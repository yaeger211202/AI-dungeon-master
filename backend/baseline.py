"""
Baseline (Free-form) Engine — AI Dungeon Master
Step 6: The "control group" for the experimental comparison.

Per the proposal:
  "Baseline Model: Free-form LLM narrative generation without structured control."

This deliberately has NONE of the safeguards from steps 3-5:
  - No structured JSON output
  - No external State Manager (LLM tracks state in its head only)
  - No Validation Layer
  - No Memory Summarization (raw history only, last 6 turns)

Persists a simple per-session conversation log to backend/baseline_sessions/
so we can review the transcript for incoherences in the demo / slides.
"""

import json
import uuid
from pathlib import Path
from threading import Lock
from typing import Optional, List

from llm import generate_freeform


BASELINE_SESSIONS_DIR = Path(__file__).parent / "baseline_sessions"
BASELINE_SESSIONS_DIR.mkdir(exist_ok=True)


BASELINE_SYSTEM_PROMPT = """You are a Dungeon Master running an immersive fantasy RPG adventure.

Narrate vivid scenes (2-4 sentences), control NPCs, manage combat outcomes,
and progress the quest. Stay descriptive and atmospheric. You may suggest
possible next actions in your narration if it fits naturally.

Begin the player's adventure: they are searching for the lost sword of Eldoria,
starting at the village entrance with a torch and a dagger."""


class BaselineEngine:
    def __init__(self, sessions_dir: Path = BASELINE_SESSIONS_DIR):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(exist_ok=True)
        self._lock = Lock()

    def _path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.sessions_dir / f"{safe}.json"

    def _load(self, session_id: str) -> Optional[dict]:
        p = self._path(session_id)
        if not p.exists():
            return None
        with p.open() as f:
            return json.load(f)

    def _save(self, session: dict) -> None:
        p = self._path(session["session_id"])
        tmp = p.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(session, f, indent=2)
        tmp.replace(p)

    def get_or_create(self, session_id: Optional[str] = None) -> dict:
        with self._lock:
            if session_id:
                existing = self._load(session_id)
                if existing:
                    return existing
            new_id = session_id or str(uuid.uuid4())
            session = {"session_id": new_id, "conversation_history": []}
            self._save(session)
            return session

    def generate_turn(self, session_id: Optional[str], user_action: str) -> dict:
        """
        Free-form turn. No state, no validation, no summaries.
        Returns: {session_id, narrative}
        """
        session = self.get_or_create(session_id)
        sid = session["session_id"]
        history = session["conversation_history"][-6:]  # last 3 turns, raw

        history_text = "\n".join(history) if history else "(adventure just beginning)"
        user_prompt = f"""Recent History:
{history_text}

Player Action: {user_action}

Respond as the Dungeon Master:"""

        narrative = generate_freeform(BASELINE_SYSTEM_PROMPT, user_prompt).strip()

        with self._lock:
            session = self._load(sid)
            session["conversation_history"].append(f"Player: {user_action}")
            session["conversation_history"].append(f"DM: {narrative}")
            self._save(session)

        return {"session_id": sid, "narrative": narrative}

    def reset(self, session_id: str) -> dict:
        with self._lock:
            session = {"session_id": session_id, "conversation_history": []}
            self._save(session)
            return session
