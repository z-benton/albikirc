from __future__ import annotations

from typing import Callable, Any


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        return callback

    def unsubscribe(self, event_type: str, callback: Callable):
        subscribers = self._subscribers.get(event_type)
        if not subscribers:
            return
        try:
            subscribers.remove(callback)
        except ValueError:
            return
        if not subscribers:
            self._subscribers.pop(event_type, None)

    def publish(self, event_type: str, *args: Any, **kwargs: Any):
        if event_type in self._subscribers:
            for callback in list(self._subscribers[event_type]):
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error in event handler for {event_type}: {e}")

event_bus = EventBus()
