#!/usr/bin/env python3
"""Independent mock of the CDO Room Booking System."""

from __future__ import annotations

import argparse
from datetime import date, time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mock_http import Actor, Api, ApiError, JsonStore, now_iso, object_schema, path_parameter, query_parameter


ROOT = Path(__file__).resolve().parent
STORE = JsonStore(ROOT / "data" / "seed.json")
TOKENS = {
    "polygate-student-demo": Actor("student-1001", "student"),
    "polygate-organizer-demo": Actor("organizer-1001", "organizer"),
}
API = Api("Mock CDO Room Booking API", "cdo-room-booking-api")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_time(value: str) -> time:
    return time.fromisoformat(value)


def ensure_interval(day: str, start: str, end: str) -> None:
    parse_date(day)
    if parse_time(start) >= parse_time(end):
        raise ApiError(400, "invalid_interval", "start_time must be earlier than end_time")


def overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return parse_time(a_start) < parse_time(b_end) and parse_time(b_start) < parse_time(a_end)


def room_by_id(data: dict[str, Any], room_id: str) -> dict[str, Any]:
    room = next((item for item in data["rooms"] if item["room_id"] == room_id), None)
    if room is None:
        raise ApiError(404, "room_not_found", f"Unknown room_id: {room_id}")
    return room


def booking_by_id(data: dict[str, Any], booking_id: str, actor_id: str) -> dict[str, Any]:
    booking = next((item for item in data["bookings"] if item["booking_id"] == booking_id), None)
    if booking is None or booking["owner_id"] != actor_id:
        raise ApiError(404, "booking_not_found", f"Unknown booking_id: {booking_id}")
    return booking


def conflicts(data: dict[str, Any], room_id: str, day: str, start: str, end: str, exclude: str | None = None):
    return [
        item
        for item in data["bookings"]
        if item["booking_id"] != exclude
        and item["room_id"] == room_id
        and item["date"] == day
        and item["status"] != "cancelled"
        and overlaps(item["start_time"], item["end_time"], start, end)
    ]


def list_rooms(request, store):
    with store.lock:
        rooms = []
        capacity_min = int(request.one("capacity_min", "0"))
        required_features = {v.strip().lower() for v in (request.one("features", "") or "").split(",") if v.strip()}
        day, start, end = request.one("date"), request.one("start_time"), request.one("end_time")
        if any((day, start, end)) and not all((day, start, end)):
            raise ApiError(400, "missing_parameter", "date, start_time, and end_time must be supplied together")
        if day and start and end:
            ensure_interval(day, start, end)
        for room in store.data["rooms"]:
            if request.one("campus") and room["campus"].lower() != request.one("campus").lower():
                continue
            if room["capacity"] < capacity_min or not required_features.issubset({x.lower() for x in room["features"]}):
                continue
            copy = dict(room)
            if day and start and end:
                copy["available"] = not conflicts(store.data, room["room_id"], day, start, end)
            rooms.append(copy)
        return {"count": len(rooms), "rooms": rooms}


def get_room(request, store):
    with store.lock:
        return {"room": room_by_id(store.data, request.params["room_id"])}


def availability(request, store):
    day, start, end = request.one("date"), request.one("start_time"), request.one("end_time")
    if not all((day, start, end)):
        raise ApiError(400, "missing_parameter", "date, start_time, and end_time are required")
    ensure_interval(day, start, end)
    with store.lock:
        room_by_id(store.data, request.params["room_id"])
        found = conflicts(store.data, request.params["room_id"], day, start, end)
        return {"room_id": request.params["room_id"], "date": day, "start_time": start, "end_time": end, "available": not found, "conflicts": found}


def list_bookings(request, store):
    with store.lock:
        items = [item for item in store.data["bookings"] if item["owner_id"] == request.actor.actor_id]
        if request.one("status"):
            items = [item for item in items if item["status"] == request.one("status")]
        return {"count": len(items), "bookings": items}


def create_booking(request, store):
    request.require("room_id", "date", "start_time", "end_time", "purpose", "attendee_count")
    ensure_interval(request.body["date"], request.body["start_time"], request.body["end_time"])
    with store.lock:
        room = room_by_id(store.data, request.body["room_id"])
        attendees = int(request.body["attendee_count"])
        if attendees < 1 or attendees > room["capacity"]:
            raise ApiError(400, "invalid_attendee_count", f"attendee_count must be 1 to {room['capacity']}")
        found = conflicts(store.data, room["room_id"], request.body["date"], request.body["start_time"], request.body["end_time"])
        if found:
            raise ApiError(409, "room_unavailable", "The requested room is not available", found)
        booking = {
            "booking_id": f"booking-{store.data['next_booking_id']:04d}",
            "owner_id": request.actor.actor_id,
            "room_id": room["room_id"],
            "date": request.body["date"],
            "start_time": request.body["start_time"],
            "end_time": request.body["end_time"],
            "purpose": str(request.body["purpose"]),
            "attendee_count": attendees,
            "status": "confirmed",
            "created_at": now_iso(),
        }
        store.data["next_booking_id"] += 1
        store.data["bookings"].append(booking)
        return 201, {"booking": booking}


