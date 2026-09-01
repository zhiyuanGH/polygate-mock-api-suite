# PolyGate Independent Mock API Suite

Five sandbox APIs selected from the PolyU system stocktake for the PolyGate Agent Challenge. They live in one repository for organizer convenience, but each service is an independent deployment unit: it has its own process, port, source code, synthetic data, tests, Dockerfile, authentication boundary, and OpenAPI 3.1 document. No service imports or calls another service.

| System | Directory | Port | Main agent workflows |
| --- | --- | ---: | --- |
| CDO Room Booking System (ITS Ref. 12) | `cdo_room_booking_api/` | 8101 | Search rooms, check availability, create/update/list/cancel bookings |
| CFSO Student Locker System (ITS Ref. 134) | `cfso_student_locker_api/` | 8102 | Search lockers, draft/submit applications, accept offers, cancel/release |
| GS RPg Leave Management System (ITS Ref. 119) | `gs_rpg_leave_api/` | 8103 | Read policy/balance, draft/update/submit/track/cancel leave |
| SAO ISS Job Board (ITS Ref. 138) | `sao_job_board_api/` | 8104 | Search/save jobs, draft/update/submit/track/withdraw applications |
| CFSO CMMS (ITS Ref. 19) | `cfso_cmms_api/` | 8105 | Find assets, report/update/track/cancel faults, add follow-up messages |

## Run one service

```bash
cd cdo_room_booking_api
python3 app.py
```

Use `Authorization: Bearer polygate-student-demo` for `/v1/*`. Each service publishes its agent contract at `/openapi.json` and health status at `/health`.

## Test all services

```bash
make test
```

## Run all with Docker Compose

```bash
docker compose up --build
```

Running all five together is optional. Every directory can be built and deployed by itself using the commands in its README.

## Competition boundary

All data and identities are synthetic. The fixed demo token is only for local development. Before student participants receive access, deploy each API inside the isolated competition network, terminate TLS at the gateway, replace demo authentication with competition identities, apply per-service ingress and rate limits, export audit logs, and verify that no production route, credential, or personal data exists.
