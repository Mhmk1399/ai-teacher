"""Thin client around Ollama's HTTP API.

Why not the official ``ollama`` python package?  It is fine, but a tiny
hand-rolled HTTP client is easier to read, easier to mock in tests, and gives
us direct control over JSON mode, retries, and timeouts.
"""
from __future__ import annotations
import json
import time
from typing import Any
import requests

from core.config import settings


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None, timeout: int = 300):
        self.host = (host or settings.OLLAMA_HOST).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout

    # ---------- low-level ----------

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.host}{path}"
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise LLMError(f"Ollama returned error: {data['error']}")
            return data
        except requests.RequestException as e:
            raise LLMError(f"Ollama call failed: {e}") from e

    def _get(self, path: str) -> dict:
        url = f"{self.host}{path}"
        try:
            r = requests.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise LLMError(f"Ollama call failed: {e}") from e

    def health(self) -> dict:
        """Check Ollama is reachable and the model is pulled."""
        try:
            tags = self._get("/api/tags")
            models = [m.get("name", "") for m in tags.get("models", [])]
            ok = self.model in models
            return {"reachable": True, "model_pulled": ok, "available_models": models}
        except LLMError as e:
            return {"reachable": False, "error": str(e)}

    # ---------- chat ----------

    def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.2,
        num_predict: int = 1024,
        max_retries: int = 2,
    ) -> str:
        """Plain chat completion. Returns the assistant text content."""
        options = {"temperature": temperature, "num_predict": num_predict}
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"

        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                t0 = time.time()
                data = self._post("/api/chat", payload)
                dt = time.time() - t0
                content = data.get("message", {}).get("content", "")
                if not content:
                    raise LLMError("Empty response from Ollama")
                return content
            except LLMError as e:
                try:
                    return self.generate_from_messages(
                        messages,
                        json_mode=json_mode,
                        temperature=temperature,
                        num_predict=num_predict,
                    )
                except LLMError as generate_error:
                    last_err = LLMError(f"{e}; generate fallback also failed: {generate_error}")
                    break
                last_err = e
                if attempt < max_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"Ollama chat failed after retries: {last_err}")

    def generate_from_messages(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.2,
        num_predict: int = 1024,
    ) -> str:
        """Fallback for Ollama models/servers that expose completion but not chat."""
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        prompt_parts = [
            f"{m.get('role', 'user').upper()}:\n{m.get('content', '')}"
            for m in messages
            if m.get("role") != "system"
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": "\n\n".join(prompt_parts),
            "system": "\n\n".join(system_parts),
            "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if json_mode:
            payload["format"] = "json"

        data = self._post("/api/generate", payload)
        content = data.get("response", "")
        if not content:
            raise LLMError("Empty response from Ollama generate endpoint")
        return content

    # ---------- high-level helpers ----------

    def score(self, system: str, user: str) -> dict:
        """Force a JSON object back, parse it, raise if not valid JSON."""
        text = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_mode=True,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {e}\n--- raw ---\n{text}") from e


# Module-level singleton (cheap; recreated if settings change).
_client: OllamaClient | None = None


def get_client() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
