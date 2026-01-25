from datetime import datetime, timedelta

from app.services.grader import Verdict
from app.services.srs import apply_srs_by_mode
from app.db.models import ReviewState


LEARNING_STEPS = [1, 10]
GRADUATE_DAYS = 1


def test_watch_first_ok_suspends():
    now = datetime.utcnow()
    updated = apply_srs_by_mode(
        review=None,
        verdict=Verdict.OK,
        now_utc=now,
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="ans",
        last_score=100,
        mode="watch",
        watch_target=2,
    )
    assert updated.state == ReviewState.suspended.value
    assert updated.due_at is None
    assert updated.watch_streak == 0
    assert updated.watch_failed is False


def test_watch_first_bad_enters_srs():
    now = datetime.utcnow()
    updated = apply_srs_by_mode(
        review=None,
        verdict=Verdict.BAD,
        now_utc=now,
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="ans",
        last_score=0,
        mode="watch",
        watch_target=2,
    )
    assert updated.watch_failed is True
    assert updated.watch_streak == 0
    assert updated.state in (ReviewState.learning.value, ReviewState.review.value)
    assert updated.due_at is not None
    assert updated.due_at <= now


def test_watch_requires_two_consecutive_ok_after_failure():
    now = datetime.utcnow()
    review = apply_srs_by_mode(
        review=None,
        verdict=Verdict.BAD,
        now_utc=now,
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="first",
        last_score=0,
        mode="watch",
        watch_target=2,
    )
    assert review.watch_failed is True

    review = apply_srs_by_mode(
        review=review,
        verdict=Verdict.OK,
        now_utc=now + timedelta(minutes=1),
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="ok1",
        last_score=100,
        mode="watch",
        watch_target=2,
    )
    assert review.watch_streak == 1

    review = apply_srs_by_mode(
        review=review,
        verdict=Verdict.BAD,
        now_utc=now + timedelta(minutes=2),
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="bad_again",
        last_score=0,
        mode="watch",
        watch_target=2,
    )
    assert review.watch_streak == 0
    assert review.due_at is not None
    assert review.due_at <= now + timedelta(minutes=2)

    review = apply_srs_by_mode(
        review=review,
        verdict=Verdict.OK,
        now_utc=now + timedelta(minutes=3),
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="ok2",
        last_score=100,
        mode="watch",
        watch_target=2,
    )
    review = apply_srs_by_mode(
        review=review,
        verdict=Verdict.OK,
        now_utc=now + timedelta(minutes=4),
        learning_steps_minutes=LEARNING_STEPS,
        graduate_days=GRADUATE_DAYS,
        last_answer_raw="ok3",
        last_score=100,
        mode="watch",
        watch_target=2,
    )

    assert review.watch_streak >= 2
    assert review.state == ReviewState.suspended.value
    assert review.due_at is None
