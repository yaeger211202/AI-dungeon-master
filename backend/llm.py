"""
LLM client wrapper — AI Dungeon Master
Step 2: Talks to Groq's API and returns parsed JSON.

This is the ONLY place the rest of the app talks to the LLM. If we later swap
models (e.g. for the baseline-vs-structured experiment in Step 7), we change
it here.
"""

import os
import json
from typing import Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
        "and paste your key from https://console.groq.com/keys"
    )

_client = Groq(api_key=GROQ_API_KEY)


def generate_structured(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
    max_tokens: int = 1024,
) -> dict:
    """
    Call the LLM and return a parsed JSON dict.
    Uses Groq's JSON mode so the model is forced to produce valid JSON.

    Raises:
        ValueError if the response isn't valid JSON (rare with JSON mode).
        groq.APIError on network/auth issues.
    """
    completion = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
        max_tokens=max_tokens,
    )

    raw = completion.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {raw[:200]}...") from e


def generate_freeform(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
    max_tokens: int = 1024,
) -> str:
    """
    Plain-text generation. Used later for the BASELINE system in Step 6
    (free-form narrative without JSON structure).
    """
    completion = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return completion.choices[0].message.content
