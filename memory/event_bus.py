"""In-process pub/sub for pushing live FleetMind events to the dashboard.

The supervisor publishes lifecycle updates (an event was received, agents are
running, the run completed) and any connected dashboard consumes them over the
Server-Sent Events endpoint `GET /events/live` (see `api/main.py`).

This is deliberately tiny and dependency-free: a list of asyncio queues, one
per connected client. `publish()` is synchronous and non-blocking so it can be
called from anywhere (sync agent code, async handlers) without awaiting. If no
dashboard is connected (e.g. during `tests/demo.py`), publishing is a no-op.
"""

import asyncio
from typing import Dict, List

_subscribers: List["asyncio.Queue[Dict]"] = []


def subscribe() -> "asyncio.Queue[Dict]":
    """Register a new SSE client and return its queue."""
    queue: "asyncio.Queue[Dict]" = asyncio.Queue()
    _subscribers.append(queue)
    return queue


def unsubscribe(queue: "asyncio.Queue[Dict]") -> None:
    """Drop a disconnected SSE client's queue."""
    if queue in _subscribers:
        _subscribers.remove(queue)


def publish(message: Dict) -> None:
    """Fan a message out to every connected dashboard, non-blocking."""
    for queue in list(_subscribers):
        try:
            queue.put_nowait(message)
        except Exception:
            # A full/closed queue should never break an agent run.
            pass


def subscriber_count() -> int:
    return len(_subscribers)
