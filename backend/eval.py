"""
Evaluation script — AI Dungeon Master
Step 7: Reads validator logs + session files and prints summary metrics.

Use the numbers it prints directly on your slides.

Run:
    cd backend
    python eval.py
"""

import json
from collections import Counter
from pathlib import Path


BACKEND_DIR = Path(__file__).parent
LOGS_DIR = BACKEND_DIR / "logs"
SESSIONS_DIR = BACKEND_DIR / "sessions"
BASELINE_DIR = BACKEND_DIR / "baseline_sessions"


def load_jsonl(path: Path):
    out = []
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def analyze_structured():
    session_files = list(SESSIONS_DIR.glob("*.json")) if SESSIONS_DIR.exists() else []
    log_files = list(LOGS_DIR.glob("*.jsonl")) if LOGS_DIR.exists() else []

    # Skip the TEST session created by test_validator.py — it's synthetic.
    log_files = [p for p in log_files if p.stem != "TEST"]

    sessions = []
    for sf in session_files:
        try:
            with sf.open() as f:
                sessions.append(json.load(f))
        except Exception:
            continue

    total_turns = 0
    total_violations = 0
    rule_counter: Counter = Counter()
    per_session = []

    for lf in log_files:
        entries = load_jsonl(lf)
        if not entries:
            continue
        turns = len(entries)
        viols = sum(e.get("violation_count", 0) for e in entries)
        total_turns += turns
        total_violations += viols
        for e in entries:
            for v in e.get("violations", []):
                rule_counter[v.get("rule", "UNKNOWN")] += 1
        per_session.append({
            "session_id": lf.stem,
            "turns": turns,
            "violations": viols,
            "rate": (viols / turns) if turns else 0.0,
        })

    return {
        "session_count_on_disk": len(sessions),
        "session_count_with_logs": len(per_session),
        "total_turns": total_turns,
        "total_violations": total_violations,
        "violation_rate": (total_violations / total_turns) if total_turns else 0.0,
        "by_rule": dict(rule_counter),
        "per_session": per_session,
    }


def analyze_baseline():
    baseline_files = list(BASELINE_DIR.glob("*.json")) if BASELINE_DIR.exists() else []
    total_turns = 0
    sessions = []
    for bf in baseline_files:
        try:
            with bf.open() as f:
                data = json.load(f)
            turns = len(data.get("conversation_history", [])) // 2
            total_turns += turns
            sessions.append({"session_id": bf.stem, "turns": turns})
        except Exception:
            continue
    return {
        "session_count": len(sessions),
        "total_turns": total_turns,
        "per_session": sessions,
    }


def hr():
    print("=" * 72)


def main():
    hr()
    print("AI DUNGEON MASTER — EVALUATION REPORT")
    hr()

    s = analyze_structured()
    print("\n[STRUCTURED SYSTEM]  (state mgr + validator + memory)")
    print(f"  Sessions on disk:           {s['session_count_on_disk']}")
    print(f"  Sessions with validation logs: {s['session_count_with_logs']}")
    print(f"  Total turns played:         {s['total_turns']}")
    print(f"  Total validator violations: {s['total_violations']}")
    if s["total_turns"]:
        print(f"  Violation rate per turn:    {s['violation_rate']:.2%}")
        target = 0.05
        verdict = "PASS ✅" if s["violation_rate"] < target else "MISS ⚠️"
        print(f"  Proposal target (<5%):      {verdict}")
    print()
    if s["by_rule"]:
        print("  Violations by rule:")
        for rule, count in sorted(s["by_rule"].items(), key=lambda kv: -kv[1]):
            print(f"     {rule:<32} {count}")
    else:
        print("  Violations by rule:        (none)")

    print()
    print("  Per-session breakdown:")
    if not s["per_session"]:
        print("     (no sessions yet — play a few turns in Structured mode)")
    for ps in s["per_session"]:
        sid = ps["session_id"][:8]
        print(f"     {sid}...  turns={ps['turns']:>3}  violations={ps['violations']:>2}  rate={ps['rate']:.0%}")

    hr()
    b = analyze_baseline()
    print("\n[BASELINE SYSTEM]  (free-form LLM, no state, no validation)")
    print(f"  Sessions on disk:    {b['session_count']}")
    print(f"  Total turns played:  {b['total_turns']}")
    print("  (Baseline has no automatic validation; review transcripts manually")
    print("   or use an LLM judge to compare narrative coherence.)")
    if b["per_session"]:
        print()
        print("  Per-session breakdown:")
        for ps in b["per_session"]:
            sid = ps["session_id"][:8]
            print(f"     {sid}...  turns={ps['turns']:>3}")

    hr()
    print("\nNumbers to put on your slides:")
    print(f"  - Structured turns played:    {s['total_turns']}")
    print(f"  - Structured violations:      {s['total_violations']}")
    if s["total_turns"]:
        print(f"  - Structured violation rate:  {s['violation_rate']:.1%}")
    print(f"  - Baseline turns played:      {b['total_turns']}")
    hr()


if __name__ == "__main__":
    main()
