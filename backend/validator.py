"""
Validation Layer — AI Dungeon Master
Step 4: Sits between the LLM and the StateManager.

Catches cases where the LLM's proposed state changes are NOT justified by
its own narrative (hallucinated items, teleporting, silent quest swaps, etc.).
Each violation is logged to backend/logs/{session_id}.jsonl so Step 8
(evaluation metrics) can compute an objective inconsistency rate.

Per the proposal:
  - "Validation Layer: Verifies consistency between generated outputs and stored state."
  - "Reduce state inconsistencies to fewer than 5% of turns during evaluation."

Rules implemented:
  1. HEALTH_BOUNDS               — clamp health to [0, 100]
  2. HEALTH_JUMP                 — big delta requires combat or healing in narrative
  3. INVENTORY_ADD_UNJUSTIFIED   — new item must be mentioned in narrative
  4. INVENTORY_REMOVE_UNJUSTIFIED— removed item must be mentioned in narrative
  5. LOCATION_TELEPORT           — location change requires a movement verb
  6. QUEST_DRIFT                 — quest change requires a quest-event keyword
  7. OUTPUT_SCHEMA               — required JSON fields are present
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


# ---------- Keyword sets used by rules ----------

COMBAT_KEYWORDS = {
    "attack", "strike", "hit", "stab", "slash", "fight", "battle", "wound",
    "blood", "damage", "hurt", "injure", "blow", "punch", "kick", "shoot",
    "arrow", "trap", "bite", "claw", "fall", "burn", "ambush", "cut",
}

HEALING_KEYWORDS = {
    "heal", "healed", "healing", "potion", "rest", "rests", "rested",
    "recover", "recovered", "restore", "restored", "bandage", "mend",
    "cure", "cured", "tend", "regenerate", "refresh",
}

MOVEMENT_KEYWORDS = {
    "walk", "walks", "walked", "run", "runs", "ran", "enter", "enters",
    "entered", "leave", "leaves", "left", "travel", "travels", "go", "goes",
    "went", "head", "heads", "headed", "move", "moves", "moved", "climb",
    "climbs", "descend", "descended", "step", "steps", "approach",
    "approaches", "arrive", "arrives", "arrived", "journey", "sprint",
    "crawl", "ride", "rides", "swim", "fly", "teleport", "warp", "exit",
}

ACQUIRE_KEYWORDS = {
    "find", "finds", "found", "pick", "picks", "picked", "take", "takes",
    "took", "grab", "grabs", "grabbed", "discover", "discovered", "receive",
    "received", "obtain", "obtained", "loot", "looted", "claim", "claimed",
    "gain", "gained", "acquire", "acquired", "given", "rewarded",
}

LOSE_KEYWORDS = {
    "drop", "drops", "dropped", "use", "uses", "used", "broke", "broken",
    "break", "lose", "lost", "give", "gives", "gave", "throw", "throws",
    "threw", "consume", "consumed", "shatter", "shattered", "stolen",
    "steal", "discard", "discarded", "trade", "traded",
}

QUEST_UPDATE_KEYWORDS = {
    "complete", "completed", "completes", "finish", "finished", "finishes",
    "accept", "accepts", "accepted", "new quest", "next quest", "quest log",
    "quest update", "quest", "mission", "task", "objective", "fulfill",
    "fulfilled", "succeed", "succeeded",
}


def _contains_any(text: str, keywords: set) -> bool:
    if not text:
        return False
    text_l = text.lower()
    return any(kw in text_l for kw in keywords)


def _item_mentioned(text: str, item: str) -> bool:
    if not text or not item:
        return False
    return item.lower() in text.lower()


# ---------- Violation record ----------

@dataclass
class Violation:
    rule: str
    severity: str  # "info" | "warning" | "error"
    details: str
    action_taken: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- Type coercion (defensive — same idea as Step 3 sanity) ----------

def _coerce_types(proposed: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        out["health"] = int(proposed.get("health", current["health"]))
    except (TypeError, ValueError):
        out["health"] = current["health"]

    inv = proposed.get("inventory", current["inventory"])
    if not isinstance(inv, list):
        inv = current["inventory"]
    out["inventory"] = [str(x) for x in inv if x is not None]

    quest = proposed.get("quest", current["quest"])
    out["quest"] = quest if isinstance(quest, str) and quest.strip() else current["quest"]

    location = proposed.get("location", current["location"])
    out["location"] = (
        location if isinstance(location, str) and location.strip() else current["location"]
    )
    return out


# ---------- Individual rules ----------

def _rule_health_bounds(health: int) -> Tuple[int, List[Violation]]:
    if 0 <= health <= 100:
        return health, []
    clamped = max(0, min(100, health))
    return clamped, [Violation(
        rule="HEALTH_BOUNDS",
        severity="warning",
        details=f"Health {health} outside [0,100], clamped to {clamped}.",
        action_taken="clamped",
        data={"original": health, "clamped": clamped},
    )]


def _rule_health_jump(
    current_health: int, proposed_health: int, narrative: str, threshold: int = 40
) -> Tuple[int, List[Violation]]:
    delta = proposed_health - current_health
    if abs(delta) <= threshold:
        return proposed_health, []
    if delta < 0 and _contains_any(narrative, COMBAT_KEYWORDS):
        return proposed_health, []
    if delta > 0 and _contains_any(narrative, HEALING_KEYWORDS):
        return proposed_health, []
    return current_health, [Violation(
        rule="HEALTH_JUMP",
        severity="warning",
        details=(
            f"Health changed {current_health} -> {proposed_health} (delta {delta}) "
            f"but narrative shows no combat/healing event."
        ),
        action_taken="reverted",
        data={"current": current_health, "proposed": proposed_health, "delta": delta},
    )]


def _rule_inventory(
    current_inv: List[str], proposed_inv: List[str], narrative: str
) -> Tuple[List[str], List[Violation]]:
    violations: List[Violation] = []
    current_set = set(current_inv)
    proposed_set = set(proposed_inv)

    added = proposed_set - current_set
    removed = current_set - proposed_set

    final_inv = list(proposed_inv)

    for item in added:
        # Allow if the narrative mentions the item by name OR uses an acquire verb.
        if not _item_mentioned(narrative, item) and not _contains_any(narrative, ACQUIRE_KEYWORDS):
            final_inv = [x for x in final_inv if x != item]
            violations.append(Violation(
                rule="INVENTORY_ADD_UNJUSTIFIED",
                severity="warning",
                details=f"LLM added '{item}' but narrative doesn't mention finding/receiving it.",
                action_taken="item_removed",
                data={"item": item},
            ))

    for item in removed:
        if not _item_mentioned(narrative, item) and not _contains_any(narrative, LOSE_KEYWORDS):
            if item not in final_inv:
                final_inv.append(item)
            violations.append(Violation(
                rule="INVENTORY_REMOVE_UNJUSTIFIED",
                severity="warning",
                details=f"LLM removed '{item}' but narrative doesn't mention using/losing it.",
                action_taken="item_restored",
                data={"item": item},
            ))

    return final_inv, violations


def _rule_location(
    current_location: str, proposed_location: str, narrative: str
) -> Tuple[str, List[Violation]]:
    if proposed_location == current_location:
        return proposed_location, []
    if _contains_any(narrative, MOVEMENT_KEYWORDS):
        return proposed_location, []
    return current_location, [Violation(
        rule="LOCATION_TELEPORT",
        severity="warning",
        details=(
            f"Location changed '{current_location}' -> '{proposed_location}' "
            f"but narrative has no movement verb."
        ),
        action_taken="reverted",
        data={"current": current_location, "proposed": proposed_location},
    )]


def _rule_quest(
    current_quest: str, proposed_quest: str, narrative: str
) -> Tuple[str, List[Violation]]:
    if proposed_quest == current_quest:
        return proposed_quest, []
    if _contains_any(narrative, QUEST_UPDATE_KEYWORDS):
        return proposed_quest, []
    return current_quest, [Violation(
        rule="QUEST_DRIFT",
        severity="warning",
        details=(
            f"Quest changed '{current_quest}' -> '{proposed_quest}' "
            f"but narrative shows no quest event."
        ),
        action_taken="reverted",
        data={"current": current_quest, "proposed": proposed_quest},
    )]


def _check_schema(llm_output: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Violation]]:
    violations: List[Violation] = []
    out = dict(llm_output) if isinstance(llm_output, dict) else {}

    if not isinstance(out.get("narrative"), str) or not out["narrative"].strip():
        violations.append(Violation(
            rule="OUTPUT_SCHEMA",
            severity="error",
            details="Missing or empty 'narrative' field.",
            action_taken="default_used",
        ))
        out["narrative"] = "(The DM falls momentarily silent.)"

    if not isinstance(out.get("player_state"), dict):
        violations.append(Violation(
            rule="OUTPUT_SCHEMA",
            severity="error",
            details="Missing or invalid 'player_state' field.",
            action_taken="default_used",
        ))
        out["player_state"] = {}

    choices = out.get("choices")
    if not isinstance(choices, list) or not choices:
        violations.append(Violation(
            rule="OUTPUT_SCHEMA",
            severity="warning",
            details="Missing or empty 'choices' list.",
            action_taken="default_used",
        ))
        out["choices"] = ["Continue cautiously", "Look around", "Check inventory"]

    return out, violations


# ---------- The Validator ----------

class Validator:
    """
    Orchestrates the 7 rules and writes per-turn logs.
    """

    def __init__(self, logs_dir: Path = LOGS_DIR):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(exist_ok=True)

    def validate(
        self,
        session_id: str,
        turn_number: int,
        player_action: str,
        current_state: Dict[str, Any],
        llm_output: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[Violation]]:
        """
        Validate a single LLM turn.

        Returns:
            (validated_llm_output, violations)
            where validated_llm_output is the LLM dict with its player_state
            replaced by the corrected one.
        """
        violations: List[Violation] = []

        out, v = _check_schema(llm_output)
        violations.extend(v)

        narrative = out.get("narrative", "")
        proposed = _coerce_types(out["player_state"], current_state)

        new_health, v = _rule_health_bounds(proposed["health"])
        violations.extend(v)
        new_health, v = _rule_health_jump(current_state["health"], new_health, narrative)
        violations.extend(v)

        new_inv, v = _rule_inventory(current_state["inventory"], proposed["inventory"], narrative)
        violations.extend(v)

        new_location, v = _rule_location(current_state["location"], proposed["location"], narrative)
        violations.extend(v)

        new_quest, v = _rule_quest(current_state["quest"], proposed["quest"], narrative)
        violations.extend(v)

        validated_state = {
            "health": new_health,
            "inventory": new_inv,
            "quest": new_quest,
            "location": new_location,
        }
        out["player_state"] = validated_state

        self._log_turn(
            session_id=session_id,
            turn_number=turn_number,
            player_action=player_action,
            narrative=narrative,
            current_state=current_state,
            proposed_state=proposed,
            final_state=validated_state,
            violations=violations,
        )

        return out, violations

    def _log_turn(
        self,
        session_id: str,
        turn_number: int,
        player_action: str,
        narrative: str,
        current_state: Dict[str, Any],
        proposed_state: Dict[str, Any],
        final_state: Dict[str, Any],
        violations: List[Violation],
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "turn_number": turn_number,
            "player_action": player_action,
            "narrative": narrative,
            "current_state": current_state,
            "proposed_state": proposed_state,
            "final_state": final_state,
            "violations": [v.to_dict() for v in violations],
            "violation_count": len(violations),
        }
        path = self.logs_dir / f"{session_id}.jsonl"
        with path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
