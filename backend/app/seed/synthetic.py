"""Synthetic school & college generator (Bangladesh: SSC Class 9-10, HSC Class 11-12).

All data is fictional. A latent "difficulty" variable drives attendance, scores,
submissions and engagement, and ~15% of students "decline" after the mid-term exam — the
kind of pattern an early-warning system should surface. The historical cohort also
carries an end-of-term outcome label (fail/withdraw) used only for model training.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

# Bangladeshi school (SSC, Class 9-10) and college (HSC, Class 11-12) groups -> subject sections.
PROGRAMS = {
    "School - Science": ["SSC-BAN", "SSC-ENG", "SSC-MATH", "SSC-PHY", "SSC-CHEM"],
    "School - Business Studies": ["SSC-BAN", "SSC-ENG", "SSC-MATH", "SSC-ACC", "SSC-FIN"],
    "School - Humanities": ["SSC-BAN", "SSC-ENG", "SSC-MATH", "SSC-HIST", "SSC-GEO"],
    "College - Science": ["HSC-BAN", "HSC-ENG", "HSC-ICT", "HSC-PHY", "HSC-CHEM"],
    "College - Business Studies": ["HSC-BAN", "HSC-ENG", "HSC-ICT", "HSC-ACC", "HSC-BOM"],
    "College - Humanities": ["HSC-BAN", "HSC-ENG", "HSC-ICT", "HSC-CIV", "HSC-ECO"],
}
PROGRAM_WEIGHTS = [0.22, 0.15, 0.13, 0.20, 0.17, 0.13]
# Classes that belong to each level (School = SSC, College = HSC).
LEVEL_CLASSES = {"School": (9, 10), "College": (11, 12)}

COURSES = {
    "SSC-BAN": "Bangla (SSC)",
    "SSC-ENG": "English (SSC)",
    "SSC-MATH": "General Mathematics (SSC)",
    "SSC-PHY": "Physics (SSC)",
    "SSC-CHEM": "Chemistry (SSC)",
    "SSC-ACC": "Accounting (SSC)",
    "SSC-FIN": "Finance & Banking (SSC)",
    "SSC-HIST": "History of Bangladesh & World Civilisation (SSC)",
    "SSC-GEO": "Geography & Environment (SSC)",
    "HSC-BAN": "Bangla (HSC)",
    "HSC-ENG": "English (HSC)",
    "HSC-ICT": "Information & Communication Technology (HSC)",
    "HSC-PHY": "Physics (HSC)",
    "HSC-CHEM": "Chemistry (HSC)",
    "HSC-ACC": "Accounting (HSC)",
    "HSC-BOM": "Business Organisation & Management (HSC)",
    "HSC-CIV": "Civics & Good Governance (HSC)",
    "HSC-ECO": "Economics (HSC)",
}


def level_of(program: str) -> str:
    """'School' or 'College' for a group name such as 'College - Science'."""
    return program.split(" - ", 1)[0]


FIRST = [
    "Aarav", "Nusrat", "Tanvir", "Farhana", "Rafi", "Mim", "Sabbir", "Tasnim", "Imran", "Sadia",
    "Arif", "Jannat", "Nayeem", "Lamia", "Rakib", "Sumaiya", "Fahim", "Anika", "Shakil", "Raisa",
    "Mahin", "Tahsin", "Rifat", "Ishrat", "Zubair", "Maliha", "Sami", "Nabila", "Ayan", "Priya",
]
LAST = [
    "Hossain", "Rahman", "Ahmed", "Islam", "Chowdhury", "Karim", "Akter", "Hasan", "Sarker", "Uddin",
    "Mahmud", "Alam", "Begum", "Khan", "Das", "Roy", "Saha", "Mondal", "Talukder", "Bhuiyan",
]

QUIZ_WEEKS = {"Class Test 1": (3, 20), "Class Test 2": (6, 20), "Mid-Term Exam": (7, 50), "Class Test 3": (9, 20)}
ASSIGNMENT_WEEKS = {f"Homework {i}": w for i, w in enumerate([2, 4, 6, 8, 10], start=1)}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def term_start_for(today: date, weeks_elapsed: int = 10) -> date:
    start = today - timedelta(weeks=weeks_elapsed, days=1)
    return start - timedelta(days=start.weekday())  # Monday


@dataclass
class Cohort:
    students: pd.DataFrame
    enrollments: pd.DataFrame
    attendance: pd.DataFrame
    assessments: pd.DataFrame
    assignments: pd.DataFrame
    engagement: pd.DataFrame

    def frames(self) -> dict[str, pd.DataFrame]:
        return {
            "students": self.students,
            "attendance": self.attendance,
            "assessments": self.assessments,
            "assignments": self.assignments,
            "engagement": self.engagement,
        }


def generate_cohort(
    n_students: int,
    seed: int,
    term_start: date,
    weeks_elapsed: int = 10,
    code_prefix: str = "S",
    with_outcome: bool = False,
    special_cases: bool = False,
) -> Cohort:
    rng = np.random.default_rng(seed)
    programs = rng.choice(list(PROGRAMS), size=n_students, p=PROGRAM_WEIGHTS)
    equity = np.where(rng.random(n_students) < 0.35, "B", "A")
    z = rng.normal(0, 1, n_students) + np.where(equity == "B", 0.15, 0.0)
    decliner = rng.random(n_students) < 0.15
    # Class within the level: School -> 9 or 10, College -> 11 or 12.
    second_year = rng.random(n_students) < 0.5
    year = np.array([LEVEL_CLASSES[level_of(p)][int(b)] for p, b in zip(programs, second_year, strict=True)])
    # Previous exam GPA on the Bangladeshi 5.00 scale (for college students: their SSC GPA).
    gpa = np.clip(4.1 - 0.55 * z + rng.normal(0, 0.35, n_students), 1.0, 5.0).round(2)

    students, enr, att, sc, asg, eng = [], [], [], [], [], []
    for i in range(n_students):
        code = f"{code_prefix}{2026}{i + 1:04d}"
        name = f"{FIRST[rng.integers(len(FIRST))]} {LAST[rng.integers(len(LAST))]}"
        # Special demo cases (current cohort only): 0 = declining student (demo login),
        # 1 = enrolled but no data yet, 2 = stale data (records stop at week 4).
        zi, dec, last_week, no_data = z[i], decliner[i], weeks_elapsed, False
        if special_cases and i == 0:
            zi, dec = 0.3, True
        if special_cases and i == 1:
            no_data = True
        if special_cases and i == 2:
            last_week = 4
        row = {
            "student_code": code,
            "full_name": name,
            "program": programs[i],
            "year_of_study": int(year[i]),
            "prior_gpa": float(gpa[i]) if not (special_cases and i == 1) else None,
            "equity_group": equity[i],
            "latent": float(zi),
            "decliner": bool(dec),
        }
        if with_outcome:
            p_fail = _sigmoid(-2.2 + 1.5 * zi + 1.6 * dec + rng.normal(0, 0.4))
            row["outcome_at_risk"] = int(rng.random() < p_fail)
        students.append(row)

        for course in PROGRAMS[programs[i]]:
            enr.append({"student_code": code, "course_code": course})
            if no_data:
                continue
            c_eff = rng.normal(0, 0.3)
            for w in range(1, last_week + 1):
                drop = 1.0 if (dec and w >= 6) else 0.0
                week_start = term_start + timedelta(weeks=w - 1)
                for day in (0, 2):
                    p_att = _sigmoid(2.3 - 1.1 * zi - 1.8 * drop + c_eff)
                    u = rng.random()
                    if u < p_att:
                        status = "late" if rng.random() < 0.08 else "present"
                    else:
                        status = "excused" if rng.random() < 0.1 else "absent"
                    att.append({"student_code": code, "course_code": course,
                                "date": week_start + timedelta(days=day), "week": w, "status": status})
                logins = int(rng.poisson(max(0.3, 5.5 - 1.4 * zi - 3.2 * drop)))
                eng.append({"student_code": code, "course_code": course, "week": w, "week_start": week_start,
                            "logins": logins, "activity_minutes": int(logins * rng.uniform(15, 40))})
            for name_, (w, mx) in QUIZ_WEEKS.items():
                if w > last_week:
                    continue
                drop = 1.0 if (dec and w >= 6) else 0.0
                pct = float(np.clip(72 - 11 * zi - 16 * drop + c_eff * 10 + rng.normal(0, 9), 0, 100))
                sc.append({"student_code": code, "course_code": course, "assessment_name": name_,
                           "date": term_start + timedelta(weeks=w - 1, days=3), "week": w,
                           "score": round(pct / 100 * mx, 1), "max_score": float(mx)})
            for name_, w in ASSIGNMENT_WEEKS.items():
                if w > last_week:
                    continue
                drop = 1.0 if (dec and w >= 6) else 0.0
                p_miss = _sigmoid(-2.7 + 1.2 * zi + 1.8 * drop)
                p_late = float(np.clip(0.12 + 0.06 * zi, 0.02, 0.4))
                u = rng.random()
                status = "missing" if u < p_miss else ("late" if u < p_miss + p_late else "on_time")
                asg.append({"student_code": code, "course_code": course, "assignment_name": name_,
                            "due_date": term_start + timedelta(weeks=w - 1, days=4), "week": w, "status": status})

    return Cohort(
        students=pd.DataFrame(students),
        enrollments=pd.DataFrame(enr),
        attendance=pd.DataFrame(att),
        assessments=pd.DataFrame(sc),
        assignments=pd.DataFrame(asg),
        engagement=pd.DataFrame(eng),
    )
