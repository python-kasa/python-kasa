"""EventBus fan-out semantics."""

from __future__ import annotations

from datetime import datetime

from gzplug.core.events import Event, EventBus, EventKind, Sample


def an_event(detail: str = "") -> Event:
    return Event(
        kind=EventKind.MESSAGE,
        timestamp=datetime.now().astimezone(),
        detail=detail,
    )


async def test_every_subscriber_gets_every_event(bus: EventBus):
    with bus.subscribe() as first, bus.subscribe() as second:
        bus.publish(an_event("hello"))
        assert first.get_nowait().detail == "hello"
        assert second.get_nowait().detail == "hello"


async def test_subscription_ends_with_the_context(bus: EventBus):
    with bus.subscribe():
        assert bus.subscriber_count == 1
    assert bus.subscriber_count == 0


async def test_a_full_subscriber_drops_rather_than_blocking(bus: EventBus):
    """A slow consumer must never stall the loop driving the bench."""
    with bus.subscribe(maxsize=1) as queue:
        bus.publish(an_event("kept"))
        bus.publish(an_event("dropped"))
        assert queue.qsize() == 1
        assert queue.get_nowait().detail == "kept"


async def test_publishing_with_no_subscribers_is_harmless(bus: EventBus):
    bus.publish(an_event())


def test_sample_defaults_to_all_unknown():
    sample = Sample()
    assert sample.is_on is None
    assert sample.power_w is None
