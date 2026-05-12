"""
Standalone test/demo for the Validation Layer — AI Dungeon Master.

Runs each of the 7 rules against a crafted bad LLM output and prints the
result. This proves the validator is alive WITHOUT needing the LLM, and
gives you concrete material for your final demo / paper.

Run:
    cd backend
    python test_validator.py
"""

from validator import Validator

CURRENT = {
    "health": 80,
    "inventory": ["Torch", "Dagger"],
    "quest": "Find the lost sword of Eldoria",
    "location": "Village entrance",
}

CASES = [
    {
        "name": "HEALTH_BOUNDS (health=150 should clamp to 100)",
        "llm_output": {
            "narrative": "You feel fine.",
            "player_state": {**CURRENT, "health": 150},
            "choices": ["Continue"],
        },
    },
    {
        "name": "HEALTH_JUMP (huge drop with peaceful narrative — should revert)",
        "llm_output": {
            "narrative": "You take a deep breath and look at the calm stars overhead.",
            "player_state": {**CURRENT, "health": 10},
            "choices": ["Continue"],
        },
    },
    {
        "name": "HEALTH_JUMP allowed (huge drop with combat narrative — should pass)",
        "llm_output": {
            "narrative": "The orc strikes you with a vicious slash, drawing blood.",
            "player_state": {**CURRENT, "health": 10},
            "choices": ["Continue"],
        },
    },
    {
        "name": "INVENTORY_ADD_UNJUSTIFIED (hallucinated 'Magic Sword' — should be removed)",
        "llm_output": {
            "narrative": "You take a quiet step forward and listen.",
            "player_state": {**CURRENT, "inventory": ["Torch", "Dagger", "Magic Sword"]},
            "choices": ["Continue"],
        },
    },
    {
        "name": "INVENTORY_ADD allowed (narrative mentions finding the item — should pass)",
        "llm_output": {
            "narrative": "Hidden under a loose stone, you find a Magic Sword glinting in torchlight.",
            "player_state": {**CURRENT, "inventory": ["Torch", "Dagger", "Magic Sword"]},
            "choices": ["Continue"],
        },
    },
    {
        "name": "INVENTORY_REMOVE_UNJUSTIFIED (Dagger vanishes silently — should be restored)",
        "llm_output": {
            "narrative": "You look around the quiet clearing.",
            "player_state": {**CURRENT, "inventory": ["Torch"]},
            "choices": ["Continue"],
        },
    },
    {
        "name": "LOCATION_TELEPORT (location change with no movement verb — should revert)",
        "llm_output": {
            "narrative": "You consider your options.",
            "player_state": {**CURRENT, "location": "Dragon's Lair"},
            "choices": ["Continue"],
        },
    },
    {
        "name": "LOCATION change allowed (narrative says 'you enter' — should pass)",
        "llm_output": {
            "narrative": "You enter the Dragon's Lair, heart pounding.",
            "player_state": {**CURRENT, "location": "Dragon's Lair"},
            "choices": ["Continue"],
        },
    },
    {
        "name": "QUEST_DRIFT (silent quest swap — should revert)",
        "llm_output": {
            "narrative": "You look at the trees.",
            "player_state": {**CURRENT, "quest": "Rescue the princess"},
            "choices": ["Continue"],
        },
    },
    {
        "name": "OUTPUT_SCHEMA (missing narrative & choices — should be filled with defaults)",
        "llm_output": {
            "player_state": CURRENT,
        },
    },
]


def main():
    v = Validator()
    print("=" * 70)
    print("VALIDATION LAYER — RULE-BY-RULE TEST")
    print("=" * 70)
    for i, case in enumerate(CASES, 1):
        print(f"\n[{i}] {case['name']}")
        print("-" * 70)
        out, violations = v.validate(
            session_id="TEST",
            turn_number=i,
            player_action=f"(test case {i})",
            current_state=CURRENT,
            llm_output=case["llm_output"],
        )
        if not violations:
            print("  ✅ No violations — change allowed.")
        else:
            print(f"  ⚠️  {len(violations)} violation(s):")
            for vi in violations:
                print(f"     - {vi.rule}: {vi.details}")
                print(f"       action: {vi.action_taken}")
        print(f"  final inventory: {out['player_state']['inventory']}")
        print(f"  final health:    {out['player_state']['health']}")
        print(f"  final location:  {out['player_state']['location']}")
        print(f"  final quest:     {out['player_state']['quest']}")

    print("\n" + "=" * 70)
    print("Full structured logs are saved to backend/logs/TEST.jsonl")
    print("=" * 70)


if __name__ == "__main__":
    main()
