import json,threading,unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from app import Handler,STORE
class ApiTest(unittest.TestCase):
 @classmethod
 def setUpClass(c): c.s=ThreadingHTTPServer(("127.0.0.1",0),Handler); c.port=c.s.server_address[1]; c.t=threading.Thread(target=c.s.serve_forever,daemon=True); c.t.start()
 @classmethod
 def tearDownClass(c): c.s.shutdown(); c.s.server_close(); c.t.join(timeout=2)
 def setUp(s): STORE.reset()
 def req(s,m,p,b=None):
  c=HTTPConnection("127.0.0.1",s.port,timeout=5); c.request(m,p,json.dumps(b).encode() if b is not None else None,{"Authorization":"Bearer polygate-student-demo","Content-Type":"application/json"}); r=c.getresponse(); x=json.loads(r.read()); c.close(); return r.status,x
 def test_balance(s):
  st,p=s.req("GET","/v1/leave-balances"); annual=next(x for x in p["balances"] if x["leave_type_id"]=="annual"); s.assertEqual(st,200); s.assertEqual(annual["available_days"],15)
 def test_draft_update_submit_cancel(s):
  b={"leave_type_id":"annual","start_date":"2026-09-21","end_date":"2026-09-22","reason":"Research break","contact_during_leave":"student@example.invalid"}; st,p=s.req("POST","/v1/leave-applications",b); aid=p["application"]["application_id"]
  st,p=s.req("PATCH",f"/v1/leave-applications/{aid}",{"reason":"Updated reason"}); s.assertEqual(p["application"]["status"],"draft")
  st,p=s.req("POST",f"/v1/leave-applications/{aid}/submit",{}); s.assertEqual(p["application"]["status"],"submitted")
  st,p=s.req("DELETE",f"/v1/leave-applications/{aid}"); s.assertEqual(p["application"]["status"],"cancelled")
 def test_sick_leave_requires_document(s):
  b={"leave_type_id":"sick","start_date":"2026-09-21","end_date":"2026-09-23","reason":"Illness","contact_during_leave":"student@example.invalid"}; st,p=s.req("POST","/v1/leave-applications",b); aid=p["application"]["application_id"]; st,p=s.req("POST",f"/v1/leave-applications/{aid}/submit",{}); s.assertEqual(st,400); s.assertEqual(p["error"]["code"],"document_required")
 def test_overlap_rejected(s):
  b={"leave_type_id":"annual","start_date":"2026-07-09","end_date":"2026-07-13","reason":"Overlap","contact_during_leave":"student@example.invalid"}; st,p=s.req("POST","/v1/leave-applications",b); aid=p["application"]["application_id"]; st,p=s.req("POST",f"/v1/leave-applications/{aid}/submit",{}); s.assertEqual(st,409)
if __name__=="__main__": unittest.main()
