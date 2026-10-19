"""The crew: seven Agent Framework agents, their models and their MCP tools.

Models are Microsoft Foundry deployments in Azure (FOUNDRY_ENDPOINT, MODEL_LARGE,
MODEL_SMALL), any OpenAI-compatible endpoint locally, or the offline mock. Agents that read
numbers get an MCPStreamableHTTPTool for the Match Stats MCP server, limited to the tools
their prompt lists. A function middleware records every MCP result an agent receives, so
the Fact Checker can check cards against exactly what the writers saw.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx
from agent_framework import Agent, FunctionInvocationContext, MCPStreamableHTTPTool
from agent_framework import function_middleware as as_function_middleware
from pydantic import BaseModel

from agents import prompts
from agents.mock_llm import MockChatClient
from agents.resilience import ChaosSwitch, Guard
from agents.stats_client import StatsClient
from agents.tracing import Step, Tracer
from runtime.bus import Bus
from runtime.config import Settings
from runtime.store import Store

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

HARD_TIMEOUT_S = 20.0


@dataclass
class RunRecord:
    """MCP tool calls made during one agent run."""

    calls: list[tuple[str, dict[str, Any], Any]] = field(default_factory=list)

    def tools(self) -> list[str]:
        return [name for name, _, _ in self.calls]

    def payloads(self) -> list[Any]:
        return [result for _, _, result in self.calls]


CURRENT_RUN: ContextVar[RunRecord | None] = ContextVar("pitchside_agent_run", default=None)


def _parse_result(result: Any) -> Any:
    """Tool results arrive as Agent Framework content; recover the JSON the server sent."""
    if isinstance(result, list):
        texts = [getattr(c, "text", None) for c in result]
        text = "".join(t for t in texts if t)
    else:
        text = str(result) if result is not None else ""
    try:
        value = json.loads(text)
    except ValueError:
        return text
    if isinstance(value, dict) and set(value) == {"result"}:
        return value["result"]
    return value


@as_function_middleware
async def record_tool_calls(
    context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
) -> None:
    await call_next()
    record = CURRENT_RUN.get()
    if record is not None:
        args = dict(context.arguments) if isinstance(context.arguments, dict) else {}
        record.calls.append((context.function.name, args, _parse_result(context.result)))


def chat_client(settings: Settings, size: str, role: str) -> Any:
    deployment = settings.model_large if size == "large" else settings.model_small
    if settings.llm == "mock":
        return MockChatClient(role, model=f"mock-{size}")
    if settings.llm == "openai":
        from agent_framework.openai import OpenAIChatCompletionClient

        return OpenAIChatCompletionClient(
            model=deployment,
            base_url=settings.openai_compat_base_url,
            api_key=settings.openai_compat_api_key or "not-needed",
        )
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    return FoundryChatClient(
        project_endpoint=settings.foundry_endpoint,
        model=deployment,
        credential=DefaultAzureCredential(),
    )


class Crew:
    """Agents plus what they share: guard (timeouts, breakers, chaos), tracer, MCP client."""

    def __init__(
        self,
        settings: Settings,
        bus: Bus,
        store: Store,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.store = store
        self.chaos = ChaosSwitch()
        self.guard = Guard(settings.model_timeout_s, self.chaos)
        self.tracer = Tracer(bus, store)
        self.http_client = http_client  # tests: reach the MCP server in-process
        self.stats = StatsClient(settings.mcp_url, http_client=http_client)
        self.agents: dict[str, Agent] = {}
        self.prompts = {name: prompts.load(name) for name in prompts.AGENTS}

    def model_name(self, agent: str) -> str:
        size = self.prompts[agent].model
        if self.settings.llm == "mock":
            return f"mock-{size}"
        return self.settings.model_large if size == "large" else self.settings.model_small

    async def start(self) -> None:
        for name, prompt in self.prompts.items():
            tools = []
            if prompt.tools:
                tools.append(
                    MCPStreamableHTTPTool(
                        name="match_stats",
                        url=self.settings.mcp_url,
                        allowed_tools=list(prompt.tools),
                        load_prompts=False,
                        request_timeout=10,
                        http_client=self.http_client,
                    )
                )
            agent = Agent(
                client=chat_client(self.settings, prompt.model, name),
                instructions=prompt.text,
                name=name,
                description=f"Pitchside AI {name.replace('_', ' ')} ({prompt.ref})",
                tools=tools or None,
                middleware=[record_tool_calls],
                default_options={"temperature": 0.4} if self.settings.llm != "mock" else None,
            )
            await agent.open()
            self.agents[name] = agent
        await self.stats.connect()

    async def close(self) -> None:
        for agent in self.agents.values():
            try:
                await agent.close()
            except Exception:
                log.exception("closing agent %s", agent.name)
        await self.stats.close()

    async def run(
        self,
        agent: str,
        task: str,
        payload: dict[str, Any],
        output: type[T],
        step: Step,
        *,
        on_slow: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[T, RunRecord]:
        """Run one agent on a JSON payload and parse its structured output.

        Raises AgentUnavailableError, TimeoutError or the model/parse error; the caller turns
        those into a fallback and a trace status.
        """
        record = RunRecord()
        text = f"{task}\n\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

        async def call() -> Any:
            token = CURRENT_RUN.set(record)
            try:
                return await self.agents[agent].run(text, options={"response_format": output})
            finally:
                CURRENT_RUN.reset(token)

        try:
            response = await self.guard.call(agent, call, hard_s=HARD_TIMEOUT_S, on_slow=on_slow)
        finally:
            step.tools = record.tools()
        value = response.value
        if not isinstance(value, output):
            value = output.model_validate_json(response.text)
        return value, record
