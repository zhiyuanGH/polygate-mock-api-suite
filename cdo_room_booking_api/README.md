# Mock CDO Room Booking API

Independent, sandbox-only mock of the **CDO Room Booking System** (ITS Ref. 12). It uses synthetic data and has no production-system route.

An agent can search rooms by capacity/features/time, inspect room details, check availability, list its own bookings, create a booking, change it, and cancel it. Scheduling conflicts and room-capacity rules are enforced.

## Run

```bash
python3 app.py --port 8101
```

Use `Authorization: Bearer polygate-student-demo` for `/v1/*`. Register `http://localhost:8101/openapi.json` as the agent tool contract.

```bash
curl -H 'Authorization: Bearer polygate-student-demo' \
  'http://localhost:8101/v1/rooms?capacity_min=30&features=projector&date=2026-09-15&start_time=12:00&end_time=13:00'
```

Run tests with `python3 -m unittest discover -s tests`. Build with `docker build -t polygate-cdo-room .` and run with `docker run --rm -p 8101:8101 polygate-cdo-room`.

Demo tokens are intentionally fixed for the mock. In the competition environment, terminate TLS at the gateway, replace demo tokens with the competition identity provider, restrict ingress to the competition network, enable rate limits and audit export, and never load production credentials or personal data.
