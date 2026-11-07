import ast
import logging
import operator
import re
import unicodedata
from datetime import datetime

import config
import tense_lab
from firebase_data import DataUnavailable, children
from llm_client import LLMClient
from tiny_model import TinyModel
from training_data import DATA, EMPTY, FALLBACK

log = logging.getLogger("durbar.engine")

BS_MONTHS = ["Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
             "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"]
MONTH_NAME_TO_NUM = {
    "baisakh": 1, "baishakh": 1, "jestha": 2, "jeth": 2, "ashadh": 3, "asar": 3, "ashad": 3,
    "shrawan": 4, "srawan": 4, "saun": 4, "bhadra": 5, "bhadau": 5, "ashwin": 6, "asoj": 6,
    "ashoj": 6, "kartik": 7, "kattik": 7, "mangsir": 8, "mangshir": 8, "poush": 9, "push": 9,
    "magh": 10, "falgun": 11, "fagun": 11, "chaitra": 12, "chait": 12,
}
NAME_KEYS = ("fullName", "full_name", "fullname", "name", "displayName")
IMAGE_KEYS = ("profileImageUrl", "profileImageURL", "profileImage", "profilePicture", "profilePic",
              "photoUrl", "photoURL", "imageUrl", "imageURL", "image", "avatar")
ROLE_KEYS = ("role", "userRole", "userType", "type")
CLASS_KEYS = ("className", "class", "grade", "classLevel", "studentClass")
SUBJECT_KEYS = ("assignedSubjects", "assignedSubject", "subjects", "subject")
SUBJECT_NAME_KEYS = ("name", "title", "subject", "subjectName")
MAX_PROFILES = 3
MAX_NOTES = 3
MODEL_THRESHOLD = 0.65

NOTES_WORDS = ["note", "notes", "pdf", "pdfs", "chapter", "chapters", "material", "materials",
               "resource", "resources", "youtube", "video", "videos"]
PROFILE_WORDS = ["profile", "profiles", "account", "accounts", "who is", "details of", "detail of",
                 "info of", "information of", "profile picture", "photo of", "picture of", "pic of", "image of"]
PROFILE_FILLERS = {"details", "detail", "info", "information", "picture", "photo", "image", "pic",
                   "name", "full", "send", "of", "about", "show", "give", "me", "please"}
CALENDAR_KINDS = [
    {"types": {"exam", "test"}, "label": "exam or test", "words": ["exam", "exams", "examination", "test", "tests"]},
    {"types": {"school_event"}, "label": "school event", "words": ["school event", "event", "events"]},
    {"types": {"emergency"}, "label": "emergency holiday", "words": ["emergency"]},
    {"types": {"vacation"}, "label": "vacation", "words": ["vacation", "vacations", "break"]},
    {"types": {"festival"}, "label": "festival", "words": ["festival", "festivals"]},
    {"types": {"emergency", "vacation", "festival"}, "label": "holiday",
     "words": ["holiday", "holidays", "day off", "off day", "closed", "chhuti", "leave"]},
]
TYPE_NAMES = {"exam": "exam", "test": "test", "school_event": "school event",
              "emergency": "emergency", "vacation": "vacation", "festival": "festival"}
TENSE_WORDS = {
    "past": {"last", "previous", "prev", "past", "earlier", "before", "ago", "ended", "finished",
             "yesterday", "recent", "recently", "was"},
    "present": {"now", "today", "current", "currently", "ongoing", "running", "tonight"},
    "future": {"next", "upcoming", "coming", "future", "tomorrow", "soon", "later", "will"},
}
SUBJECTS = {
    "computer": {"computer", "computers", "comp"},
    "english": {"english"},
    "mathematics": {"mathematics", "math", "maths", "mathematic"},
    "science": {"science"},
    "nepali": {"nepali"},
    "social": {"social"},
}
FORMAT_WORDS = {
    "pdf": ["pdf", "pdfs"],
    "photo": ["photo", "photos", "image", "images", "picture", "pictures"],
    "youtube": ["youtube", "video", "videos"],
}
FORMAT_LABELS = {"pdf": "PDF", "photo": "Image", "youtube": "YouTube"}
FORMAT_NAMES = {"pdf": "a PDF", "photo": "an image", "youtube": "a YouTube link"}
STOPWORDS = {
    "i", "me", "my", "need", "want", "give", "find", "show", "get", "a", "an", "the", "of", "for", "on",
    "in", "about", "please", "pls", "plz", "can", "you", "could", "tell", "do", "have", "any", "some",
    "there", "is", "are", "our", "and", "to", "with", "from", "how", "what", "which", "all", "related",
    "regarding", "when", "where", "be", "it", "this", "that", "was", "will",
}

