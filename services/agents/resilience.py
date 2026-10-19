"""Failure handling for agent calls: time budgets, per-agent circuit breakers and the
Director panel's chaos switch."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")

FAILURES_TO_OPEN = 3
FAILURE_WINDOW_S = 60.0
OPEN_FOR_S = 30.0


class AgentUnavailableError(Exception):
    """The agent was not called: its breaker is open or the chaos switch killed it."""

    def __init__(self, agent: str, status: str) -> None:
        super().__init__(f"{agent}: {status}")
        self.status = status


@dataclass
class CircuitBreaker:
    """Opens after FAILURES_TO_OPEN failures within FAILURE_WINDOW_S; stays open OPEN_FOR_S,
    then lets one call through (half-open) and closes again on success."""

    clock: Callable[[], float] = time.monotonic
    failures: list[float] = field(default_factory=list)
    open_until: float = 0.0

    def allow(self) -> bool:
        return self.clock() >= self.open_until

    @property
    def is_open(self) -> bool:
        return not self.allow()

    def success(self) -> None:
        self.failures.clear()

    def failure(self) -> None:
        now = self.clock()
        self.failures = [t for t in self.failures if now - t < FAILURE_WINDOW_S] + [now]
        if len(self.failures) >= FAILURES_TO_OPEN:
            self.open_until = now + OPEN_FOR_S
            self.failures.clear()


@dataclass
class ChaosSwitch:
    """Kill an agent for a while (the demo's 'kill the Narrator for 20 s'), or make the
    next few cards carry a wrong number so the Fact Checker has something to catch."""

    clock: Callable[[], float] = time.monotonic
    killed_until: dict[str, float] = field(default_factory=dict)
    wrong_numbers: int = 0

    def kill(self, agent: str, seconds: float) -> float:
        until = self.clock() + seconds
        self.killed_until[agent] = until
        return until

    def is_killed(self, agent: str) -> bool:
        return self.clock() < self.killed_until.get(agent, 0.0)

    def take_wrong_number(self) -> bool:
        if self.wrong_numbers > 0:
            self.wrong_numbers -= 1
            return True
        return False

    def status(self) -> dict[str, object]:
        now = self.clock()
        return {
            "killed": {a: round(u - now, 1) for a, u in self.killed_until.items() if u > now},
            "wrong_numbers_pending": self.wrong_numbers,
        }


class Guard:
    """Runs agent calls under a time budget, a circuit breaker per agent and the chaos switch."""

    def __init__(self, timeout_s: float, chaos: ChaosSwitch | None = None) -> None:
        self.timeout_s = timeout_s
        self.chaos = chaos or ChaosSwitch()
        self.breakers: dict[str, CircuitBreaker] = {}

    def breaker(self, agent: str) -> CircuitBreaker:
        return self.breakers.setdefault(agent, CircuitBreaker())

    async def call(
        self,
        agent: str,
        fn: Callable[[], Awaitable[T]],
        *,
        soft_s: float | None = None,
        hard_s: float | None = None,
        on_slow: Callable[[], Awaitable[None]] | None = None,
    ) -> T:
        """Await fn() under the agent's breaker and the chaos switch.

        After soft_s (default: the 4 s budget) `on_slow` runs once (it publishes the
        stats-only card), and the call keeps going until hard_s, so a late answer can still
        upgrade that card. Raises AgentUnavailableError, TimeoutError or the call's error.
        """
        if self.chaos.is_killed(agent):
            raise AgentUnavailableError(agent, "chaos switch")
        breaker = self.breaker(agent)
        if not breaker.allow():
            raise AgentUnavailableError(agent, "circuit open")
        soft = self.timeout_s if soft_s is None else soft_s
        hard = max(soft, hard_s if hard_s is not None else soft * 4)
        task = asyncio.ensure_future(fn())
        try:
            done, _ = await asyncio.wait({task}, timeout=soft)
            if not done:
                if on_slow is not None:
                    await on_slow()
                done, _ = await asyncio.wait({task}, timeout=hard - soft)
            if not done:
                task.cancel()
                raise TimeoutError(f"{agent} took longer than {hard:g} s")
            result = task.result()
        except asyncio.CancelledError:
            task.cancel()
            raise
        except Exception:
            if not task.done():
                task.cancel()
            breaker.failure()
            raise
        breaker.success()
        return result
