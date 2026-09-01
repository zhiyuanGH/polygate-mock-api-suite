#!/usr/bin/env python3
"""Independent mock of the CFSO Computerized Maintenance Management System."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from mock_http import Actor, Api, ApiError, JsonStore, now_iso, object_schema, path_parameter, query_parameter

ROOT=Path(__file__).resolve().parent; STORE=JsonStore(ROOT/"data"/"seed.json")
TOKENS={"polygate-student-demo":Actor("student-1001","student"),"polygate-organizer-demo":Actor("organizer-1001","organizer")}
API=Api("Mock CFSO CMMS API","cfso-cmms-api")

def category(data,category_id):
 item=next((x for x in data["categories"] if x["category_id"]==category_id),None)
 if item is None: raise ApiError(404,"category_not_found",f"Unknown category_id: {category_id}")
 return item
def asset(data,asset_id):
 item=next((x for x in data["assets"] if x["asset_id"]==asset_id),None)
 if item is None: raise ApiError(404,"asset_not_found",f"Unknown asset_id: {asset_id}")
 return item
def service_request(data,request_id,owner_id):
 item=next((x for x in data["service_requests"] if x["request_id"]==request_id),None)
 if item is None or item["owner_id"]!=owner_id: raise ApiError(404,"service_request_not_found",f"Unknown request_id: {request_id}")
 return item
def list_categories(request,store):
 with store.lock: return {"categories":store.data["categories"]}
def list_assets(request,store):
 with store.lock:
  items=list(store.data["assets"])
  for field in ("building","floor","asset_type"):
   if request.one(field): items=[x for x in items if x[field].lower()==request.one(field).lower()]
  q=(request.one("q","") or "").lower()
  if q: items=[x for x in items if q in " ".join([x["name"],x["location"],x["asset_id"]]).lower()]
  return {"count":len(items),"assets":items}
def get_asset(request,store):
 with store.lock: return {"asset":asset(store.data,request.params["asset_id"])}
def list_requests(request,store):
 with store.lock:
  items=[x for x in store.data["service_requests"] if x["owner_id"]==request.actor.actor_id]
  if request.one("status"): items=[x for x in items if x["status"]==request.one("status")]
  return {"count":len(items),"service_requests":items}
def create_request(request,store):
 request.require("category_id","location","title","description","urgency","access_permission","preferred_contact")
 if request.body["urgency"] not in {"low","normal","high","emergency"}: raise ApiError(400,"invalid_urgency","urgency must be low, normal, high, or emergency")
 with store.lock:
  category(store.data,request.body["category_id"])
  if request.body.get("asset_id"): asset(store.data,request.body["asset_id"])
  item={"request_id":f"fm-{store.data['next_request_id']:04d}","owner_id":request.actor.actor_id,"category_id":request.body["category_id"],"asset_id":request.body.get("asset_id"),"location":request.body["location"],"title":request.body["title"],"description":request.body["description"],"urgency":request.body["urgency"],"access_permission":bool(request.body["access_permission"]),"preferred_contact":request.body["preferred_contact"],"attachment_refs":request.body.get("attachment_refs",[]),"status":"submitted","created_at":now_iso(),"last_updated_at":now_iso()}
  store.data["next_request_id"]+=1; store.data["service_requests"].append(item); return 201,{"service_request":item}
def get_request(request,store):
 with store.lock:
  item=service_request(store.data,request.params["request_id"],request.actor.actor_id); comments=[x for x in store.data["comments"] if x["request_id"]==item["request_id"]]; return {"service_request":item,"comments":comments}
def update_request(request,store):
 allowed={"category_id","asset_id","location","title","description","urgency","access_permission","preferred_contact","attachment_refs"}
 if set(request.body)-allowed: raise ApiError(400,"unknown_field","The request contains fields that cannot be changed")
 with store.lock:
  item=service_request(store.data,request.params["request_id"],request.actor.actor_id)
  if item["status"] not in {"submitted","triaged"}: raise ApiError(409,"service_request_not_editable","Only submitted or triaged requests can be changed")
  if request.body.get("category_id"): category(store.data,request.body["category_id"])
  if request.body.get("asset_id"): asset(store.data,request.body["asset_id"])
  if request.body.get("urgency") and request.body["urgency"] not in {"low","normal","high","emergency"}: raise ApiError(400,"invalid_urgency","Invalid urgency")
  item.update(request.body); item["last_updated_at"]=now_iso(); return {"service_request":item}
def add_comment(request,store):
 request.require("message")
 with store.lock:
  item=service_request(store.data,request.params["request_id"],request.actor.actor_id)
  if item["status"]=="cancelled": raise ApiError(409,"service_request_closed","Comments cannot be added to a cancelled request")
  comment={"comment_id":f"comment-{store.data['next_comment_id']:04d}","request_id":item["request_id"],"author_id":request.actor.actor_id,"message":request.body["message"],"attachment_refs":request.body.get("attachment_refs",[]),"created_at":now_iso()}
  store.data["next_comment_id"]+=1; store.data["comments"].append(comment); item["last_updated_at"]=now_iso(); return 201,{"comment":comment}
def cancel_request(request,store):
 with store.lock:
  item=service_request(store.data,request.params["request_id"],request.actor.actor_id)
  if item["status"] in {"completed","cancelled"}:
   if item["status"]=="completed": raise ApiError(409,"service_request_completed","A completed request cannot be cancelled")
   return {"service_request":item}
  item["status"]="cancelled"; item["cancelled_at"]=now_iso(); item["last_updated_at"]=now_iso(); return {"service_request":item}

rid=[path_parameter("request_id","Facilities service request identifier")]; aid=[path_parameter("asset_id","Asset identifier")]
schema=object_schema(["category_id","location","title","description","urgency","access_permission","preferred_contact"],{"category_id":{"type":"string"},"asset_id":{"type":["string","null"]},"location":{"type":"string"},"title":{"type":"string"},"description":{"type":"string"},"urgency":{"type":"string","enum":["low","normal","high","emergency"]},"access_permission":{"type":"boolean"},"preferred_contact":{"type":"string"},"attachment_refs":{"type":"array","items":{"type":"string"}}})
API.route("GET",r"/v1/facility-categories","/v1/facility-categories",list_categories,operation_id="listFacilityCategories",summary="List issue categories and response targets")
API.route("GET",r"/v1/assets","/v1/assets",list_assets,operation_id="searchAssets",summary="Find maintainable campus assets",parameters=[query_parameter("q","Asset text search"),query_parameter("building","Exact building"),query_parameter("floor","Exact floor"),query_parameter("asset_type","Exact asset type")])
API.route("GET",r"/v1/assets/(?P<asset_id>[^/]+)","/v1/assets/{asset_id}",get_asset,operation_id="getAsset",summary="Get asset details",parameters=aid)
API.route("GET",r"/v1/service-requests","/v1/service-requests",list_requests,operation_id="listMyServiceRequests",summary="List facilities requests",parameters=[query_parameter("status","Optional status filter")])
API.route("POST",r"/v1/service-requests","/v1/service-requests",create_request,operation_id="createServiceRequest",summary="Report a facilities issue",request_schema=schema)
API.route("GET",r"/v1/service-requests/(?P<request_id>[^/]+)","/v1/service-requests/{request_id}",get_request,operation_id="getServiceRequest",summary="Get a request and its conversation",parameters=rid)
API.route("PATCH",r"/v1/service-requests/(?P<request_id>[^/]+)","/v1/service-requests/{request_id}",update_request,operation_id="updateServiceRequest",summary="Correct or add details",parameters=rid,request_schema={**schema,"required":[]})
API.route("POST",r"/v1/service-requests/(?P<request_id>[^/]+)/comments","/v1/service-requests/{request_id}/comments",add_comment,operation_id="addServiceRequestComment",summary="Add a follow-up message or attachment reference",parameters=rid,request_schema=object_schema(["message"],{"message":{"type":"string"},"attachment_refs":{"type":"array","items":{"type":"string"}}}))
API.route("DELETE",r"/v1/service-requests/(?P<request_id>[^/]+)","/v1/service-requests/{request_id}",cancel_request,operation_id="cancelServiceRequest",summary="Cancel an unresolved request",parameters=rid)
Handler=API.make_handler(STORE,TOKENS)
def main():
 p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",default=8105,type=int); a=p.parse_args(); s=ThreadingHTTPServer((a.host,a.port),Handler); print(f"Mock CFSO CMMS API listening on http://{a.host}:{a.port}"); s.serve_forever()
if __name__=="__main__": main()
