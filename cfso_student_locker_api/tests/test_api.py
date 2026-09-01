import json, threading, unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from app import Handler, STORE

class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler); cls.port=cls.server.server_address[1]; cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2)
    def setUp(self): STORE.reset()
    def request(self,method,path,body=None):
        c=HTTPConnection("127.0.0.1",self.port,timeout=5); h={"Authorization":"Bearer polygate-student-demo","Content-Type":"application/json"}; c.request(method,path,json.dumps(body).encode() if body is not None else None,h); r=c.getresponse(); p=json.loads(r.read()); c.close(); return r.status,p
    def test_search(self):
        s,p=self.request("GET","/v1/lockers?size=medium&status=available"); self.assertEqual(s,200); self.assertEqual(p["count"],2)
    def test_full_application_workflow(self):
        body={"period_id":"2026-27","size_preference":"medium","building_preferences":["VA","BC"],"accessibility_required":True}
        s,p=self.request("POST","/v1/locker-applications",body); self.assertEqual(s,201); aid=p["application"]["application_id"]
        s,p=self.request("POST",f"/v1/locker-applications/{aid}/submit",{}); self.assertEqual(p["application"]["status"],"offered")
        s,p=self.request("POST",f"/v1/locker-applications/{aid}/accept",{}); self.assertEqual(p["application"]["status"],"accepted"); self.assertEqual(p["locker"]["status"],"assigned")
        s,p=self.request("DELETE",f"/v1/locker-applications/{aid}"); self.assertEqual(p["application"]["status"],"cancelled")
    def test_duplicate_application_rejected(self):
        body={"period_id":"2026-27","size_preference":"small","building_preferences":["VA"]}
        self.request("POST","/v1/locker-applications",body); s,p=self.request("POST","/v1/locker-applications",body); self.assertEqual(s,409); self.assertEqual(p["error"]["code"],"duplicate_application")
    def test_cannot_accept_draft(self):
        s,p=self.request("POST","/v1/locker-applications",{"period_id":"2026-27","size_preference":"large","building_preferences":["BC"]}); aid=p["application"]["application_id"]
        s,p=self.request("POST",f"/v1/locker-applications/{aid}/accept",{}); self.assertEqual(s,409)

if __name__=="__main__": unittest.main()
