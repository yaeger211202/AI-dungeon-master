"""
Memory Manager — AI Dungeon Master
Step 5: Compresses old turns into running summaries.

Why this exists (from the proposal):
  - "Memory Compression Module: Summarizes previous turns to manage token
     limits and maintain long-term coherence."
  - "Implement memory summarization and explicit state reinforcement in prompts."
  - "To maintain narrative coherence for at least 15-20 consecutive turns."

Strategy:
  Every SUMMARY_EVERY turns, we ask the LLM to summarize the just-completed
  chunk of turns into 2-3 sentences. Summaries accumulate across the session
  and are injected into the prompt for every subsequent turn (via
  prompts.build_turn_prompt). The last few raw turns are ALSO included, so
  the LLM gets a high-level recap PLUS verbatim recent context.
"""

from prompts import MEMORY_SUMMARY_PROMPT
from llm import generate_freeform

SUMMARY_EVERY = 6  # Trigger a new summary every N completed turns.


class MemoryManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager

    def maybe_summarize(self, session_id: str) -> bool:
        """
        If the session has just crossed a SUMMARY_EVERY boundary, generate a
        summary of the most recent block of turns and persist it.

        Returns True if a new summary was created.
        """
        session = self.state_manager._load(session_id)
        if session is None:
            return False

        turn_count = len(session["conversation_history"]) // 2
        summaries = session.get("summaries", [])
        summary_count = len(summaries)
        expected_summaries = turn_count // SUMMARY_EVERY

        if summary_count >= expected_summaries:
            return False  # No boundary crossed since last summary.

        # Summarize the chunk that just completed:
        # turns [summary_count*N, (summary_count+1)*N)
        start_turn = summary_count * SUMMARY_EVERY
        end_turn = start_turn + SUMMARY_EVERY
        start_idx = start_turn * 2  # each turn = 2 history entries
        end_idx = end_turn * 2
        chunk = session["conversation_history"][start_idx:end_idx]
        if not chunk:
            return False
        chunk_text = "\n".join(chunk)

        try:
            summary = generate_freeform(MEMORY_SUMMARY_PROMPT, chunk_text, temperature=0.3)
        except Exception as e:
            print(f"[memory] summarization failed: {e}")
            return False

        summary = (summary or "").strip()
        if not summary:
            return False

        self.state_manager.add_summary(session_id, summary)
        print(
            f"[memory] session={session_id[:8]} turn={turn_count} "
            f"summary#{summary_count + 1} generated ({len(summary)} chars)"
        )
        return True
