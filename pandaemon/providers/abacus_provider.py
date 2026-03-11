"""Abacus API provider — OpenAI-compatible interface tailored for Abacus Roteador."""

from __future__ import annotations

import json_repair
from typing import Any
from loguru import logger
from openai import AsyncOpenAI

from pandaemon.providers.base import LLMProvider, LLMResponse, ToolCallRequest

class AbacusProvider(LLMProvider):

    def __init__(
        self, 
        api_key: str | None = None, 
        api_base: str = "https://api.abacus.ai/api/v0/", 
        default_model: str = "abacus-router"
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        
        if not api_key:
            logger.warning("AbacusProvider initialized without an api_key. Requests will likely fail.")
            
        self._client = AsyncOpenAI(
            api_key=api_key or "no-key",
            base_url=api_base,
        )

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                   model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
                   reasoning_effort: str | None = None) -> LLMResponse:
        
        model_name = model or self.default_model
        
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": self._sanitize_empty_content(messages),
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }
        
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
            
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
            
        try:
            raw_response = await self._client.chat.completions.create(**kwargs)
            return self._parse_openai_response(raw_response)
        except Exception as e:
            logger.error(f"AbacusProvider error: {e}")
            return LLMResponse(content=f"Error calling Abacus API: {e}", finish_reason="error")

    def _parse_openai_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                # Handle potential JSON parsing issues robustly
                args_data = tc.function.arguments
                if isinstance(args_data, str):
                    try:
                        args_data = json_repair.loads(args_data)
                    except Exception:
                        args_data = {}
                        
                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id, 
                        name=tc.function.name,
                        arguments=args_data
                    )
                )

        u = response.usage
        usage_data = {}
        if u:
            usage_data = {
                "prompt_tokens": u.prompt_tokens, 
                "completion_tokens": getattr(u, "completion_tokens", 0), 
                "total_tokens": u.total_tokens
            }

        return LLMResponse(
            content=msg.content, 
            tool_calls=tool_calls, 
            finish_reason=choice.finish_reason or "stop",
            usage=usage_data,
            reasoning_content=getattr(msg, "reasoning_content", None),
        )

    def get_default_model(self) -> str:
        return self.default_model
