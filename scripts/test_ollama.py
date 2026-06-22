"""Quick connectivity + smoke test for the local Ollama setup.

Run:  python scripts/test_ollama.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings
from core.llm import get_client, LLMError


def main() -> int:
    print(f"→ Ollama host:  {settings.OLLAMA_HOST}")
    print(f"→ Ollama model: {settings.OLLAMA_MODEL}\n")

    client = get_client()
    health = client.health()
    print(f"Reachable:    {health.get('reachable')}")
    if not health.get("reachable"):
        print(f"Error: {health.get('error')}")
        print("\nIs Ollama running? Try:  ollama serve")
        return 1
    print(f"Model pulled: {health.get('model_pulled')}")
    if not health.get("model_pulled"):
        print(f"\nThe model isn't pulled yet. Run:\n  ollama pull {settings.OLLAMA_MODEL}")
        return 1

    print("\n→ Sending a tiny chat to verify inference…")
    reply = client.chat(
        [{"role": "user", "content": "Reply with the single word: pong"}],
        temperature=0.0,
        num_predict=8,
    )
    print(f"Reply: {reply!r}")
    if "pong" not in reply.lower():
        print("⚠ Unexpected reply — model may not be following instructions well.")
        return 1

    print("\n→ Sending a JSON-mode scoring dry-run…")
    result = client.score(
        system="You are a JSON API. Reply with strict JSON only.",
        user='Score this: {"answer":"hello","rubric":"basic greeting"}',
    )
    print(json.dumps(result, indent=2)[:500])
    print("\n✅ Smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LLMError as e:
        print(f"\n❌ LLM error: {e}")
        sys.exit(2)
