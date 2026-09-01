# Mock GS RPg Leave API

Independent sandbox mock of the **RPg Leave Management System** (ITS Ref. 119). Agents can inspect policies and calculated balances, create/update drafts, submit leave, track status, and cancel eligible applications. It enforces date overlap, balance, duration, and supporting-document rules.

Run `python3 app.py --port 8103`, authenticate `/v1/*` with `Bearer polygate-student-demo`, and register `/openapi.json`. Tests: `python3 -m unittest discover -s tests`.

Docker: `docker build -t polygate-rpg-leave .` then `docker run --rm -p 8103:8103 polygate-rpg-leave`. Data is synthetic; use competition-only identity, networking, audit logs, and secrets.
