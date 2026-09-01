#!/usr/bin/env python3
"""Independent mock of the SAO ISS Job Board."""

from __future__ import annotations

import argparse
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path

from mock_http import Actor, Api, ApiError, JsonStore, now_iso, object_schema, path_parameter, query_parameter

ROOT=Path(__file__).resolve().parent; STORE=JsonStore(ROOT/"data"/"seed.json")
TOKENS={"polygate-student-demo":Actor("student-1001","student"),"polygate-organizer-demo":Actor("organizer-1001","organizer")}
API=Api("Mock SAO ISS Job Board API","sao-job-board-api")

def job(data,job_id):
 item=next((x for x in data["jobs"] if x["job_id"]==job_id),None)
 if item is None: raise ApiError(404,"job_not_found",f"Unknown job_id: {job_id}")
 return item
def application(data,application_id,owner_id):
 item=next((x for x in data["applications"] if x["application_id"]==application_id),None)
 if item is None or item["owner_id"]!=owner_id: raise ApiError(404,"application_not_found",f"Unknown application_id: {application_id}")
 return item
def list_jobs(request,store):
 with store.lock:
  items=[x for x in store.data["jobs"] if x["status"]=="open" and x["closing_date"]>=store.data["clock_date"]]
  q=(request.one("q","") or "").lower(); skills={x.strip().lower() for x in (request.one("skills","") or "").split(",") if x.strip()}
  if q: items=[x for x in items if q in " ".join([x["title"],x["employer"],x["description"]," ".join(x["skills"])]).lower()]
  for field in ("employment_type","work_mode","location"):
   if request.one(field): items=[x for x in items if x[field].lower()==request.one(field).lower()]
  if skills: items=[x for x in items if skills.issubset({s.lower() for s in x["skills"]})]
  return {"count":len(items),"jobs":items}
def get_job(request,store):
 with store.lock: return {"job":job(store.data,request.params["job_id"])}
def list_saved(request,store):
 with store.lock:
  ids=store.data["saved_jobs"].get(request.actor.actor_id,[]); return {"count":len(ids),"jobs":[job(store.data,x) for x in ids]}
def save_job(request,store):
 with store.lock:
  item=job(store.data,request.params["job_id"]); ids=store.data["saved_jobs"].setdefault(request.actor.actor_id,[])
  if item["job_id"] not in ids: ids.append(item["job_id"])
  return {"saved":True,"job_id":item["job_id"]}
def unsave_job(request,store):
 with store.lock:
  job(store.data,request.params["job_id"]); ids=store.data["saved_jobs"].setdefault(request.actor.actor_id,[])
  if request.params["job_id"] in ids: ids.remove(request.params["job_id"])
  return {"saved":False,"job_id":request.params["job_id"]}
def list_applications(request,store):
 with store.lock:
  items=[x for x in store.data["applications"] if x["owner_id"]==request.actor.actor_id]
  if request.one("status"): items=[x for x in items if x["status"]==request.one("status")]
  return {"count":len(items),"applications":items}
def create_application(request,store):
 request.require("job_id","resume_ref","cover_note")
 with store.lock:
  posting=job(store.data,request.body["job_id"])
  if posting["status"]!="open" or posting["closing_date"]<store.data["clock_date"]: raise ApiError(409,"job_closed","The job is no longer accepting applications")
  active=[x for x in store.data["applications"] if x["owner_id"]==request.actor.actor_id and x["job_id"]==posting["job_id"] and x["status"]!="withdrawn"]
  if active: raise ApiError(409,"duplicate_application","An application already exists",{"application_id":active[0]["application_id"]})
  item={"application_id":f"job-app-{store.data['next_application_id']:04d}","owner_id":request.actor.actor_id,"job_id":posting["job_id"],"resume_ref":request.body["resume_ref"],"cover_note":request.body["cover_note"],"answers":request.body.get("answers",{}),"status":"draft","created_at":now_iso()}
  store.data["next_application_id"]+=1; store.data["applications"].append(item); return 201,{"application":item}
def get_application(request,store):
 with store.lock: return {"application":application(store.data,request.params["application_id"],request.actor.actor_id)}
def update_application(request,store):
 allowed={"resume_ref","cover_note","answers"}
 if set(request.body)-allowed: raise ApiError(400,"unknown_field","Only resume_ref, cover_note, and answers can be changed")
 with store.lock:
  item=application(store.data,request.params["application_id"],request.actor.actor_id)
  if item["status"]!="draft": raise ApiError(409,"application_not_editable","Only draft applications can be changed")
  item.update(request.body); item["updated_at"]=now_iso(); return {"application":item}
