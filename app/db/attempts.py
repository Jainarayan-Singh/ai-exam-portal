"""
app/db/attempts.py
All PostgreSQL queries for the `exam_attempts` table.
"""

from typing import Optional, List, Dict
from app.db import fetch_one, fetch_all, execute, set_clause, insert_returning


_COLS = "id,student_id,exam_id,attempt_number,status,start_time,end_time"


def get_attempts_status_counts() -> Dict[str, int]:
    """Attempt count per status (completed / in_progress / ...) — one
    aggregate query, for the admin dashboard's Attempts chart."""
    try:
        rows = fetch_all("SELECT status, COUNT(*) AS count FROM exam_attempts GROUP BY status")
        return {r["status"]: r["count"] for r in rows}
    except Exception as e:
        print(f"[db.attempts] get_attempts_status_counts error: {e}")
        return {}


def get_top_attempted_exams(limit: int = 5) -> List[Dict]:
    """Most-attempted exams (top N by attempt count) — one aggregate JOIN
    query, for the dashboard's Most Attempted Exams chart."""
    try:
        return fetch_all(
            "SELECT ex.name AS name, COUNT(a.id) AS count FROM exam_attempts a "
            "JOIN exams ex ON ex.id = a.exam_id "
            "GROUP BY ex.id, ex.name ORDER BY count DESC LIMIT %s",
            (limit,),
        )
    except Exception as e:
        print(f"[db.attempts] get_top_attempted_exams error: {e}")
        return []


def get_active_attempt(user_id: int, exam_id: int) -> Optional[Dict]:
    """Return the most recent in_progress attempt for this user+exam."""
    try:
        return fetch_one(
            f"SELECT {_COLS} FROM exam_attempts WHERE student_id=%s AND exam_id=%s AND status=%s "
            "ORDER BY id DESC LIMIT 1",
            (user_id, exam_id, "in_progress"),
        )
    except Exception as e:
        print(f"[db.attempts] get_active_attempt error: {e}")
        return None


def get_latest_attempt(user_id: int, exam_id: int) -> Optional[Dict]:
    """Return the most recent attempt regardless of status."""
    try:
        return fetch_one(
            f"SELECT {_COLS} FROM exam_attempts WHERE student_id=%s AND exam_id=%s ORDER BY id DESC LIMIT 1",
            (user_id, exam_id),
        )
    except Exception as e:
        print(f"[db.attempts] get_latest_attempt error: {e}")
        return None


def get_completed_attempts_count(user_id: int, exam_id: int) -> int:
    try:
        row = fetch_one(
            "SELECT COUNT(*) AS count FROM exam_attempts WHERE student_id=%s AND exam_id=%s AND status=%s",
            (user_id, exam_id, "completed"),
        )
        return row["count"] if row else 0
    except Exception as e:
        print(f"[db.attempts] get_completed_attempts_count error: {e}")
        return 0


def get_all_attempts_for_exam(user_id: int, exam_id: int) -> List[Dict]:
    """All attempts (any status) for next attempt_number calculation."""
    try:
        return fetch_all(
            "SELECT id,attempt_number FROM exam_attempts WHERE student_id=%s AND exam_id=%s",
            (user_id, exam_id),
        )
    except Exception as e:
        print(f"[db.attempts] get_all_attempts_for_exam error: {e}")
        return []


def create_exam_attempt(attempt_data: Dict) -> Optional[Dict]:
    try:
        return insert_returning("exam_attempts", attempt_data)
    except Exception as e:
        print(f"[db.attempts] create_exam_attempt error: {e}")
        return None


def update_exam_attempt(attempt_id: int, updates: Dict) -> bool:
    try:
        sc, params = set_clause(updates)
        execute(f"UPDATE exam_attempts SET {sc} WHERE id=%s", params + [attempt_id])
        return True
    except Exception as e:
        print(f"[db.attempts] update_exam_attempt error: {e}")
        return False


def get_attempts_summary() -> List[Dict]:
    """
    Return all attempts with student+exam IDs for the admin attempts page.
    """
    try:
        return fetch_all("SELECT student_id,exam_id,status FROM exam_attempts")
    except Exception as e:
        print(f"[db.attempts] get_attempts_summary error: {e}")
        return []
