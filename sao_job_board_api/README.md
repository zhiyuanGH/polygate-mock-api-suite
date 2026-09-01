# Mock SAO ISS Job Board API

Independent sandbox mock of the **SAO ISS Job Board** (ITS Ref. 138). Agents can search and inspect opportunities, save/unsave jobs, create and edit application drafts, answer required screening questions, submit, track, and withdraw applications.

Run `python3 app.py --port 8104`, use `Bearer polygate-student-demo`, and register `/openapi.json`. Tests: `python3 -m unittest discover -s tests`.

Docker: `docker build -t polygate-job-board .` then `docker run --rm -p 8104:8104 polygate-job-board`. Employers, jobs, applications, resumes, and users are synthetic.