def get_booking(request, store):
    with store.lock:
        return {"booking": booking_by_id(store.data, request.params["booking_id"], request.actor.actor_id)}


def update_booking(request, store):
    allowed = {"room_id", "date", "start_time", "end_time", "purpose", "attendee_count"}
    unknown = set(request.body) - allowed
    if unknown:
        raise ApiError(400, "unknown_field", f"Unsupported field(s): {', '.join(sorted(unknown))}")
    with store.lock:
        booking = booking_by_id(store.data, request.params["booking_id"], request.actor.actor_id)
        if booking["status"] != "confirmed":
            raise ApiError(409, "booking_not_editable", "Only confirmed bookings can be changed")
        candidate = {**booking, **request.body}
        ensure_interval(candidate["date"], candidate["start_time"], candidate["end_time"])
        room = room_by_id(store.data, candidate["room_id"])
        candidate["attendee_count"] = int(candidate["attendee_count"])
        if candidate["attendee_count"] < 1 or candidate["attendee_count"] > room["capacity"]:
            raise ApiError(400, "invalid_attendee_count", f"attendee_count must be 1 to {room['capacity']}")
        found = conflicts(store.data, room["room_id"], candidate["date"], candidate["start_time"], candidate["end_time"], booking["booking_id"])
        if found:
            raise ApiError(409, "room_unavailable", "The revised time is unavailable", found)
        booking.update({key: candidate[key] for key in allowed})
        booking["updated_at"] = now_iso()
        return {"booking": booking}


def cancel_booking(request, store):
    with store.lock:
        booking = booking_by_id(store.data, request.params["booking_id"], request.actor.actor_id)
        if booking["status"] == "cancelled":
            return {"booking": booking}
        booking["status"] = "cancelled"
        booking["cancelled_at"] = now_iso()
        return {"booking": booking}


room_id_param = [path_parameter("room_id", "Room identifier")]
booking_id_param = [path_parameter("booking_id", "Booking identifier")]
booking_schema = object_schema(
    ["room_id", "date", "start_time", "end_time", "purpose", "attendee_count"],
    {
        "room_id": {"type": "string", "examples": ["BC-302"]},
        "date": {"type": "string", "format": "date"},
        "start_time": {"type": "string", "examples": ["12:00"]},
        "end_time": {"type": "string", "examples": ["13:00"]},
        "purpose": {"type": "string"},
        "attendee_count": {"type": "integer", "minimum": 1},
    },
)
API.route("GET", r"/v1/rooms", "/v1/rooms", list_rooms, operation_id="searchRooms", summary="Search rooms", description="Filter rooms and optionally calculate availability for a requested interval.", parameters=[query_parameter("campus", "Exact campus name"), query_parameter("capacity_min", "Minimum seats", "integer"), query_parameter("features", "Comma-separated required features"), query_parameter("date", "Availability date"), query_parameter("start_time", "Availability start time"), query_parameter("end_time", "Availability end time")])
API.route("GET", r"/v1/rooms/(?P<room_id>[^/]+)", "/v1/rooms/{room_id}", get_room, operation_id="getRoom", summary="Get room details", parameters=room_id_param)
API.route("GET", r"/v1/rooms/(?P<room_id>[^/]+)/availability", "/v1/rooms/{room_id}/availability", availability, operation_id="checkRoomAvailability", summary="Check room availability", parameters=room_id_param + [query_parameter("date", "Booking date", required=True), query_parameter("start_time", "Start time", required=True), query_parameter("end_time", "End time", required=True)])
API.route("GET", r"/v1/bookings", "/v1/bookings", list_bookings, operation_id="listMyBookings", summary="List the current user's bookings", parameters=[query_parameter("status", "Optional status filter")])
API.route("POST", r"/v1/bookings", "/v1/bookings", create_booking, operation_id="createBooking", summary="Create a confirmed booking", request_schema=booking_schema)
API.route("GET", r"/v1/bookings/(?P<booking_id>[^/]+)", "/v1/bookings/{booking_id}", get_booking, operation_id="getBooking", summary="Get one booking", parameters=booking_id_param)
API.route("PATCH", r"/v1/bookings/(?P<booking_id>[^/]+)", "/v1/bookings/{booking_id}", update_booking, operation_id="updateBooking", summary="Change a confirmed booking", parameters=booking_id_param, request_schema={**booking_schema, "required": []})
API.route("DELETE", r"/v1/bookings/(?P<booking_id>[^/]+)", "/v1/bookings/{booking_id}", cancel_booking, operation_id="cancelBooking", summary="Cancel a booking", parameters=booking_id_param)


Handler = API.make_handler(STORE, TOKENS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock CDO Room Booking API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8101, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mock CDO Room Booking API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
