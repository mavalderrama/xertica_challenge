from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    def __init__(self, llm: Any, tracer: Any) -> None:
        self.llm = llm
        self.tracer = tracer

    @abstractmethod
    async def run(self, state: dict) -> dict:
        pass