def submit_application(request,store):
 with store.lock:
  item=application(store.data,request.params["application_id"],request.actor.actor_id)
  if item["status"]!="draft": raise ApiError(409,"invalid_status","Only a draft application can be submitted")
  posting=job(store.data,item["job_id"])
  if posting["status"]!="open" or posting["closing_date"]<store.data["clock_date"]: raise ApiError(409,"job_closed","The job is no longer accepting applications")
  missing=[q["question_id"] for q in posting["screening_questions"] if q.get("required") and item.get("answers",{}).get(q["question_id"]) in (None,"")]
  if missing: raise ApiError(400,"missing_answers","Required screening questions are unanswered",{"question_ids":missing})
  item["status"]="submitted"; item["submitted_at"]=now_iso(); return {"application":item}
def withdraw_application(request,store):
 with store.lock:
  item=application(store.data,request.params["application_id"],request.actor.actor_id)
  if item["status"] in {"hired","rejected"}: raise ApiError(409,"application_locked","A final application cannot be withdrawn")
  item["status"]="withdrawn"; item["withdrawn_at"]=now_iso(); return {"application":item}

aid=[path_parameter("application_id","Job application identifier")]; jid=[path_parameter("job_id","Job identifier")]
schema=object_schema(["job_id","resume_ref","cover_note"],{"job_id":{"type":"string"},"resume_ref":{"type":"string","description":"Opaque competition file reference"},"cover_note":{"type":"string"},"answers":{"type":"object","additionalProperties":{"type":"string"}}})
API.route("GET",r"/v1/jobs","/v1/jobs",list_jobs,operation_id="searchJobs",summary="Search open jobs",parameters=[query_parameter("q","Full-text search"),query_parameter("employment_type","Exact employment type"),query_parameter("work_mode","On-site, hybrid, or remote"),query_parameter("location","Exact location"),query_parameter("skills","Comma-separated required skills")])
API.route("GET",r"/v1/jobs/(?P<job_id>[^/]+)","/v1/jobs/{job_id}",get_job,operation_id="getJob",summary="Get job details and screening questions",parameters=jid)
API.route("GET",r"/v1/saved-jobs","/v1/saved-jobs",list_saved,operation_id="listSavedJobs",summary="List saved jobs")
API.route("POST",r"/v1/saved-jobs/(?P<job_id>[^/]+)","/v1/saved-jobs/{job_id}",save_job,operation_id="saveJob",summary="Save a job",parameters=jid,request_schema={"type":"object","properties":{},"additionalProperties":False})
API.route("DELETE",r"/v1/saved-jobs/(?P<job_id>[^/]+)","/v1/saved-jobs/{job_id}",unsave_job,operation_id="unsaveJob",summary="Remove a saved job",parameters=jid)
API.route("GET",r"/v1/job-applications","/v1/job-applications",list_applications,operation_id="listMyJobApplications",summary="List job applications",parameters=[query_parameter("status","Optional status filter")])
API.route("POST",r"/v1/job-applications","/v1/job-applications",create_application,operation_id="createJobApplication",summary="Create a draft job application",request_schema=schema)
API.route("GET",r"/v1/job-applications/(?P<application_id>[^/]+)","/v1/job-applications/{application_id}",get_application,operation_id="getJobApplication",summary="Get a job application",parameters=aid)
API.route("PATCH",r"/v1/job-applications/(?P<application_id>[^/]+)","/v1/job-applications/{application_id}",update_application,operation_id="updateJobApplication",summary="Update a draft application",parameters=aid,request_schema={**schema,"required":[]})
API.route("POST",r"/v1/job-applications/(?P<application_id>[^/]+)/submit","/v1/job-applications/{application_id}/submit",submit_application,operation_id="submitJobApplication",summary="Validate and submit an application",parameters=aid,request_schema={"type":"object","properties":{},"additionalProperties":False})
API.route("DELETE",r"/v1/job-applications/(?P<application_id>[^/]+)","/v1/job-applications/{application_id}",withdraw_application,operation_id="withdrawJobApplication",summary="Withdraw an application",parameters=aid)
Handler=API.make_handler(STORE,TOKENS)
def main():
 p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",default=8104,type=int); a=p.parse_args(); s=ThreadingHTTPServer((a.host,a.port),Handler); print(f"Mock SAO Job Board API listening on http://{a.host}:{a.port}"); s.serve_forever()
if __name__=="__main__": main()
