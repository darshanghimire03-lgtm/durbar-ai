import time
from typing import Any

from app.services.cards import mock_card
from app.services.firebase import search_mocks
from app.tools.base import ToolContext, ToolResult, definition
from app.utils.text import to_int, truthy

TTL_SECONDS = 3600
MAX_SESSIONS = 500
LETTERS = "ABCDEFGH"

_sessions: dict[str, dict[str, Any]] = {}

HIDDEN_NOTE = (
    "Correct answers are kept on the server. Never state, hint or guess them. "
    "After the user answers, call check_mock_answers."
)

DEFINITIONS = [
    definition(
        "get_mock_questions",
        "Get random multiple choice mock test questions for a subject. Answers are hidden from users and from "
        "you. Call without a subject to list available subjects.",
        {
            "subject": {"type": "string", "description": "Subject name"},
            "count": {"type": "integer", "description": "Number of questions, 1-10, default 5"},
        },
    ),
    definition(
        "check_mock_answers",
        "Check the user's answers for the latest mock test. Pass each question number with the selected option "
        "letter. Set reveal true only when the user asks to see the answers. Returns correctness and the right "
        "option for the answered questions.",
        {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer", "description": "Question number shown to the user"},
                        "selected": {"type": "string", "description": "Option letter A, B, C or D"},
                    },
                },
                "description": "The user's answers",
            },
            "reveal": {"type": "boolean", "description": "Show the right answers for all questions"},
        },
    ),
]


def _save(key: str, subject: str, questions: list[dict]) -> None:
    _sessions[key] = {"subject": subject, "questions": questions, "at": time.monotonic()}
    if len(_sessions) > MAX_SESSIONS:
        _sessions.pop(next(iter(_sessions)))


def _load(key: str) -> dict[str, Any] | None:
    session = _sessions.get(key)
    if not session:
        return None
    if time.monotonic() - session["at"] > TTL_SECONDS:
        _sessions.pop(key, None)
        return None
    return session


def _to_index(value: Any) -> int:
    text = str(value if value is not None else "").strip().upper()
    if len(text) == 1 and text in LETTERS:
        return LETTERS.index(text)
    if len(text) == 1 and text in "12345678":
        return int(text) - 1
    return -1


def _right(q: dict) -> dict[str, Any]:
    idx = q["answer_index"]
    ok = 0 <= idx < len(q["options"])
    return {
        "right_option": LETTERS[idx] if ok else None,
        "right_text": q["options"][idx] if ok else None,
    }


async def get_mock_questions(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    res = await search_mocks(args.get("subject"), args.get("count"))
    if res.get("error") or "questions" not in res:
        return ToolResult(data=res)

    _save(ctx.session_key, res["subject_key"], res["questions"])
    questions = [
        {"number": i + 1, "question": q["question"], "options": q["options"]}
        for i, q in enumerate(res["questions"])
    ]
    return ToolResult(
        data={
            "subject": res["subject_key"],
            "total_available": res["total_available"],
            "note": HIDDEN_NOTE,
            "questions": questions,
        },
        brief={"subject": res["subject_key"], "count": len(questions), "note": HIDDEN_NOTE},
        card=mock_card(res["subject_key"], questions),
    )


async def check_mock_answers(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    session = _load(ctx.session_key)
    if not session:
        return ToolResult(data={"error": "No active mock test. Ask the user to start a new one."})

    questions = session["questions"]
    given = args.get("answers") if isinstance(args.get("answers"), list) else []
    answered: set[int] = set()
    results: list[dict[str, Any]] = []

    for item in given:
        if not isinstance(item, dict):
            continue
        number = to_int(item.get("number"))
        if not 1 <= number <= len(questions):
            results.append({"number": number, "error": "No such question"})
            continue
        q = questions[number - 1]
        answered.add(number)
        idx = _to_index(item.get("selected"))
        results.append(
            {
                "number": number,
                "selected": LETTERS[idx] if idx >= 0 else None,
                "correct": idx == q["answer_index"],
                **_right(q),
            }
        )

    if truthy(args.get("reveal")):
        for i, q in enumerate(questions):
            if i + 1 not in answered:
                results.append({"number": i + 1, "selected": None, **_right(q)})

    results.sort(key=lambda r: r["number"])
    score = sum(1 for r in results if r.get("correct") is True)
    return ToolResult(
        data={
            "subject": session["subject"],
            "total_questions": len(questions),
            "answered": len(answered),
            "score": score,
            "results": results,
        }
    )


HANDLERS = {"get_mock_questions": get_mock_questions, "check_mock_answers": check_mock_answers}