MSG = {
    "db_unavailable": "I can't reach my information database right now. Please try again in a little while.",
    "error": "Sorry, something went wrong while answering. Please try again.",
    "date_unavailable": "I couldn't work out today's Bikram Sambat date, so I can't check the calendar right now.",
    "ask_subject": "Which subject or chapter do you need notes for? For example: \"computer note\" or \"English notes\".",
    "cal_next": "The next {label} is \"{title}\" ({type}).",
    "cal_prev": "The previous {label} was \"{title}\" ({type}).",
    "cal_now": "\"{title}\" is going on right now (until {end}).",
    "cal_now_none": "No {label} is going on right now.",
    "cal_none": "I couldn't find any {label} in the calendar for that. I don't want to guess, so please check with your school.",
    "notes_intro": "Here are the notes I found for {topic}:",
    "notes_intro_relaxed": "I couldn't find notes specifically about \"{other}\", but here are notes for {topic}:",
    "notes_none": "I couldn't find any notes matching \"{topic}\".",
    "notes_subjects": " Available subjects: {subjects}.",
    "notes_more": "...and {count} more. Add a chapter name to narrow it down.",
    "notes_format_missing": "I couldn't find notes with {formats}, but here are the notes I have.",
    "ask_person": "Whose profile do you want? For example: \"profile of Ram Sharma\".",
    "profile_none": "I couldn't find anyone named \"{query}\".",
    "profile_more": "...and {count} more people. Use the full name to narrow it down.",
}

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}


def normalize(text):
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text)
    return " ".join(text.split())


def has_phrase(norm, tokens, words):
    padded = f" {norm} "
    for w in words:
        if " " in w:
            if f" {w} " in padded:
                return True
        elif w in tokens:
            return True
    return False


def term_in(term, words):
    for w in words:
        if w == term:
            return True
        if len(term) >= 4 and len(w) >= 4 and (w.startswith(term) or term.startswith(w)):
            return True
    return False


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def first_int(*values):
    for v in values:
        n = to_int(v)
        if n is not None:
            return n
    return None


def parse_month(key):
    n = to_int(key)
    return n if n is not None else MONTH_NAME_TO_NUM.get(normalize(key))


def first_url(item):
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


def urls(node):
    return [u for u in (first_url(item) for _, item in children(node)) if u]


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def first_text(user, keys):
    for key in keys:
        value = user.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
            return str(value).strip()
    return ""


def user_image(user):
    for key in IMAGE_KEYS:
        url = first_url(user.get(key))
        if url:
            return url
    return ""


def user_subjects(user):
    names = []
    for key in SUBJECT_KEYS:
        node = user.get(key)
        if node in (None, "", [], {}):
            continue
        if isinstance(node, str):
            names += [p.strip() for p in node.split(",") if p.strip()]
        else:
            for child_key, value in children(node):
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
                elif isinstance(value, dict):
                    names.append(first_text(value, SUBJECT_NAME_KEYS) or child_key)
                elif value is True:
                    names.append(child_key)
        if names:
            break
    unique = []
    for n in names:
        if n not in unique:
            unique.append(n)
    return unique


def safe_eval(node):
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](safe_eval(node.left), safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](safe_eval(node.operand))
    raise ValueError("unsupported")


