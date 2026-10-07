"""Event Bus in‑process (pub/sub). O WebSocket e o engine Broadcast usam este evento."""

class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event_type: str, handler):
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler):
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event_type: str, data):
        for handler in self._handlers.get(event_type, []):
            try:
                handler(data)
            except Exception:
                pass  # handlers shouldn't crash the loop

event_bus = EventBus()