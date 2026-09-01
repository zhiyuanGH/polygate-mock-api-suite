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
 def test_asset_search(s):
  st,p=s.req("GET","/v1/assets?building=BC&asset_type=air-conditioning"); s.assertEqual(st,200); s.assertEqual(p["assets"][0]["asset_id"],"asset-AC-BC302")
 def test_report_update_comment_cancel(s):
  b={"category_id":"electrical","asset_id":"asset-LIGHT-Z205","location":"Z205","title":"Light flicker","description":"Flickers every minute","urgency":"high","access_permission":True,"preferred_contact":"student@example.invalid","attachment_refs":["file://synthetic/photo-1"]}
  st,p=s.req("POST","/v1/service-requests",b); s.assertEqual(st,201); rid=p["service_request"]["request_id"]
  st,p=s.req("PATCH",f"/v1/service-requests/{rid}",{"description":"Two lights now flicker"}); s.assertEqual(st,200)
  st,p=s.req("POST",f"/v1/service-requests/{rid}/comments",{"message":"Issue is still present"}); s.assertEqual(st,201)
  st,p=s.req("GET",f"/v1/service-requests/{rid}"); s.assertEqual(len(p["comments"]),1)
  st,p=s.req("DELETE",f"/v1/service-requests/{rid}"); s.assertEqual(p["service_request"]["status"],"cancelled")
 def test_invalid_category(s):
  b={"category_id":"unknown","location":"X","title":"X","description":"X","urgency":"normal","access_permission":True,"preferred_contact":"x"}; st,p=s.req("POST","/v1/service-requests",b); s.assertEqual(st,404)
 def test_user_cannot_read_other_request(s):
  st,p=s.req("GET","/v1/service-requests/fm-0002"); s.assertEqual(st,404)
if __name__=="__main__": unittest.main()
