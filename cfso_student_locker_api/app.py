#!/usr/bin/env python3
"""Independent mock of the CFSO Student Locker System."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from mock_http import Actor, Api, ApiError, JsonStore, now_iso, object_schema, path_parameter, query_parameter


ROOT = Path(__file__).resolve().parent
STORE = JsonStore(ROOT / "data" / "seed.json")
TOKENS = {"polygate-student-demo": Actor("student-1001", "student"), "polygate-organizer-demo": Actor("organizer-1001", "organizer")}
API = Api("Mock CFSO Student Locker API", "cfso-student-locker-api")


def locker(data, locker_id):
    item = next((x for x in data["lockers"] if x["locker_id"] == locker_id), None)
    if item is None:
        raise ApiError(404, "locker_not_found", f"Unknown locker_id: {locker_id}")
    return item


def application(data, application_id, owner_id):
    item = next((x for x in data["applications"] if x["application_id"] == application_id), None)
    if item is None or item["owner_id"] != owner_id:
        raise ApiError(404, "application_not_found", f"Unknown application_id: {application_id}")
    return item


def list_periods(request, store):
    with store.lock:
        return {"periods": store.data["periods"]}


def list_lockers(request, store):
    with store.lock:
        items = list(store.data["lockers"])
        for field in ("building", "size", "status"):
            if request.one(field):
                items = [x for x in items if x[field].lower() == request.one(field).lower()]
        if request.one("accessible") is not None:
            wanted = request.one("accessible").lower() in {"1", "true", "yes"}
            items = [x for x in items if x["accessible"] == wanted]
        return {"count": len(items), "lockers": items}


def get_locker(request, store):
    with store.lock:
        return {"locker": locker(store.data, request.params["locker_id"])}


def list_applications(request, store):
    with store.lock:
        items = [x for x in store.data["applications"] if x["owner_id"] == request.actor.actor_id]
        return {"count": len(items), "applications": items}


def create_application(request, store):
    request.require("period_id", "size_preference", "building_preferences")
    if not isinstance(request.body["building_preferences"], list) or not request.body["building_preferences"]:
        raise ApiError(400, "invalid_preference", "building_preferences must be a non-empty array")
    with store.lock:
        if not any(x["period_id"] == request.body["period_id"] and x["status"] == "open" for x in store.data["periods"]):
            raise ApiError(409, "period_closed", "The application period is not open")
        active = [x for x in store.data["applications"] if x["owner_id"] == request.actor.actor_id and x["period_id"] == request.body["period_id"] and x["status"] not in {"cancelled", "rejected"}]
        if active:
            raise ApiError(409, "duplicate_application", "An active application already exists", {"application_id": active[0]["application_id"]})
        item = {
            "application_id": f"locker-app-{store.data['next_application_id']:04d}",
            "owner_id": request.actor.actor_id,
            "period_id": request.body["period_id"],
            "size_preference": request.body["size_preference"],
            "building_preferences": request.body["building_preferences"],
            "accessibility_required": bool(request.body.get("accessibility_required", False)),
            "status": "draft",
            "created_at": now_iso(),
            "offered_locker_id": None,
        }
        store.data["next_application_id"] += 1
        store.data["applications"].append(item)
        return 201, {"application": item}


def get_application(request, store):
    with store.lock:
        return {"application": application(store.data, request.params["application_id"], request.actor.actor_id)}


def update_application(request, store):
    allowed = {"size_preference", "building_preferences", "accessibility_required"}
    if set(request.body) - allowed:
        raise ApiError(400, "unknown_field", "Only locker preferences can be changed")
    with store.lock:
        item = application(store.data, request.params["application_id"], request.actor.actor_id)
        if item["status"] != "draft":
            raise ApiError(409, "application_not_editable", "Only draft applications can be changed")
        item.update(request.body); item["updated_at"] = now_iso()
        return {"application": item}


def submit_application(request, store):
    with store.lock:
        item = application(store.data, request.params["application_id"], request.actor.actor_id)
        if item["status"] != "draft":
            raise ApiError(409, "invalid_status", "Only a draft application can be submitted")
        buildings = item["building_preferences"]
        available = [x for x in store.data["lockers"] if x["status"] == "available" and x["size"] == item["size_preference"] and x["building"] in buildings and (not item["accessibility_required"] or x["accessible"])]
        if available:
            selected = sorted(available, key=lambda x: buildings.index(x["building"]))[0]
            selected["status"] = "held"
            item["status"] = "offered"; item["offered_locker_id"] = selected["locker_id"]
        else:
            item["status"] = "waitlisted"
        item["submitted_at"] = now_iso()
        return {"application": item}


def accept_offer(request, store):
    with store.lock:
        item = application(store.data, request.params["application_id"], request.actor.actor_id)
        if item["status"] != "offered":
            raise ApiError(409, "no_active_offer", "The application has no offer to accept")
        selected = locker(store.data, item["offered_locker_id"])
        if selected["status"] != "held":
            raise ApiError(409, "offer_unavailable", "The held locker is no longer available")
        selected["status"] = "assigned"; selected["assigned_to"] = request.actor.actor_id
        item["status"] = "accepted"; item["accepted_at"] = now_iso()
        return {"application": item, "locker": selected}


def cancel_application(request, store):
    with store.lock:
        item = application(store.data, request.params["application_id"], request.actor.actor_id)
        if item["status"] == "cancelled":
            return {"application": item}
        if item.get("offered_locker_id"):
            selected = locker(store.data, item["offered_locker_id"])
            if selected.get("assigned_to") in (None, request.actor.actor_id):
                selected["status"] = "available"; selected.pop("assigned_to", None)
        item["status"] = "cancelled"; item["cancelled_at"] = now_iso()
        return {"application": item}


app_schema = object_schema(["period_id", "size_preference", "building_preferences"], {
    "period_id": {"type": "string"}, "size_preference": {"type": "string", "enum": ["small", "medium", "large"]},
    "building_preferences": {"type": "array", "items": {"type": "string"}}, "accessibility_required": {"type": "boolean"}
})
aid = [path_parameter("application_id", "Locker application identifier")]
API.route("GET", r"/v1/locker-periods", "/v1/locker-periods", list_periods, operation_id="listLockerPeriods", summary="List application periods")
API.route("GET", r"/v1/lockers", "/v1/lockers", list_lockers, operation_id="searchLockers", summary="Search lockers", parameters=[query_parameter("building", "Exact building"), query_parameter("size", "Locker size"), query_parameter("status", "Availability status"), query_parameter("accessible", "Whether an accessible locker is required", "boolean")])
API.route("GET", r"/v1/lockers/(?P<locker_id>[^/]+)", "/v1/lockers/{locker_id}", get_locker, operation_id="getLocker", summary="Get locker details", parameters=[path_parameter("locker_id", "Locker identifier")])
API.route("GET", r"/v1/locker-applications", "/v1/locker-applications", list_applications, operation_id="listMyLockerApplications", summary="List the current user's locker applications")
API.route("POST", r"/v1/locker-applications", "/v1/locker-applications", create_application, operation_id="createLockerApplication", summary="Create a draft locker application", request_schema=app_schema)
API.route("GET", r"/v1/locker-applications/(?P<application_id>[^/]+)", "/v1/locker-applications/{application_id}", get_application, operation_id="getLockerApplication", summary="Get a locker application", parameters=aid)
API.route("PATCH", r"/v1/locker-applications/(?P<application_id>[^/]+)", "/v1/locker-applications/{application_id}", update_application, operation_id="updateLockerApplication", summary="Update draft preferences", parameters=aid, request_schema={**app_schema, "required": []})
API.route("POST", r"/v1/locker-applications/(?P<application_id>[^/]+)/submit", "/v1/locker-applications/{application_id}/submit", submit_application, operation_id="submitLockerApplication", summary="Submit an application and obtain an offer or waitlist status", parameters=aid, request_schema={"type": "object", "properties": {}, "additionalProperties": False})
API.route("POST", r"/v1/locker-applications/(?P<application_id>[^/]+)/accept", "/v1/locker-applications/{application_id}/accept", accept_offer, operation_id="acceptLockerOffer", summary="Accept an offered locker", parameters=aid, request_schema={"type": "object", "properties": {}, "additionalProperties": False})
API.route("DELETE", r"/v1/locker-applications/(?P<application_id>[^/]+)", "/v1/locker-applications/{application_id}", cancel_application, operation_id="cancelLockerApplication", summary="Cancel an application or release an assignment", parameters=aid)


Handler = API.make_handler(STORE, TOKENS)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", default=8102, type=int); args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler); print(f"Mock CFSO Student Locker API listening on http://{args.host}:{args.port}"); server.serve_forever()


if __name__ == "__main__": main()
