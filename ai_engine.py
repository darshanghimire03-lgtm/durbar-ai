"""Durbar AI engine: simple rule-based understanding (no LLM, no NLP library).

Flow for every message:
  1. normalise the text (lowercase, strip punctuation, keep Nepali letters)
  2. notes request?      -> search units/notes in Firebase
  3. calendar request?   -> find the next holiday/exam/event in the calendar
  4. small talk?         -> answer from knowledge.json
  5. otherwise           -> "I don't know that yet. You can teach me!"
"""
import json
import logging
import unicodedata
from datetime import datetime

import config
from firebase_data import DataUnavailable, children

log = logging.getLogger("durbar.engine")

BS_MONTHS = [
    "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]
# Lets calendar month keys be written as names instead of numbers.
MONTH_NAME_TO_NUM = {
    "baisakh": 1, "baishakh": 1, "jestha": 2, "jeth": 2, "ashadh": 3, "asar": 3, "ashad": 3,
    "shrawan": 4, "srawan": 4, "saun": 4, "bhadra": 5, "bhadau": 5, "ashwin": 6, "asoj": 6,
    "ashoj": 6, "kartik": 7, "kattik": 7, "mangsir": 8, "mangshir": 8, "poush": 9, "push": 9,
    "magh": 10, "falgun": 11, "fagun": 11, "chaitra": 12, "chait": 12,
}


# ----------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------
def normalize(text: str) -> str:
    """Lowercase, replace punctuation/symbols with spaces, collapse whitespace.

    Only Unicode punctuation (P*) and symbols (S*) are removed, so Nepali
    letters and vowel signs (matras) are preserved.
    """
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text)
    return " ".join(text.split())


def _is_deva(s: str) -> bool:
    return any("\u0900" <= c <= "\u097f" for c in s)


def _has_phrase(norm: str, tokens, words) -> bool:
    """True if any word/phrase appears in the message (whole words only)."""
    padded = f" {norm} "
    for w in words:
        if " " in w:
            if f" {w} " in padded:
                return True
        else:
            for t in tokens:
                if t == w or (_is_deva(w) and t.startswith(w)):
                    return True
    return False


def _term_in(term: str, words) -> bool:
    """Basic keyword match: exact word, or a simple stem match ('program'~'programming')."""
    for w in words:
        if w == term:
            return True
        if _is_deva(term) and w.startswith(term):
            return True
        if len(term) >= 4 and len(w) >= 4 and (w.startswith(term) or term.startswith(w)):
            return True
    return False


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _first_int(*values):
    for v in values:
        n = _to_int(v)
        if n is not None:
            return n
    return None


def _parse_month(key):
    n = _to_int(key)
    if n is not None:
        return n
    return MONTH_NAME_TO_NUM.get(normalize(key))


def _fmt_date(d) -> str:
    year, month, day = d
    return f"{day} {BS_MONTHS[month - 1]} {year} BS"


def _first_url(item):
    """Resources may be plain URL strings or small objects with a url field."""
    if isinstance(item, str):
        url = item.strip()
    elif isinstance(item, dict):
        url = ""
        for key in ("url", "link", "downloadUrl", "downloadURL", "src"):
            if isinstance(item.get(key), str):
                url = item[key].strip()
                break
    else:
        return None
    return url if url.lower().startswith(("http://", "https://")) else None


