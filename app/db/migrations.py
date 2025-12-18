from __future__ import annotations

from sqlalchemy import inspect, text


def run_migrations(conn):
    insp = inspect(conn)

    # Deck folders table
    if "deck_folders" not in insp.get_table_names():
        conn.execute(
            text(
                """
                CREATE TABLE deck_folders (
                    id VARCHAR(36) PRIMARY KEY,
                    admin_tg_id BIGINT NOT NULL,
                    path VARCHAR(512) NOT NULL,
                    CONSTRAINT uq_folder_admin_path UNIQUE (admin_tg_id, path)
                )
                """
            )
        )

    # Deck folder FK
    deck_cols = [c["name"] for c in insp.get_columns("decks")]
    if "folder_id" not in deck_cols:
        conn.execute(
            text(
                "ALTER TABLE decks ADD COLUMN folder_id VARCHAR(36) NULL REFERENCES deck_folders(id)"
            )
        )

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
