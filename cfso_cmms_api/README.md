# Mock CFSO CMMS API

Independent sandbox mock of the **CFSO Computerized Maintenance Management System** (ITS Ref. 19). Agents can inspect issue categories, find campus assets, report a defect, revise it, add follow-up messages and attachment references, track its state, and cancel an unresolved request.

Run `python3 app.py --port 8105`, use `Bearer polygate-student-demo`, and register `/openapi.json`. Tests: `python3 -m unittest discover -s tests`.

Docker: `docker build -t polygate-cmms .` then `docker run --rm -p 8105:8105 polygate-cmms`. All locations, assets, users, and service records are synthetic.
