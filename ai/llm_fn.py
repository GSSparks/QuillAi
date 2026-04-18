"""
ai/llm_fn.py

Standalone LLM callable factory — returns a simple prompt→response
function that uses the current settings without importing the full
AIWorker. Used for memory extraction, FAQ, wiki generation etc.
"""

import requests


def make_llm_fn(settings_manager):
    """
    Return a callable(prompt: str) -> str that hits the active backend.
    Non-streaming, short timeout, max 500 tokens.
    """
    def _llm_fn(prompt: str) -> str:
        try:
            response = requests.post(
                settings_manager.get_llm_url(),
                json={
                    "model":      settings_manager.get_active_model(),
                    "messages":   [{"role": "user", "content": prompt}],
                    "stream":     False,
                    "max_tokens": 500,
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings_manager.get_api_key()}",
                },
                timeout=120,
            )
            data    = response.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            content = data.get("content", [])
            return content[0].get("text", "") if content else ""
        except Exception:
            return ""

    return _llm_fn
