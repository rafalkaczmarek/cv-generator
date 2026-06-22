"""Shared LLM stub for agent unit tests."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM(Runnable[Any, FakeLLMResponse]):
    def __init__(self, payload: str) -> None:
        super().__init__()
        self.payload = payload

    def bind(self, **_kwargs: Any) -> FakeLLM:
        return self

    def invoke(
        self,
        _inputs: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> FakeLLMResponse:
        return FakeLLMResponse(self.payload)
