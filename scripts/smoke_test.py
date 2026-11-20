r"""End-to-end smoke test against a RUNNING server (default http://127.0.0.1:8000).

    .\.venv\Scripts\python.exe scripts\smoke_test.py [--base http://127.0.0.1:8000]

Walks through every role's main workflow over real HTTP, using the demo accounts.
It writes demo records (a support plan, an intervention, a request, a goal, an import batch),
so run it against demo data only.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

PASSWORD = "Demo@2026!"
ROOT = Path(__file__).resolve().parents[1]
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str, detail: str = "") -> bool:
    results.append((bool(cond), label))
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    return bool(cond)


def session(base: str, email: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=30)
    r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    check(r.status_code == 200, f"login {email}", r.text)
    return c


def timed_get(c: httpx.Client, path: str) -> httpx.Response:
    t = time.perf_counter()
    r = c.get(path)
    ms = (time.perf_counter() - t) * 1000
    check(r.status_code == 200 and ms < 2000, f"GET {path} ({ms:.0f} ms)", f"{r.status_code} {r.text[:200]}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")  # avoids the slow IPv6 localhost fallback on Windows
    base = ap.parse_args().base

    print("\n== Static UI & security headers")
    anon = httpx.Client(base_url=base, timeout=30)
    for page in ["/", "/dashboard.html", "/alerts.html", "/students.html", "/student.html", "/interventions.html",
                 "/imports.html", "/reports.html", "/admin.html", "/me.html", "/css/styles.css", "/js/ui.js",
                 "/vendor/chart.umd.min.js"]:
        r = anon.get(page)
        check(r.status_code == 200, f"serve {page}", str(r.status_code))
    h = anon.get("/").headers
    check("default-src 'self'" in h.get("content-security-policy", ""), "CSP header present")
    check(h.get("x-frame-options") == "DENY", "X-Frame-Options DENY")

    print("\n== Authentication")
    check(anon.get("/api/students").status_code == 401, "unauthenticated API -> 401")
    bad = anon.post("/api/auth/login", json={"email": "teacher1@saews.demo", "password": "wrong"})
    check(bad.status_code == 401, "wrong password -> 401")
    check("set-cookie" not in bad.headers, "no session cookie on failed login")

    teacher = session(base, "teacher1@saews.demo")
    advisor = session(base, "advisor1@saews.demo")
    student = session(base, "student@saews.demo")
    analyst = session(base, "analyst@saews.demo")
    admin = session(base, "admin@saews.demo")
    ck = teacher.cookies.jar
    cookie = next(iter(ck), None)
    check(cookie is not None and cookie.has_nonstandard_attr("HttpOnly"), "session cookie is HttpOnly")

    print("\n== Teacher: dashboard, alerts, profile (FR3-FR5)")
    s = timed_get(teacher, "/api/risk/summary").json()
    check(s["students"] > 0, f"teacher scope has {s['students']} students")
    alerts = timed_get(teacher, "/api/risk/alerts").json()["items"]
    check(len(alerts) > 0, f"{len(alerts)} alerts in scope")
    order = {"critical": 0, "high": 1, "moderate": 2, "insufficient_data": 3, "unavailable": 4}
    check([order[a["assessment"]["risk_level"]] for a in alerts] == sorted(order[a["assessment"]["risk_level"]] for a in alerts),
          "alerts sorted by priority")
    target = next(a for a in alerts if a["assessment"]["risk_level"] in ("high", "critical"))
    sid = target["id"]
    prof = timed_get(teacher, f"/api/students/{sid}").json()
    a = prof["assessment"]
    check(a["method"] == "model" and a["model_version"] and a["created_at"] and a["data_as_of"],
          "assessment has method, model version, timestamp, data freshness (AT-03)")
    check(len(a["factors"]) > 0 and all(f["label"] for f in a["factors"]), "plain-language contributing factors (FR5)")
    check(a["created_at"].endswith("+00:00"), "timestamps carry timezone")
    ind = timed_get(teacher, f"/api/students/{sid}/indicators").json()
    check(len(ind["attendance"]) >= 8 and len(ind["scores"]) > 0, "indicator time series for charts")
    timed_get(teacher, f"/api/students/{sid}/assessments")
    st_list = timed_get(teacher, "/api/students?level=high").json()["items"]
    check(all(x["assessment"]["risk_level"] == "high" for x in st_list), "student list filter by level")

    print("\n== Teacher: scope enforcement (AT-01)")
    all_ids = {x["id"] for x in admin.get("/api/students").json()["items"]}
    mine = {x["id"] for x in teacher.get("/api/students").json()["items"]}
    outside = sorted(all_ids - mine)
    check(len(outside) > 0, f"{len(outside)} students outside teacher1's courses")
    if outside:
        check(teacher.get(f"/api/students/{outside[0]}").status_code == 403, "other teacher's student -> 403")

    print("\n== Review, flag, re-assess (FR5)")
    r = teacher.post(f"/api/risk/{a['id']}/review", json={"note": "Discussed in class"})
    check(r.status_code == 200 and r.json()["review_status"] == "reviewed", "mark alert reviewed")
    r = teacher.post(f"/api/students/{sid}/assess")
    check(r.status_code == 200 and r.json()["is_current"], "manual re-assessment")
    new_a = r.json()
    r = teacher.post(f"/api/risk/{new_a['id']}/flag", json={"reason": "Week 7 attendance looks wrong", "data_issue": True})
    check(r.status_code == 200 and r.json()["review_status"] == "flagged", "flag alert with data issue")

    print("\n== Recommendations -> plan -> intervention (FR6/FR7, AT-06)")
    recs = teacher.get(f"/api/students/{sid}/recommendations").json()["items"]
    proposed = [x for x in recs if x["status"] == "proposed"]
    check(len(proposed) > 0, f"{len(proposed)} proposed recommendations")
    staff = teacher.get("/api/staff").json()["items"]
    owner = next(x for x in staff if x["role"] == "advisor")
    due = (date.today() + timedelta(days=10)).isoformat()
    plan = None
    if proposed:
        r = teacher.post(f"/api/recommendations/{proposed[0]['id']}/approve",
                         json={"edited_text": "Weekly tutoring, Tuesdays 3pm", "owner_id": owner["id"], "due_date": due})
        plan = r.json().get("plan") if r.status_code == 200 else None
        check(plan and plan["owner"]["id"] == owner["id"] and plan["due_date"] == due and plan["status"] == "planned",
              "approve creates plan with owner, due date, status", r.text[:200])
        check(teacher.post(f"/api/recommendations/{proposed[0]['id']}/approve", json={}).status_code == 409,
              "double approval rejected")
        if len(proposed) > 1:
            r = teacher.post(f"/api/recommendations/{proposed[1]['id']}/dismiss", json={"reason": "Already in place"})
            check(r.status_code == 200 and r.json()["status"] == "dismissed", "dismiss recommendation")
    if plan:
        r = teacher.post(f"/api/plans/{plan['id']}/interventions",
                         json={"action_type": "tutoring_session", "notes": "First session", "status": "done"})
        p = r.json()
        iv = p["interventions"][-1]
        check(r.status_code == 201 and p["status"] == "in_progress", "intervention recorded, plan in progress")
        check("attendance_rate" in iv["baseline_snapshot"], "baseline indicator snapshot stored")
        r = teacher.patch(f"/api/interventions/{iv['id']}", json={"status": "done", "outcome": "Student attended"})
        check(r.status_code == 200 and r.json()["interventions"][-1]["followup_snapshot"], "outcome + follow-up snapshot")
        r = teacher.patch(f"/api/plans/{plan['id']}", json={"status": "completed"})
        check(r.status_code == 200 and r.json()["status"] == "completed", "plan marked completed")
    timed_get(advisor, "/api/plans?mine=true")

    print("\n== Student portal (FR3/FR6/FR8, AT-07)")
    me = timed_get(student, "/api/me/profile").json()
    check(me["student_code"] == "S20260001", "student sees own profile")
    sup = timed_get(student, "/api/me/support").json()
    check(all("risk" not in k for k in sup), "no risk labels exposed to student")
    timed_get(student, "/api/me/indicators")
    check(student.get(f"/api/students/{sid}").status_code == 403, "student blocked from staff endpoints")
    g = student.post("/api/me/goals", json={"title": "Attend every SE331 class", "target_date": due})
    check(g.status_code == 201, "create study goal")
    check(student.patch(f"/api/me/goals/{g.json()['id']}", json={"status": "achieved"}).json()["status"] == "achieved",
          "update study goal")
    r = student.post("/api/me/requests", json={"kind": "correction", "subject": "Attendance week 7",
                                               "details": "I was present on Monday", "target_record": "SE331 week 7"})
    assignee = r.json().get("assigned_to") or {}
    check(r.status_code == 201 and assignee.get("id") == (me["advisor"] or {}).get("id"),
          f"correction request routed to the student's advisor ({assignee.get('full_name')})")
    req_id = r.json()["id"]
    reviewer = advisor if assignee.get("full_name") == "Kamrul Advisor" else session(base, "advisor2@saews.demo")
    other = session(base, "advisor2@saews.demo") if reviewer is advisor else advisor
    check(other.patch(f"/api/requests/{req_id}", json={"status": "resolved", "resolution": "x"}).status_code == 403,
          "a different advisor cannot handle it")
    inbox = reviewer.get("/api/requests?status=open").json()["items"]
    check(any(x["id"] == req_id for x in inbox), "request appears in advisor inbox")
    check(reviewer.patch(f"/api/requests/{req_id}", json={"status": "resolved"}).status_code == 422,
          "closing without resolution note rejected")
    r = reviewer.patch(f"/api/requests/{req_id}", json={"status": "resolved", "resolution": "Corrected in register"})
    check(r.status_code == 200 and r.json()["status"] == "resolved", "advisor resolves request")
    mine_req = student.get("/api/me/requests").json()["items"]
    check(any(x["id"] == req_id and x["resolution"] for x in mine_req), "student sees the response")

    print("\n== Data import (FR2, AT-02)")
    bad_file = (ROOT / "sample_data" / "example_with_errors_attendance.csv").read_bytes()
    r = admin.post("/api/imports/validate", data={"kind": "attendance"}, files={"file": ("bad.csv", bad_file, "text/csv")})
    b = r.json()
    check(b["status"] == "rejected" and len(b["errors"]) == 5, f"bad file rejected with {len(b['errors'])} line errors")
    check(admin.post(f"/api/imports/{b['id']}/commit").status_code == 409, "rejected batch cannot be committed")
    good = (ROOT / "sample_data" / "example_attendance_week11_SE331.csv").read_bytes()
    r = teacher.post("/api/imports/validate", data={"kind": "attendance"}, files={"file": ("good.csv", good, "text/csv")})
    check(r.json()["status"] == "validated", "teacher validates own-course file", r.text[:300])
    r = teacher.post(f"/api/imports/{r.json()['id']}/commit")
    check(r.status_code == 200 and r.json()["status"] == "committed", "commit -> background re-assessment")
    r = teacher.post("/api/imports/validate", data={"kind": "students"},
                     files={"file": ("s.csv", b"student_code,full_name,program,year_of_study\n", "text/csv")})
    check(r.status_code == 403, "teacher cannot import student master data")
    tpl = admin.get("/api/imports/template/assessments")
    check(tpl.status_code == 200 and tpl.text.startswith("student_code,course_code"), "CSV template download")

    print("\n== Reports & privacy (FR9, AT-08)")
    rs = timed_get(analyst, "/api/reports/summary").json()
    check(rs["deidentified"], "analyst summary is de-identified")
    check(all(v is None or v == 0 or v >= rs["min_group_size"] for c in rs["by_program"].values() for v in c.values()),
          "small cells suppressed")
    check(analyst.get("/api/reports/export?identifiable=true").status_code == 403, "analyst identifiable export -> 403")
    ex = analyst.get("/api/reports/export")
    check(ex.status_code == 200 and "pseudonym" in ex.text.splitlines()[0] and "S2026" not in ex.text,
          "de-identified export has no names/IDs")
    ex = teacher.get("/api/reports/export?identifiable=true")
    check(ex.status_code == 200 and "full_name" in ex.text.splitlines()[0], "teacher identifiable export (own scope)")
    timed_get(teacher, "/api/reports/trends")
    check(analyst.get(f"/api/students/{sid}").status_code == 403, "analyst cannot open individual profiles")

    print("\n== Admin (FR1/FR8/FR10)")
    users = timed_get(admin, "/api/admin/users").json()["items"]
    check(len(users) >= 7, f"{len(users)} users listed")
    m = timed_get(admin, "/api/admin/model").json()
    check(m["status"]["available"] and m["metrics"] and m["metrics"]["fairness"], "model monitor: metrics + fairness")
    aud = timed_get(admin, "/api/admin/audit?outcome=denied").json()["items"]
    actions = {x["action"] for x in aud}
    check({"student.view", "report.export"} <= actions, f"denials audited: {sorted(actions)}")
    ret = admin.post("/api/admin/retention", json={"dry_run": True})
    check(ret.status_code == 200 and ret.json()["dry_run"], "retention dry run")
    check(teacher.get("/api/admin/users").status_code == 403, "non-admin blocked from admin API")
    r = admin.post("/api/admin/users", json={"email": f"qa{int(time.time())}@saews.demo", "full_name": "QA Teacher",
                                             "role": "teacher", "password": "short"})
    check(r.status_code == 422, "weak password rejected")

    print("\n== Background refresh completed")
    time.sleep(2)
    hist = teacher.get(f"/api/students/{sid}/assessments").json()["items"]
    check(sum(1 for x in hist if x["is_current"]) == 1, "exactly one current assessment per student")

    for c in (teacher, advisor, student, analyst, admin):
        c.post("/api/auth/logout")
    check(teacher.get("/api/auth/me").status_code == 401, "logout clears session")

    failed = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for label in failed:
        print(f"  FAILED: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
