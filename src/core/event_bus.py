"""
EventBus - Decoupled Pub/Sub Broker for AI Operating System.
Allows agents, tools, and managers to communicate via events without direct coupling.
"""

import asyncio
import logging
from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger("event_bus")

@dataclass
class Event:
    topic: str
    data: Dict[str, Any]
    sender: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._history: List[Event] = []
        self._dead_letters: List[Dict[str, Any]] = []

    def subscribe(self, topic: str, callback: Callable[[Event], Any]):
        """Subscribe a callback function to a topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)
        log.debug(f"Subscribed to '{topic}': {callback}")

    def unsubscribe(self, topic: str, callback: Callable[[Event], Any]):
        """Unsubscribe a callback from a topic."""
        if topic in self._subscribers and callback in self._subscribers[topic]:
            self._subscribers[topic].remove(callback)

    async def publish(self, topic: str, data: Dict[str, Any], sender: str = "system"):
        """Publish an event to all subscribers of a topic."""
        event = Event(topic=topic, data=data, sender=sender)
        self._history.append(event)
        
        # Keep history capped at 1000 events to conserve memory
        if len(self._history) > 1000:
            self._history.pop(0)

        subscribers = self._subscribers.get(topic, []) + self._subscribers.get("*", [])
        log.info(f"[EventBus] Topic: '{topic}' | Sender: '{sender}' | Subscribers: {len(subscribers)}")

        for cb in subscribers:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception as e:
                log.error(f"[EventBus Error] Subscriber failed on topic '{topic}': {e}")
                self._dead_letters.append({
                    "topic": topic,
                    "sender": sender,
                    "error": str(e),
                    "timestamp": event.timestamp
                })
                # Cap dead-letter queue at 200
                if len(self._dead_letters) > 200:
                    self._dead_letters.pop(0)

    def get_history(self, topic_filter: str = None) -> List[Event]:
        """Return event history, optionally filtered by topic."""
        if not topic_filter:
            return list(self._history)
        return [e for e in self._history if e.topic == topic_filter]

    def get_dead_letters(self) -> List[Dict[str, Any]]:
        """Return events whose subscriber callbacks failed."""
        return list(self._dead_letters)

    def clear_history(self):
        """Clear event history and dead-letter queue. Used for test isolation."""
        self._history.clear()
        self._dead_letters.clear()

# Global singleton instance
bus = EventBus()

