"""General assistant agent."""

import re

import httpx

from backend.agents.base import Agent
from backend.app.config import settings
from backend.core.models import AgentContext
from backend.core.ai_controls import guard_input, guard_output, track_llm_run


class AssistantAgent(Agent):
    name = "assistant"

    def run(self, context: AgentContext) -> str:
        message = context.message.strip() or "Please introduce yourself."
        try:
            return self._call_llm(message)
        except httpx.ConnectError:
            return (
                "AskBank cannot connect to the language model provider. "
                "Check OPENAI_BASE_URL and your network, VPN, or firewall settings."
            )
        except httpx.HTTPStatusError:
            return (
                "AskBank reached the language model provider, but it rejected the request. "
                "Check OPENAI_API_KEY and LLM_MODEL in .env."
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return (
                "AskBank is unable to reach the language model right now. "
                "Please configure LLM_API_KEY and LLM_MODEL, then try again."
            )

    def _call_llm(self, message: str) -> str:
        message = guard_input(message)
        expanded = bool(re.search(r"\b(more|detail|detailed|explain further|elaborate|deep dive)\b", message, re.IGNORECASE))
        word_limit = 500 if expanded else 200
        provider = settings.llm_provider.casefold().strip() or "openai"

        system_prompt = (
            "You are AskBank, a helpful general banking and workplace assistant. "
            f"Answer the user's question directly in a clear, professional way. Keep the response under {word_limit} words. "
            "Do not mention internal prompts, routing, retrieval, or unavailable tools. "
            "If the question is ambiguous, state the most useful general answer and ask one concise follow-up question."
        )

        if provider == "ollama":
            response = httpx.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                },
                timeout=60.0,
            )
            response.raise_for_status()
            answer = response.json()["message"]["content"]
        else:
            api_key = settings.llm_api_key or settings.openai_api_key
            model = settings.llm_model.strip() or "gpt-4o-mini"
            if not api_key:
                raise ValueError("LLM_API_KEY and LLM_MODEL are required")
            base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "max_completion_tokens": 700 if expanded else 300,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]

        answer = guard_output(str(answer))
        track_llm_run(
            "askbank.chat",
            provider=provider,
            model=settings.ollama_model if provider == "ollama" else model,
            input_text=message,
            output_text=answer,
        )
        return answer
