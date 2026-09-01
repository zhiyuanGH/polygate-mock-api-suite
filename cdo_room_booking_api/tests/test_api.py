import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from app import Handler, STORE


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2)

    def setUp(self):
        STORE.reset()

    def request(self, method, path, body=None, authenticated=True):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer polygate-student-demo"
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = conn.getresponse(); payload = json.loads(response.read()); conn.close()
        return response.status, payload

    def test_requires_authentication(self):
        status, payload = self.request("GET", "/v1/rooms", authenticated=False)
        self.assertEqual(status, 401); self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_search_with_availability(self):
        status, payload = self.request("GET", "/v1/rooms?capacity_min=40&features=projector&date=2026-09-15&start_time=10:00&end_time=11:00")
        self.assertEqual(status, 200); self.assertFalse(payload["rooms"][0]["available"])

    def test_create_update_and_cancel_booking(self):
        body = {"room_id": "BC-302", "date": "2026-09-15", "start_time": "12:00", "end_time": "13:00", "purpose": "Agent workshop", "attendee_count": 20}
        status, payload = self.request("POST", "/v1/bookings", body)
        self.assertEqual(status, 201)
        booking_id = payload["booking"]["booking_id"]
        status, payload = self.request("PATCH", f"/v1/bookings/{booking_id}", {"purpose": "Updated workshop"})
        self.assertEqual(status, 200); self.assertEqual(payload["booking"]["purpose"], "Updated workshop")
        status, payload = self.request("DELETE", f"/v1/bookings/{booking_id}")
        self.assertEqual(status, 200); self.assertEqual(payload["booking"]["status"], "cancelled")

    def test_rejects_conflict(self):
        body = {"room_id": "BC-302", "date": "2026-09-15", "start_time": "10:00", "end_time": "11:00", "purpose": "Conflict", "attendee_count": 2}
        status, payload = self.request("POST", "/v1/bookings", body)
        self.assertEqual(status, 409); self.assertEqual(payload["error"]["code"], "room_unavailable")

    def test_openapi_exposes_agent_operations(self):
        status, payload = self.request("GET", "/openapi.json", authenticated=False)
        self.assertEqual(status, 200); self.assertIn("createBooking", str(payload))


if __name__ == "__main__":
    unittest.main()
