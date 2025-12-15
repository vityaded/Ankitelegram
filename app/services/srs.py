from __future__ import annotations

from datetime import datetime, timedelta
from app.db.models import Review, ReviewState
from app.services.grader import Verdict

def _utcnow() -> datetime:
    return datetime.utcnow()

def apply_srs(
    review: Review | None,
    verdict: Verdict,
    now_utc: datetime,
    learning_steps_minutes: list[int],
    graduate_days: int,
    last_answer_raw: str,
    last_score: int,
) -> Review:
    if review is None:
        # first encounter -> learning step 0
        r = Review(
            state=ReviewState.learning.value,
            step_index=0,
            ease=2.5,
            interval_days=0,
            lapses=0,
            due_at=now_utc + timedelta(minutes=learning_steps_minutes[0]),
            last_answer_raw=last_answer_raw,
            last_score=last_score,
            updated_at=now_utc,
        )
        return r

    review.last_answer_raw = last_answer_raw
    review.last_score = last_score
    review.updated_at = now_utc

    # suspended stays suspended
    if review.state == ReviewState.suspended.value:
        return review

    if review.state in (ReviewState.new.value,):
        review.state = ReviewState.learning.value
        review.step_index = 0
        review.due_at = now_utc + timedelta(minutes=learning_steps_minutes[0])

    if review.state == ReviewState.learning.value:
        if verdict == Verdict.BAD:
            review.step_index = 0
            review.due_at = now_utc + timedelta(minutes=learning_steps_minutes[0])
            return review

        if verdict == Verdict.ALMOST:
            # do not advance; schedule next step time (or same step+1)
            idx = min(review.step_index + 1, len(learning_steps_minutes) - 1)
            review.due_at = now_utc + timedelta(minutes=learning_steps_minutes[idx])
            return review

        # OK
        review.step_index += 1
        if review.step_index >= len(learning_steps_minutes):
            review.state = ReviewState.review.value
            review.interval_days = graduate_days
            review.due_at = now_utc + timedelta(days=graduate_days)
        else:
            review.due_at = now_utc + timedelta(minutes=learning_steps_minutes[review.step_index])
        return review

    # review state
    if review.state == ReviewState.review.value:
        if verdict == Verdict.BAD:
            review.lapses += 1
            review.ease = max(1.3, review.ease - 0.2)
            review.interval_days = 1
            review.due_at = now_utc + timedelta(days=1)
            return review

        if verdict == Verdict.ALMOST:
            review.ease = max(1.3, review.ease - 0.15)
            review.interval_days = max(1, int(round(review.interval_days * 1.2))) or 1
            review.due_at = now_utc + timedelta(days=review.interval_days)
            return review

        # OK
        review.interval_days = max(1, int(round(review.interval_days * review.ease))) or 1
        review.due_at = now_utc + timedelta(days=review.interval_days)
        return review

    # fallback
    return review