def solve_math(message):
    t = message.lower().replace("×", "*").replace("÷", "/")
    for word, sym in (("multiplied by", "*"), ("divided by", "/"), ("plus", "+"), ("minus", "-"), ("times", "*")):
        t = t.replace(word, sym)
    t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", t)
    parts = [p.strip() for p in re.findall(r"[\d\.\+\-\*/%\(\)\s]+", t)]
    if not parts:
        return None
    expr = max(parts, key=len)
    if len(expr) > 40 or not re.search(r"\d\s*[\+\-\*/%]\s*[\(\d]", expr):
        return None
    try:
        result = safe_eval(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return "I can't divide by zero."
    except Exception:
        return None
    if isinstance(result, float):
        result = int(result) if result.is_integer() else round(result, 6)
    return f"{expr} = {result}"


class DurbarEngine:
    def __init__(self, data):
        self.data = data
        self.model = TinyModel(DATA)
        self.llm = LLMClient()
        self.alias_to_subject = {a: c for c, aliases in SUBJECTS.items() for a in aliases}
        self.drop = set(NOTES_WORDS)
        for words in FORMAT_WORDS.values():
            self.drop |= set(words)
        for words in TENSE_WORDS.values():
            self.drop |= words
        self.profile_drop = set(PROFILE_FILLERS)
        for phrase in PROFILE_WORDS:
            self.profile_drop |= set(phrase.split())

    def answer(self, message):
        norm = normalize(message or "")
        if not norm:
            return EMPTY
        try:
            return self._respond(message, norm, norm.split())
        except DataUnavailable:
            return MSG["db_unavailable"]
        except Exception:
            log.exception("Unexpected error while answering")
            return MSG["error"]

    def _respond(self, message, norm, tokens):
        maths = solve_math(message)
        if maths:
            return maths
        taught = tense_lab.respond(message, norm)
        if taught:
            return taught
        clock = self._clock(norm)
        if clock:
            return clock
        if has_phrase(norm, tokens, PROFILE_WORDS):
            reply = self._profile_reply(tokens)
            if reply is not None:
                return reply
        if has_phrase(norm, tokens, NOTES_WORDS):
            return self._notes_reply(norm, tokens)
        kind = self._calendar_kind(norm, tokens)
        if kind:
            return self._calendar_reply(kind, self._tense(tokens))
        reply, score = self.model.ask(message)
        if reply and score >= MODEL_THRESHOLD:
            return reply
        return self.llm.ask(message) or FALLBACK

    def _tense(self, tokens):
        for t in tokens:
            for name, words in TENSE_WORDS.items():
                if t in words:
                    return name
        return "auto"

    def _clock(self, norm):
        if not re.search(r"\b(what time|what is the time|current time|time now|what date|what is the date|today s date|todays date|current date|what day is it|what day is today)\b", norm):
            return None
        now = datetime.now(config.NEPAL_TZ)
        text = f"Today is {now.strftime('%A, %d %B %Y')}. The time in Nepal is {now.strftime('%I:%M %p')}."
        bs = self.today_bs()
        if bs:
            text += f" In Bikram Sambat it is {bs[2]} {BS_MONTHS[bs[1] - 1]} {bs[0]} BS."
        return text

    @staticmethod
    def _name_matches(query, name):
        name_tokens = normalize(name).split()
        if not name_tokens:
            return False
        return all(any(nt == q or nt.startswith(q) for nt in name_tokens) for q in query)

    def _profile_reply(self, tokens):
        query = [t for t in tokens if t not in STOPWORDS and t not in self.profile_drop]
        if not query:
            return MSG["ask_person"]
        found = []
        for _, user in children(self.data.get_users()):
            if not isinstance(user, dict):
                continue
            name = first_text(user, NAME_KEYS)
            if name and self._name_matches(query, name):
                found.append((0 if normalize(name).split() == query else 1, name, user))
        if not found:
            if tokens[:2] == ["who", "is"]:
                return None
            return MSG["profile_none"].format(query=" ".join(query))
        found.sort(key=lambda item: (item[0], normalize(item[1])))
        blocks = []
        for _, name, user in found[:MAX_PROFILES]:
            lines = [f"Full name: {name}"]
            role = first_text(user, ROLE_KEYS)
            if role:
                lines.append(f"Role: {role.capitalize()}")
            class_name = first_text(user, CLASS_KEYS)
            if class_name:
                lines.append(f"Class: {class_name}")
            subjects = user_subjects(user)
            if subjects:
                lines.append("Assigned subjects: " + ", ".join(subjects))
            lines.append("Profile picture: " + (user_image(user) or "not set"))
            blocks.append("\n".join(lines))
        if len(found) > MAX_PROFILES:
            blocks.append(MSG["profile_more"].format(count=len(found) - MAX_PROFILES))
        return "\n\n".join(blocks)

    def today_bs(self):
        try:
            import nepali_datetime

            ad_today = datetime.now(config.NEPAL_TZ).date()
            bs = nepali_datetime.date.from_datetime_date(ad_today)
            return (bs.year, bs.month, bs.day)
        except Exception as exc:
            log.error("BS date conversion failed: %s", type(exc).__name__)
            return None

    @staticmethod
    def _calendar_kind(norm, tokens):
        for kind in CALENDAR_KINDS:
            if has_phrase(norm, tokens, kind["words"]):
                return kind
        return None

    @staticmethod
    def _parse_calendar(year, node, wanted_types):
        events = []
        for month_key, month_node in children(node):
            path_month = parse_month(month_key)
            for type_key, type_node in children(month_node):
                etype = type_key.strip().lower()
                if etype not in wanted_types:
                    continue
                for event_id, ev in children(type_node):
                    if not isinstance(ev, dict):
                        continue
                    sm = first_int(ev.get("startMonth"), path_month)
                    sd = first_int(ev.get("startDay"), ev.get("day"), ev.get("date"))
                    em = first_int(ev.get("endMonth"), sm)
                    ed = first_int(ev.get("endDay"), sd)
                    if None in (sm, sd, em, ed):
                        continue
                    if not (1 <= sm <= 12 and 1 <= em <= 12 and 1 <= sd <= 32 and 1 <= ed <= 32):
                        continue
                    end_year = year if (em, ed) >= (sm, sd) else year + 1
                    events.append({
                        "id": event_id,
                        "type": etype,
                        "title": str(ev.get("title") or ev.get("name") or "").strip(),
                        "description": str(ev.get("description") or "").strip(),
                        "start": (year, sm, sd),
                        "end": (end_year, em, ed),
                    })
        return events

    def _events(self, years, types):
        events = []
        for y in years:
            events += self._parse_calendar(y, self.data.get_calendar_year(y), types)
        return events

    @staticmethod
    def _select(events, tense, today):
        if tense == "past":
            pool = [e for e in events if e["end"] < today]
            return sorted(pool, key=lambda e: (e["end"], e["start"]), reverse=True)
        if tense == "present":
            pool = [e for e in events if e["start"] <= today <= e["end"]]
        elif tense == "future":
            pool = [e for e in events if e["start"] > today]
        else:
            pool = [e for e in events if e["end"] >= today]
        return sorted(pool, key=lambda e: (e["start"], e["end"]))

    def _collect(self, types, tense, today):
        year, month, _ = today
        if tense == "past":
            years = [year, year - 1]
        else:
            years = [year] + ([year - 1] if month == 1 else [])
        events = self._events(years, types)
        found = self._select(events, tense, today)
        if tense != "past" and not found:
            events += self._events([year + 1], types)
            found = self._select(events, tense, today)
        return found

    @staticmethod
    def _fmt_date(d):
        return f"{d[2]} {BS_MONTHS[d[1] - 1]} {d[0]} BS"

    def _calendar_reply(self, kind, tense):
        today = self.today_bs()
        if today is None:
            return MSG["date_unavailable"]
        types = kind["types"]
        label = kind["label"]
        prefix = ""
        found = self._collect(types, tense, today)
        if tense == "present" and not found:
            prefix = MSG["cal_now_none"].format(label=label) + "\n"
            found = self._collect(types, "future", today)
        if not found:
            return prefix + MSG["cal_none"].format(label=label)
        ev = found[0]
        type_name = TYPE_NAMES.get(ev["type"], ev["type"].replace("_", " "))
        title = ev["title"] or f"Untitled {type_name}"
        if ev["start"] == ev["end"]:
            date_text = self._fmt_date(ev["start"])
        else:
            date_text = f"{self._fmt_date(ev['start'])} to {self._fmt_date(ev['end'])}"
        if ev["start"] <= today <= ev["end"]:
            head = MSG["cal_now"].format(title=title, end=self._fmt_date(ev["end"]))
        elif ev["end"] < today:
            head = MSG["cal_prev"].format(label=label, title=title, type=type_name)
        else:
            head = MSG["cal_next"].format(label=label, title=title, type=type_name)
        lines = [head, f"Date: {date_text}"]
        if ev["description"]:
            lines.append(f"Details: {ev['description']}")
        return prefix + "\n".join(lines)

    def _query_terms(self, tokens):
        terms = []
        for t in tokens:
            if t in STOPWORDS or t in self.drop:
                continue
            term = self.alias_to_subject.get(t, t)
            if term not in terms:
                terms.append(term)
        return terms

    @staticmethod
    def _hits(term, words):
        variants = SUBJECTS.get(term, {term}) | {term}
        return any(term_in(v, words) for v in variants)

    def _notes_reply(self, norm, tokens):
        wanted_formats = {f for f, words in FORMAT_WORDS.items() if has_phrase(norm, tokens, words)}
        terms = self._query_terms(tokens)
        units = self.data.get_units()
        subject_keys, entries = [], []
        for subject_key, subject_node in children(units):
            subject_keys.append(subject_key)
            key_words = normalize(subject_key.replace("_", " ").replace("-", " ")).split()
            for unit_id, unit in children(subject_node):
                if not isinstance(unit, dict):
                    continue
                unit_name = str(unit.get("name") or unit_id)
                for _, note in children(unit.get("notes")):
                    if not isinstance(note, dict):
                        continue
                    entries.append({
                        "subject": subject_key,
                        "key_words": key_words,
                        "unit": unit_name,
                        "title": str(note.get("title") or "Untitled note"),
                        "description": str(note.get("description") or ""),
                        "created": num(note.get("createdAt")),
                        "pdfs": urls(note.get("pdfs")),
                        "photos": urls(note.get("photos")),
                        "youtube": urls(note.get("youtubeLinks")),
                    })
        hint = MSG["notes_subjects"].format(subjects=", ".join(subject_keys[:15])) if subject_keys else ""
        if not terms:
            return MSG["ask_subject"] + hint
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
            pool = [e for e in entries if score(e) > 0]
            topic = " ".join(terms)
        if not pool:
            return MSG["notes_none"].format(topic=topic) + hint
        format_note = ""
        if wanted_formats:
            attr = {"pdf": "pdfs", "photo": "photos", "youtube": "youtube"}
            filtered = [e for e in pool if all(e[attr[f]] for f in wanted_formats)]
            if filtered:
                pool = filtered
            else:
                joined = " and ".join(FORMAT_NAMES[f] for f in sorted(wanted_formats))
                format_note = MSG["notes_format_missing"].format(formats=joined) + " "
        pool.sort(key=lambda e: (-score(e), -e["created"]))
        shown = pool[:MAX_NOTES]
        if relaxed_for:
            intro = MSG["notes_intro_relaxed"].format(other=relaxed_for, topic=topic)
        else:
            intro = MSG["notes_intro"].format(topic=topic)
        lines = [format_note + intro, ""]
        for i, e in enumerate(shown, 1):
            lines.append(f"{i}. {e['title']} (Subject: {e['subject']}, Unit: {e['unit']})")
            if e["description"]:
                desc = e["description"]
                lines.append("   " + (desc if len(desc) <= 200 else desc[:197] + "..."))
            for key, fmt in (("pdfs", "pdf"), ("photos", "photo"), ("youtube", "youtube")):
                for url in e[key][:3]:
                    lines.append(f"   {FORMAT_LABELS[fmt]}: {url}")
            lines.append("")
        if len(pool) > len(shown):
            lines.append(MSG["notes_more"].format(count=len(pool) - len(shown)))
        return "\n".join(lines).strip()