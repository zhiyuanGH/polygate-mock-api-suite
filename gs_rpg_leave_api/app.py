#!/usr/bin/env python3
"""Independent mock of the GS RPg Leave Management System."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from mock_http import Actor, Api, ApiError, JsonStore, now_iso, object_schema, path_parameter, query_parameter


ROOT = Path(__file__).resolve().parent
STORE = JsonStore(ROOT / "data" / "seed.json")
TOKENS = {"polygate-student-demo": Actor("student-1001", "student"), "polygate-organizer-demo": Actor("organizer-1001", "organizer")}
API = Api("Mock GS RPg Leave API", "gs-rpg-leave-api")


def leave_type(data, type_id):
    item = next((x for x in data["leave_types"] if x["leave_type_id"] == type_id), None)
    if item is None: raise ApiError(404, "leave_type_not_found", f"Unknown leave_type_id: {type_id}")
    return item


def application(data, application_id, owner_id):
    item = next((x for x in data["applications"] if x["application_id"] == application_id), None)
    if item is None or item["owner_id"] != owner_id: raise ApiError(404, "application_not_found", f"Unknown application_id: {application_id}")
    return item


def working_days(start_value, end_value):
    start, end = date.fromisoformat(start_value), date.fromisoformat(end_value)
    if start > end: raise ApiError(400, "invalid_date_range", "start_date must not be after end_date")
    days, cursor = 0, start
    while cursor <= end:
        if cursor.weekday() < 5: days += 1
        cursor += timedelta(days=1)
    return days


def overlap(a_start, a_end, b_start, b_end):
    return date.fromisoformat(a_start) <= date.fromisoformat(b_end) and date.fromisoformat(b_start) <= date.fromisoformat(a_end)


def balance_for(data, owner_id, type_id):
    entitlement = data["entitlements"].get(owner_id, {}).get(type_id, 0)
    relevant = [x for x in data["applications"] if x["owner_id"] == owner_id and x["leave_type_id"] == type_id]
    used = sum(x["working_days"] for x in relevant if x["status"] == "approved")
    pending = sum(x["working_days"] for x in relevant if x["status"] == "submitted")
    return {"leave_type_id": type_id, "entitlement_days": entitlement, "used_days": used, "pending_days": pending, "available_days": entitlement - used - pending}


def list_types(request, store):
    with store.lock: return {"leave_types": store.data["leave_types"]}


def list_balances(request, store):
    with store.lock: return {"balances": [balance_for(store.data, request.actor.actor_id, x["leave_type_id"]) for x in store.data["leave_types"]]}


def list_applications(request, store):
    with store.lock:
        items=[x for x in store.data["applications"] if x["owner_id"]==request.actor.actor_id]
        if request.one("status"): items=[x for x in items if x["status"]==request.one("status")]
        return {"count":len(items),"applications":items}


def create_application(request, store):
    request.require("leave_type_id","start_date","end_date","reason","contact_during_leave")
    days=working_days(request.body["start_date"],request.body["end_date"])
    with store.lock:
        policy=leave_type(store.data,request.body["leave_type_id"])
        if days<1 or days>policy["max_consecutive_days"]: raise ApiError(400,"invalid_duration",f"Leave must contain 1 to {policy['max_consecutive_days']} working days")
        item={"application_id":f"leave-app-{store.data['next_application_id']:04d}","owner_id":request.actor.actor_id,"leave_type_id":policy["leave_type_id"],"start_date":request.body["start_date"],"end_date":request.body["end_date"],"working_days":days,"reason":request.body["reason"],"contact_during_leave":request.body["contact_during_leave"],"document_refs":request.body.get("document_refs",[]),"status":"draft","created_at":now_iso()}
        store.data["next_application_id"]+=1; store.data["applications"].append(item); return 201,{"application":item}


def get_application(request, store):
    with store.lock: return {"application":application(store.data,request.params["application_id"],request.actor.actor_id)}


def update_application(request, store):
    allowed={"leave_type_id","start_date","end_date","reason","contact_during_leave","document_refs"}
    if set(request.body)-allowed: raise ApiError(400,"unknown_field","Only draft application fields can be changed")
    with store.lock:
        item=application(store.data,request.params["application_id"],request.actor.actor_id)
        if item["status"]!="draft": raise ApiError(409,"application_not_editable","Only draft applications can be changed")
        candidate={**item,**request.body}; policy=leave_type(store.data,candidate["leave_type_id"]); days=working_days(candidate["start_date"],candidate["end_date"])
        if days<1 or days>policy["max_consecutive_days"]: raise ApiError(400,"invalid_duration",f"Leave must contain 1 to {policy['max_consecutive_days']} working days")
        item.update(request.body); item["working_days"]=days; item["updated_at"]=now_iso(); return {"application":item}


def submit_application(request, store):
    with store.lock:
        item=application(store.data,request.params["application_id"],request.actor.actor_id)
        if item["status"]!="draft": raise ApiError(409,"invalid_status","Only a draft application can be submitted")
        conflicts=[x for x in store.data["applications"] if x["owner_id"]==request.actor.actor_id and x["application_id"]!=item["application_id"] and x["status"] in {"submitted","approved"} and overlap(x["start_date"],x["end_date"],item["start_date"],item["end_date"])]
        if conflicts: raise ApiError(409,"overlapping_leave","The dates overlap another leave application",{"application_id":conflicts[0]["application_id"]})
        policy=leave_type(store.data,item["leave_type_id"]); balance=balance_for(store.data,request.actor.actor_id,item["leave_type_id"])
        if item["working_days"]>balance["available_days"]: raise ApiError(409,"insufficient_balance","The requested leave exceeds the available balance",balance)
        if item["working_days"]>=policy["document_required_after_days"] and not item["document_refs"]: raise ApiError(400,"document_required","Supporting document_refs are required for this duration")
        item["status"]="submitted"; item["submitted_at"]=now_iso(); return {"application":item,"balance":balance_for(store.data,request.actor.actor_id,item["leave_type_id"])}


def cancel_application(request, store):
    with store.lock:
        item=application(store.data,request.params["application_id"],request.actor.actor_id)
        if item["status"]=="approved": raise ApiError(409,"approved_leave_locked","Approved leave requires an administrator change request")
        if item["status"]!="cancelled": item["status"]="cancelled"; item["cancelled_at"]=now_iso()
        return {"application":item}


schema=object_schema(["leave_type_id","start_date","end_date","reason","contact_during_leave"],{"leave_type_id":{"type":"string"},"start_date":{"type":"string","format":"date"},"end_date":{"type":"string","format":"date"},"reason":{"type":"string"},"contact_during_leave":{"type":"string"},"document_refs":{"type":"array","items":{"type":"string"}}})
aid=[path_parameter("application_id","Leave application identifier")]
API.route("GET",r"/v1/leave-types","/v1/leave-types",list_types,operation_id="listLeaveTypes",summary="List leave policies")
API.route("GET",r"/v1/leave-balances","/v1/leave-balances",list_balances,operation_id="getMyLeaveBalances",summary="Get calculated leave balances")
API.route("GET",r"/v1/leave-applications","/v1/leave-applications",list_applications,operation_id="listMyLeaveApplications",summary="List leave applications",parameters=[query_parameter("status","Optional status filter")])
API.route("POST",r"/v1/leave-applications","/v1/leave-applications",create_application,operation_id="createLeaveApplication",summary="Create a draft leave application",request_schema=schema)
API.route("GET",r"/v1/leave-applications/(?P<application_id>[^/]+)","/v1/leave-applications/{application_id}",get_application,operation_id="getLeaveApplication",summary="Get a leave application",parameters=aid)
API.route("PATCH",r"/v1/leave-applications/(?P<application_id>[^/]+)","/v1/leave-applications/{application_id}",update_application,operation_id="updateLeaveApplication",summary="Update a draft leave application",parameters=aid,request_schema={**schema,"required":[]})
API.route("POST",r"/v1/leave-applications/(?P<application_id>[^/]+)/submit","/v1/leave-applications/{application_id}/submit",submit_application,operation_id="submitLeaveApplication",summary="Validate and submit a leave application",parameters=aid,request_schema={"type":"object","properties":{},"additionalProperties":False})
API.route("DELETE",r"/v1/leave-applications/(?P<application_id>[^/]+)","/v1/leave-applications/{application_id}",cancel_application,operation_id="cancelLeaveApplication",summary="Cancel a draft or submitted application",parameters=aid)
Handler=API.make_handler(STORE,TOKENS)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",default=8103,type=int); a=p.parse_args(); s=ThreadingHTTPServer((a.host,a.port),Handler); print(f"Mock GS RPg Leave API listening on http://{a.host}:{a.port}"); s.serve_forever()
if __name__=="__main__": main()
