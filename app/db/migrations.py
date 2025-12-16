from __future__ import annotations

from sqlalchemy import inspect, text


def run_migrations(conn):
    insp = inspect(conn)

    # Enrollment mode column
    enroll_cols = [c["name"] for c in insp.get_columns("enrollments")]
    if "mode" not in enroll_cols:
        conn.execute(
            text(
                "ALTER TABLE enrollments ADD COLUMN mode VARCHAR(16) NOT NULL DEFAULT 'anki'"
            )
        )

    # Review watch-mode helpers
    review_cols = [c["name"] for c in insp.get_columns("reviews")]
    if "watch_failed" not in review_cols:
        conn.execute(
            text(
                "ALTER TABLE reviews ADD COLUMN watch_failed BOOLEAN NOT NULL DEFAULT 0"
            )
        )
    if "watch_streak" not in review_cols:
        conn.execute(
            text(
                "ALTER TABLE reviews ADD COLUMN watch_streak INTEGER NOT NULL DEFAULT 0"
            )
        )
