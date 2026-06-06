"""In-process event dispatcher.

Subscribes a per-topic list of callbacks to the SNS publish history. Runs
in a daemon thread that polls every second. Each callback gets a fresh DB
session, fresh exception isolation, and its own timeout.

When we deploy and add Lambda subscribers via SNS subscriptions, this
in-process dispatcher stays as a backup so the demo + dev environments
never lose the side-effect chain.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.events.topics import TopicName
from app.integrations import sns_client

logger = logging.getLogger(__name__)


# A subscriber callback receives (event_body: dict, session_factory: callable).
# Subscribers MUST be idempotent — SNS does NOT guarantee exactly-once.
Subscriber = Callable[[dict, Callable], None]


@dataclass
class SubscriberRegistry:
    by_topic: dict[str, list[tuple[str, Subscriber]]] = field(default_factory=lambda: defaultdict(list))

    def register(self, topic: TopicName, name: str, fn: Subscriber) -> None:
        self.by_topic[topic.value].append((name, fn))

    def for_topic(self, full_topic: str) -> list[tuple[str, Subscriber]]:
        # We accept the FULL topic name (with prefix) but subscriptions are
        # registered against the short topic value — strip the prefix.
        short = full_topic
        if "-" in full_topic:
            # Strip prefix up to and including the LAST "bridge-os-" segment
            parts = full_topic.split("bridge-os-", 1)
            if len(parts) == 2:
                short = parts[1]
        return self.by_topic.get(short, [])


_registry = SubscriberRegistry()


def register_subscriber(topic: TopicName, *, name: str):
    """Decorator to register a function as a subscriber to a topic."""
    def _wrap(fn: Subscriber) -> Subscriber:
        _registry.register(topic, name, fn)
        return fn
    return _wrap


@dataclass
class DispatcherStats:
    delivered: int = 0
    failed: int = 0
    last_tick_at: Optional[float] = None


class EventDispatcher:
    """Drains the SNS publish history; routes new events to registered
    in-process subscribers."""

    def __init__(self, *, session_factory, poll_interval_seconds: float = 1.0) -> None:
        self._SessionLocal = session_factory
        self._poll_interval = poll_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # Track which message ids we've already delivered so we don't double-fire
        self._delivered_ids: set[str] = set()
        self._cursor: float = 0.0
        self.stats = DispatcherStats()

    def start(self) -> None:
        # Eagerly import so subscribers register themselves before the
        # first tick.
        from app.events import subscribers as _sub  # noqa: F401

        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._cursor = time.time()  # only deliver events newer than start
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="EventDispatcher"
        )
        self._thread.start()
        logger.info("EventDispatcher started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("EventDispatcher stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # pragma: no cover
                logger.exception("EventDispatcher tick raised")
            self._stop.wait(self._poll_interval)

    def _tick(self) -> None:
        events = sns_client.recent_events(limit=200)
        self.stats.last_tick_at = time.time()
        # Process oldest → newest so subscribers see causal order
        for ev in sorted(events, key=lambda e: e.published_at):
            if ev.message_id in self._delivered_ids:
                continue
            if ev.published_at < self._cursor:
                continue
            self._deliver(ev)
            self._delivered_ids.add(ev.message_id)

    def _deliver(self, ev) -> None:
        for name, fn in _registry.for_topic(ev.topic_name):
            try:
                fn(ev.body, self._SessionLocal)
                self.stats.delivered += 1
                logger.info(
                    "delivered %s → %s (mid=%s)", ev.topic_name, name, ev.message_id
                )
            except Exception:
                self.stats.failed += 1
                logger.exception(
                    "subscriber %s failed on event %s", name, ev.message_id
                )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_dispatcher: Optional[EventDispatcher] = None
_dispatcher_lock = threading.Lock()


def get_dispatcher() -> Optional[EventDispatcher]:
    return _dispatcher


def start_dispatcher(session_factory) -> EventDispatcher:
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is None:
            _dispatcher = EventDispatcher(session_factory=session_factory)
            _dispatcher.start()
    return _dispatcher


def stop_dispatcher() -> None:
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is not None:
            _dispatcher.stop()
            _dispatcher = None


def list_subscribers() -> dict:
    """Used by /system/events/topics."""
    out: dict[str, list[str]] = {}
    for topic, subs in _registry.by_topic.items():
        out[topic] = [name for name, _ in subs]
    return out
