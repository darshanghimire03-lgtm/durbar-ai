import re

_MOCK = re.compile(
    r"\bmock[\s\-_]*(?:tests?|exams?|papers?|questions?|mcqs?|quiz(?:zes)?|sets?|answers?)\b",
    re.I,
)

MOCK_REPLY = (
    "I can't give mock test questions or answers. Mock tests are in the Mock Test section of the app, "
    "so try them there on your own first. If a topic from one of them feels confusing, tell me the topic "
    "and I'll walk you through it."
)


def is_mock_request(message: str) -> bool:
    return bool(_MOCK.search(message))