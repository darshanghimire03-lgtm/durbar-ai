import pytest

import config
from ai_engine import DurbarEngine
from llm import OllamaBrain, SessionStore


class FakeData:
    def get_calendar_year(self, y):
        if y != 2083:
            return None
        return {"8": {"festival": {"e1": {"title": "Tihar", "startDay": 10, "endDay": 14, "description": "Festival of lights"}}}}

    def get_units(self):
        return {"computer": {"u1": {"name": "Networking", "notes": {"n1": {
            "title": "Intro to Networks", "description": "basics", "createdAt": 1,
            "pdfs": {"a": "https://x.test/net.pdf"}}}}}}

    def get_users(self):
        return {"u1": {"fullName": "Ram Sharma", "role": "student", "className": "10"}}


class FakeClient:
    """Mimics ollama.Client.chat(stream=True): `script` is a list of rounds; each round a list of message dicts."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def chat(self, **kw):
        self.calls.append(kw)
        round_ = self.script.pop(0)
        if isinstance(round_, Exception):
            raise round_
        return iter({"message": m} for m in round_)


def make(monkeypatch, script, model="test-model"):
    monkeypatch.setattr(config, "OLLAMA_MODEL", model)
    client = FakeClient(script)
    eng = DurbarEngine(FakeData(), brain=None)
    eng.brain = OllamaBrain(tools=eng.brain.tools, client=client)
    eng.today_bs = lambda: (2083, 7, 22)
    return eng, client


def test_rules_never_touch_llm(monkeypatch):
    eng, client = make(monkeypatch, [])
    assert "Hello" in eng.answer("hi") or eng.answer("hi")
    assert client.calls == []


def test_disabled_brain_gives_fallback(monkeypatch):
    eng, client = make(monkeypatch, [], model="")
    assert eng.answer("explain photosynthesis please") == eng._t("fallback", "en")


def test_llm_answers_unknown_and_remembers_session(monkeypatch):
    eng, client = make(monkeypatch, [[{"content": "Plants "}, {"content": "make food."}], [{"content": "Because sunlight."}]])
    assert eng.answer("explain photosynthesis", session_id="s1") == "Plants make food."
    assert eng.answer("and why?", session_id="s1") == "Because sunlight."
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    assert second[1]["content"] == "explain photosynthesis"
    assert "Kartik 22" in second[0]["content"]  # today's BS date is in the system prompt


def test_tool_call_uses_real_calendar_data(monkeypatch):
    call = {"function": {"name": "get_school_calendar", "arguments": {"kind": "festival", "when": "next"}}}
    eng, client = make(monkeypatch, [[{"content": "", "tool_calls": [call]}], [{"content": "Tihar starts soon!"}]])
    assert eng.answer("is there any celebration coming up soon at school") == "Tihar starts soon!"
    tool_msgs = [m for m in client.calls[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 1 and "Tihar" in tool_msgs[0]["content"]
    assert client.calls[1]["tools"] is not None


def test_notes_and_person_tools(monkeypatch):
    eng, _ = make(monkeypatch, [])
    notes = eng.brain.tools["find_study_notes"]("computer networking pdf")
    assert "Intro to Networks" in notes and "https://x.test/net.pdf" in notes
    assert "Ram Sharma" in eng.brain.tools["find_person"]("ram")


def test_tool_loop_is_bounded(monkeypatch):
    call = {"function": {"name": "find_person", "arguments": {"name": "ram"}}}
    rounds = [[{"tool_calls": [call]}]] * config.LLM_MAX_TOOL_ROUNDS + [[{"content": "done"}]]
    eng, client = make(monkeypatch, rounds)
    assert eng.answer("tell me stuff about the class captain") == "done"
    assert client.calls[-1]["tools"] is None  # last round must answer, not call tools


def test_llm_failure_falls_back(monkeypatch):
    eng, _ = make(monkeypatch, [ConnectionError("down")])
    assert eng.answer("explain photosynthesis") == eng._t("fallback", "en")


def test_gate_blocks_llm_but_not_rules(monkeypatch):
    eng, client = make(monkeypatch, [])
    assert eng.answer("explain photosynthesis", llm_gate=lambda: False) == eng._t("rate_limited", "en")
    assert client.calls == []
    assert eng.answer("hi", llm_gate=lambda: False) != eng._t("rate_limited", "en")


def test_bad_tool_arguments_do_not_crash(monkeypatch):
    eng, _ = make(monkeypatch, [])
    assert "invalid" in eng.brain._run_tool("find_person", {"bogus": 1})
    assert "Unknown" in eng.brain._run_tool("rm_rf", {})


def test_session_store_caps_and_expires():
    s = SessionStore(max_sessions=2, max_turns=1, ttl=1000)
    for i in range(3):
        s.add(f"s{i}", "q", "a")
    assert s.get("s0") == [] and s.get("s2")
    s.add("s2", "q2", "a2")
    assert len(s.get("s2")) == 2  # only the latest turn kept
    s.ttl = -1
    assert s.get("s2") == []
