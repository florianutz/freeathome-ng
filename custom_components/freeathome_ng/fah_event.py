"""Helpers for free@home NG Home Assistant events."""

from __future__ import annotations

from typing import Any

DIMMING_STATUS_DEFAULT = "not_pressed"

DIMMING_STATUS_OPTIONS = [
    DIMMING_STATUS_DEFAULT,
    "pressed_up",
    "pressed_down",
    "held_up",
    "held_down",
]


def create_event_data(
    name: str,
    serialnumber: str,
    unique_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Build a `freeathome_ng_event` payload from a decoded datapoint event."""
    event_data: dict[str, Any] = {
        "name": name,
        "serialnumber": serialnumber,
        "unique_id": unique_id,
        "command": event["command"],
    }
    if "state" in event:
        event_data["state"] = event["state"]
    if "direction" in event:
        event_data["direction"] = event["direction"]
    return event_data


def dimming_status_from_event(event: dict[str, Any]) -> str | None:
    """Return one of the four visible dimming actions for an event."""
    if event.get("command") == "pressed":
        if event.get("state") is True:
            return "pressed_up"
        if event.get("state") is False:
            return "pressed_down"
    if event.get("command") == "dim_start":
        if event.get("direction") == "up":
            return "held_up"
        if event.get("direction") == "down":
            return "held_down"
    return None


def dimming_status_sequence_from_event(event: dict[str, Any]) -> tuple[str, ...]:
    """Return the status transitions produced by a datapoint event."""
    status = dimming_status_from_event(event)
    if event.get("command") == "pressed" and status is not None:
        return (status, DIMMING_STATUS_DEFAULT)
    if event.get("command") == "dim_start" and status is not None:
        return (status,)
    if event.get("command") == "dim_stop":
        return (DIMMING_STATUS_DEFAULT,)
    return ()
