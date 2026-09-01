# Mock CFSO Student Locker API

Independent sandbox mock of the **Student Locker System** (ITS Ref. 134). Agents can discover lockers and application periods, create and revise a draft, submit it, receive an offer or waitlist result, accept an offer, and cancel or release it.

Run `python3 app.py --port 8102`; use `Authorization: Bearer polygate-student-demo`; register `/openapi.json` with the agent. Tests: `python3 -m unittest discover -s tests`.

Docker: `docker build -t polygate-locker .` then `docker run --rm -p 8102:8102 polygate-locker`.

All records are synthetic. Replace demo authentication at the competition gateway, isolate network access, export audit logs, and never add production credentials or personal data.
