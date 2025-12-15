from __future__ import annotations

import html

from app.services.grader import Verdict
from app.utils.diff_highlight import highlight_diff


def format_compare(
    correct: str,
    user: str,
    score: int,
    verdict: Verdict,
    uk: str | None = None,
    max_len: int = 3500,
) -> str:
    icon = "✅" if verdict == Verdict.OK else ("🟨" if verdict == Verdict.ALMOST else "❌")

    if correct:
        corr_html, user_html = highlight_diff(correct, user or "")
        if not corr_html:
            corr_html = html.escape(correct, quote=False)
        if not user_html:
            user_html = html.escape(user or "", quote=False)
    else:
        corr_html = html.escape(correct or "", quote=False)
        user_html = html.escape(user or "", quote=False)

    lines = [f"{icon} {score}/100", f"Correct: {corr_html}"]
    if uk:
        uk_html = html.escape(uk, quote=False)
        lines.append(f"UA: {uk_html}")
    lines.append(f"You: {user_html}")

    msg = "\n".join(lines)
    if len(msg) > max_len:
        msg = msg[: max_len - 3] + "..."
    return msg
