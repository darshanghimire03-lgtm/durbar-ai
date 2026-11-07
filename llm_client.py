import json
import logging
import urllib.request

import config

log = logging.getLogger("durbar.llm")

URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are Durbar AI, a friendly assistant inside a school app. "
    "Answer in simple English only. Keep answers short and clear. "
    "If you are not sure, say so instead of guessing."
)


class LLMClient:
    @property
    def enabled(self):
        return bool(config.OPENROUTER_API_KEY)

    def ask(self, message, history=None):
        if not self.enabled:
            return None
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += history or []
        messages.append({"role": "user", "content": message})
        body = {
            "model": config.OPENROUTER_MODEL,
            "messages": messages,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        if config.OPENROUTER_REASONING:
            body["reasoning"] = {"enabled": True}
        request = urllib.request.Request(
            URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"].get("content")
            return text.strip() if text else None
        except Exception as exc:
            log.error("LLM request failed: %s", type(exc).__name__)
            return None