def _urls(node):
    found = []
    for _, item in children(node):
        url = _first_url(item)
        if url:
            found.append(url)
    return found


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ----------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------
class DurbarEngine:
    def __init__(self, data, knowledge_path=None):
        self.data = data
        path = knowledge_path or config.KNOWLEDGE_FILE
        with open(path, encoding="utf-8") as f:
            self.kb = json.load(f)

        self.msg = self.kb.get("messages", {})
        # small-talk phrases, longest first so "how are you" beats "you"
        self.smalltalk = sorted(
            ((normalize(k).split(), v) for k, v in self.kb.get("responses", {}).items()),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
        intents = self.kb.get("intents", {})
        self.notes_words = [normalize(w) for w in intents.get("notes_words", [])]
        self.calendar_kinds = [
            {**k, "words": [normalize(w) for w in k["words"]]} for k in intents.get("calendar", [])
        ]
        # subject aliases: alias -> canonical name, and canonical -> all variants
        self.alias_to_subject = {}
        self.variants = {}
        for canon, aliases in self.kb.get("subjects", {}).items():
            names = {normalize(canon)} | {normalize(a) for a in aliases}
            self.variants[normalize(canon)] = names
            for name in names:
                self.alias_to_subject[name] = normalize(canon)
        self.format_words = {
            fmt: [normalize(w) for w in words] for fmt, words in self.kb.get("format_words", {}).items()
        }
        self.stopwords = {normalize(w) for w in self.kb.get("stopwords", [])}

    def _m(self, key: str) -> str:
        return self.msg.get(key, "")

    # ---- public entry point -----------------------------------------
    def answer(self, message: str) -> str:
        norm = normalize(message or "")
        if not norm:
            return self._m("empty")
        tokens = norm.split()
        try:
            if _has_phrase(norm, tokens, self.notes_words):
                return self._notes_reply(norm, tokens)
            kind = self._calendar_kind(norm, tokens)
            if kind:
                return self._calendar_reply(kind)
        except DataUnavailable:
            return self._m("db_unavailable")
        except Exception:
            log.exception("Unexpected error while answering")
            return self._m("error")

        reply = self._smalltalk(tokens)
        return reply if reply else self._m("fallback")

    # ---- small talk ---------------------------------------------------
    def _smalltalk(self, tokens):
        for phrase, reply in self.smalltalk:
            n = len(phrase)
            if n == 0 or len(tokens) - n > 2:  # allow at most 2 extra words ("hello durbar ai")
                continue
            for i in range(len(tokens) - n + 1):
                if tokens[i:i + n] == phrase:
                    return reply
        return None

    # ---- calendar -----------------------------------------------------
    def today_bs(self):
        """Today's Bikram Sambat date as (year, month, day) in Nepal time, or None."""
        try:
            import nepali_datetime

            ad_today = datetime.now(config.NEPAL_TZ).date()
            bs = nepali_datetime.date.from_datetime_date(ad_today)
            return (bs.year, bs.month, bs.day)
        except Exception as exc:
            log.error("BS date conversion failed: %s", type(exc).__name__)
            return None

    def _calendar_kind(self, norm, tokens):
        for kind in self.calendar_kinds:
            if _has_phrase(norm, tokens, kind["words"]):
                return kind
        return None

    @staticmethod
    def _parse_calendar(year, node, wanted_types):
        """Turn calendar/{year} into a flat list of events with real date fields."""
        events = []
        for month_key, month_node in children(node):
            path_month = _parse_month(month_key)
            for type_key, type_node in children(month_node):
                etype = type_key.strip().lower()
                if etype not in wanted_types:
                    continue
                for event_id, ev in children(type_node):
                    if not isinstance(ev, dict):
                        continue
                    sm = _first_int(ev.get("startMonth"), path_month)
                    sd = _first_int(ev.get("startDay"), ev.get("day"), ev.get("date"))
                    em = _first_int(ev.get("endMonth"), sm)
                    ed = _first_int(ev.get("endDay"), sd)
                    if None in (sm, sd, em, ed):
                        continue  # incomplete record: skip, never guess
                    if not (1 <= sm <= 12 and 1 <= em <= 12 and 1 <= sd <= 32 and 1 <= ed <= 32):
                        continue
                    end_year = year if (em, ed) >= (sm, sd) else year + 1  # spans new year
                    events.append({
                        "id": event_id,
                        "type": etype,
                        "title": str(ev.get("title") or ev.get("name") or "").strip(),
                        "description": str(ev.get("description") or "").strip(),
                        "start": (year, sm, sd),
                        "end": (end_year, em, ed),
                    })
        return events

    def _calendar_reply(self, kind):
        today = self.today_bs()
        if today is None:
            return self._m("date_unavailable")
        year, month, _ = today
        types = set(kind["types"])

        events = self._parse_calendar(year, self.data.get_calendar_year(year), types)
        if month == 1:  # an event from last Chaitra may still be running
            events += self._parse_calendar(year - 1, self.data.get_calendar_year(year - 1), types)

        def upcoming(evts):
            return sorted((e for e in evts if e["end"] >= today), key=lambda e: (e["start"], e["end"]))

        found = upcoming(events)
        if not found:  # nothing left this year, look at next year
            events += self._parse_calendar(year + 1, self.data.get_calendar_year(year + 1), types)
            found = upcoming(events)

        label = kind["label"]
        if not found:
            return (f"I couldn't find any upcoming {label} in the calendar. "
                    "I don't want to guess, so please check with your school.")

        ev = found[0]
        title = ev["title"] or f"Untitled {ev['type'].replace('_', ' ')}"
        if ev["start"] == ev["end"]:
            date_text = _fmt_date(ev["start"])
        else:
            date_text = f"{_fmt_date(ev['start'])} to {_fmt_date(ev['end'])}"

        if ev["start"] <= today:
            head = f"\"{title}\" is going on right now (until {_fmt_date(ev['end'])})."
        else:
            head = f"Your next {label} is \"{title}\" ({ev['type'].replace('_', ' ')})."
        lines = [head, f"Date: {date_text}"]
        if ev["description"]:
            lines.append(f"Details: {ev['description']}")
        return "\n".join(lines)

    # ---- educational notes -------------------------------------------
    def _query_terms(self, tokens, drop):
        terms = []
        for t in tokens:
            if t in self.stopwords or t in drop:
                continue
            canon = self.alias_to_subject.get(t)
            if canon is None and _is_deva(t):
                for alias, c in self.alias_to_subject.items():
                    if _is_deva(alias) and t.startswith(alias):
                        canon = c
                        break
            term = canon or t
            if term not in terms:
                terms.append(term)
        return terms

    def _hits(self, term, words) -> bool:
        return any(_term_in(v, words) for v in self.variants.get(term, {term}))

    def _notes_reply(self, norm, tokens):
        wanted_formats = {f for f, words in self.format_words.items() if _has_phrase(norm, tokens, words)}
        drop = set(self.notes_words) | {w for ws in self.format_words.values() for w in ws}
        terms = self._query_terms(tokens, drop)

        units = self.data.get_units()
        subject_keys, entries = [], []
        for subject_key, subject_node in children(units):
            subject_keys.append(subject_key)
            key_words = normalize(subject_key.replace("_", " ").replace("-", " ")).split()
            for unit_id, unit in children(subject_node):
                if not isinstance(unit, dict):
                    continue
                unit_name = str(unit.get("name") or unit_id)
                for note_id, note in children(unit.get("notes")):
                    if not isinstance(note, dict):
                        continue
                    entries.append({
                        "subject": subject_key,
                        "key_words": key_words,
                        "unit": unit_name,
                        "title": str(note.get("title") or "Untitled note"),
                        "description": str(note.get("description") or ""),
                        "created": _num(note.get("createdAt")),
                        "pdfs": _urls(note.get("pdfs")),
                        "photos": _urls(note.get("photos")),
                        "youtube": _urls(note.get("youtubeLinks")),
                    })

        # which query terms name a subject (e.g. "computer")?
        subject_terms = {t for t in terms if any(self._hits(t, e["key_words"]) for e in entries)}
        subject_terms |= {t for t in terms if any(self._hits(t, normalize(k).split()) for k in subject_keys)}
        other_terms = [t for t in terms if t not in subject_terms]

        def score(e):
            title_w = normalize(e["title"]).split()
            desc_w = normalize(e["description"]).split()
            unit_w = normalize(e["unit"]).split()
            s = 0
            for t in other_terms:
                s += 3 if self._hits(t, title_w) else 0
                s += 2 if self._hits(t, unit_w) else 0
                s += 1 if self._hits(t, desc_w) else 0
            return s

        relaxed_for = None
        if subject_terms:
            pool = [e for e in entries if any(self._hits(t, e["key_words"]) for t in subject_terms)]
            if other_terms:
                matched = [e for e in pool if score(e) > 0]
                if matched:
                    pool = matched
                else:
                    relaxed_for = " ".join(other_terms)
            topic = " / ".join(sorted(subject_terms))
        else:
            if not terms:
                hint = self._m("ask_subject")
                if subject_keys:
                    hint += " Available subjects: " + ", ".join(subject_keys[:15]) + "."
                return hint
            pool = [e for e in entries if score(e) > 0]
            topic = " ".join(terms)

        if not pool:
            msg = f"I couldn't find any notes matching \"{topic}\"."
            if subject_keys:
                msg += " Available subjects: " + ", ".join(subject_keys[:15]) + "."
            return msg

        format_note = ""
        if wanted_formats:
            attr = {"pdf": "pdfs", "photo": "photos", "youtube": "youtube"}
            filtered = [e for e in pool if all(e[attr[f]] for f in wanted_formats)]
            if filtered:
                pool = filtered
            else:
                names = {"pdf": "a PDF", "photo": "an image", "youtube": "a YouTube link"}
                format_note = ("I couldn't find notes with " + " and ".join(names[f] for f in sorted(wanted_formats))
                               + ", but here are the notes I have. ")

        pool.sort(key=lambda e: (-score(e), -e["created"]))
        shown = pool[:3]

        if relaxed_for:
            intro = f"I couldn't find notes specifically about \"{relaxed_for}\", but here are notes for {topic}:"
        else:
            intro = f"Here are the notes I found for {topic}:"
        lines = [format_note + intro, ""]
        for i, e in enumerate(shown, 1):
            lines.append(f"{i}. {e['title']} (Subject: {e['subject']}, Unit: {e['unit']})")
            if e["description"]:
                desc = e["description"]
                lines.append("   " + (desc if len(desc) <= 200 else desc[:197] + "..."))
            for label, key in (("PDF", "pdfs"), ("Image", "photos"), ("YouTube", "youtube")):
                for url in e[key][:3]:
                    lines.append(f"   {label}: {url}")
            lines.append("")
        if len(pool) > len(shown):
            lines.append(f"...and {len(pool) - len(shown)} more. Ask with a chapter name to narrow it down.")
        return "\n".join(lines).strip()
