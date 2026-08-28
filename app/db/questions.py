"""
app/db/questions.py
All PostgreSQL queries related to the `questions` table.

DELETE FIX (v2):
  delete_question() and delete_questions_bulk() now purge FK-dependent
  child rows (responses, question_discussions, discussion_counts) BEFORE
  deleting the question row itself.

  Correct deletion order per the schema:
    1. responses            (FK -> questions.id)
    2. question_discussions (FK -> questions.id)
    3. discussion_counts    (FK -> questions.id)
    4. questions             (the row itself)
"""

from typing import Optional, List, Dict
from app.db import fetch_one, fetch_all, execute, set_clause, insert_returning, insert_many


_ALL_COLS = (
    "id,exam_id,question_text,option_a,option_b,option_c,option_d,"
    "correct_answer,question_type,image_path,positive_marks,negative_marks,tolerance,metadata"
)


def get_question_by_id(question_id: int) -> Optional[Dict]:
    try:
        return fetch_one(f"SELECT {_ALL_COLS} FROM questions WHERE id=%s", (question_id,))
    except Exception as e:
        print(f"[db.questions] get_question_by_id error: {e}")
        return None


def get_questions_by_exam(exam_id: int) -> List[Dict]:
    try:
        return fetch_all(f"SELECT {_ALL_COLS} FROM questions WHERE exam_id=%s ORDER BY id", (exam_id,))
    except Exception as e:
        print(f"[db.questions] get_questions_by_exam error: {e}")
        return []


def create_question(question_data: Dict) -> Optional[Dict]:
    try:
        return insert_returning("questions", question_data)
    except Exception as e:
        print(f"[db.questions] create_question error: {e}")
        return None


def create_questions_bulk(questions: List[Dict]) -> bool:
    try:
        insert_many("questions", questions)
        return True
    except Exception as e:
        print(f"[db.questions] create_questions_bulk error: {e}")
        return False


def update_question(question_id: int, updates: Dict) -> bool:
    try:
        sc, params = set_clause(updates)
        execute(f"UPDATE questions SET {sc} WHERE id=%s", params + [question_id])
        return True
    except Exception as e:
        print(f"[db.questions] update_question error: {e}")
        return False


# ─────────────────────────────────────────────
# Optional per-question metadata (questions.metadata JSONB) — e.g. a
# previous-year source tag like "ESE 2021". Deliberately open-ended: no
# separate column per metadata kind, just keys inside this one JSONB blob.
# ─────────────────────────────────────────────

def build_question_metadata(source_tag: Optional[str]) -> Optional[Dict]:
    """Canonical shape for the metadata this app currently understands —
    the ONE place that decides what a "source tag" value becomes in
    storage. Every create path (single add, batch add, CSV import) should
    build its metadata column value through this, not by hand, so the
    representation never drifts between callers. Returns None for a blank
    tag (nothing to store) — a fresh row's metadata column simply stays NULL."""
    tag = (source_tag or "").strip()
    return {"source_tag": tag} if tag else None


def merge_question_metadata(question_id: int, patch: Dict) -> bool:
    """Shallow-merge `patch` into an EXISTING question's metadata, leaving
    every other key already stored there untouched — e.g. a question saved
    with {"difficulty": "medium", "source_tag": "ESE 2021"} keeps its
    difficulty if only source_tag is edited afterward. A key whose patch
    value is falsy/None is REMOVED from metadata rather than stored as an
    empty string, so clearing the Source Tag field deletes 'source_tag'
    instead of leaving clutter behind. This is the only function that
    should ever mutate metadata after a row already exists — every editor
    (admin single-edit today, anything else later) should call this
    instead of writing `metadata` through update_question() directly,
    which would replace the whole JSONB value."""
    try:
        set_keys = {k: v for k, v in patch.items() if v not in (None, "")}
        remove_keys = [k for k, v in patch.items() if v in (None, "")]
        if set_keys:
            execute(
                "UPDATE questions SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb WHERE id=%s",
                (set_keys, question_id),
            )
        for k in remove_keys:
            execute(
                "UPDATE questions SET metadata = COALESCE(metadata,'{}'::jsonb) - %s WHERE id=%s",
                (k, question_id),
            )
        return True
    except Exception as e:
        print(f"[db.questions] merge_question_metadata error: {e}")
        return False


def update_questions_by_type(exam_id: int, question_type: str, updates: Dict) -> int:
    """Set-based update for every question of a given type within an exam —
    one statement instead of fetch-all + per-row update_question() calls
    (flagged in the architecture audit). Returns the number of rows updated."""
    try:
        sc, params = set_clause(updates)
        return execute(
            f"UPDATE questions SET {sc} WHERE exam_id=%s AND UPPER(question_type)=UPPER(%s)",
            params + [exam_id, question_type],
        )
    except Exception as e:
        print(f"[db.questions] update_questions_by_type error: {e}")
        return 0


def _purge_question_children(question_id: int) -> None:
    """
    Delete all FK-dependent child rows for a question BEFORE deleting
    the question itself, to avoid FK constraint violations.

    Deletion order (safe per schema FK graph):
      1. responses            - FK on question_id
      2. question_discussions - FK on question_id
      3. discussion_counts    - FK on question_id (PK = question_id)
    """
    try:
        execute("DELETE FROM responses WHERE question_id=%s", (question_id,))
    except Exception as e:
        print(f"[db.questions] purge responses for q={question_id}: {e}")

    try:
        execute("DELETE FROM question_discussions WHERE question_id=%s", (question_id,))
    except Exception as e:
        print(f"[db.questions] purge discussions for q={question_id}: {e}")

    try:
        execute("DELETE FROM discussion_counts WHERE question_id=%s", (question_id,))
    except Exception as e:
        print(f"[db.questions] purge discussion_counts for q={question_id}: {e}")


def delete_question(question_id: int) -> bool:
    """Delete a single question and ALL FK-dependent child rows."""
    try:
        _purge_question_children(question_id)
        execute("DELETE FROM questions WHERE id=%s", (question_id,))
        return True
    except Exception as e:
        print(f"[db.questions] delete_question error: {e}")
        return False


def delete_questions_bulk(question_ids: List[int]) -> int:
    """
    Delete multiple questions and ALL their FK-dependent child rows.
    Returns count of successfully deleted questions.
    """
    if not question_ids:
        return 0

    try:
        execute("DELETE FROM responses WHERE question_id = ANY(%s)", (question_ids,))
    except Exception as e:
        print(f"[db.questions] bulk purge responses: {e}")

    try:
        execute("DELETE FROM question_discussions WHERE question_id = ANY(%s)", (question_ids,))
    except Exception as e:
        print(f"[db.questions] bulk purge discussions: {e}")

    try:
        execute("DELETE FROM discussion_counts WHERE question_id = ANY(%s)", (question_ids,))
    except Exception as e:
        print(f"[db.questions] bulk purge discussion_counts: {e}")

    try:
        execute("DELETE FROM questions WHERE id = ANY(%s)", (question_ids,))
        return len(question_ids)
    except Exception as e:
        print(f"[db.questions] bulk delete (batch) failed, falling back to per-row: {e}")

    deleted = 0
    for qid in question_ids:
        try:
            execute("DELETE FROM questions WHERE id=%s", (qid,))
            deleted += 1
        except Exception as e2:
            print(f"[db.questions] delete_questions_bulk error on {qid}: {e2}")
    return deleted
