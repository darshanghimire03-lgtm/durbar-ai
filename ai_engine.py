import json
import logging
import unicodedata
from datetime import datetime

import config
from firebase_data import DataUnavailable, children

log = logging.getLogger("durbar.engine")

MONTHS = {
    "en": ["Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
           "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"],
    "ne": ["बैशाख", "जेठ", "असार", "श्रावण", "भदौ", "आश्विन",
           "कार्तिक", "मंसिर", "पुष", "माघ", "फागुन", "चैत"],
}
MONTHS["rn"] = MONTHS["en"]
DEVA_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")
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


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text)
    return " ".join(text.split())


def _is_deva(s: str) -> bool:
    return any("\u0900" <= c <= "\u097f" for c in s)


def _has_phrase(norm: str, tokens, words) -> bool:
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


def _seq_index(tokens, phrase):
    n = len(phrase)
    if n == 0:
        return None
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == phrase:
            return i
    return None


def _term_in(term: str, words) -> bool:
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


def _first_url(item):
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


def _pick(options, lang):
    return options.get(lang) or options.get("en", "")


def _first_text(user, keys):
    for key in keys:
        value = user.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
            return str(value).strip()
    return ""


def _user_image(user):
    for key in IMAGE_KEYS:
        url = _first_url(user.get(key))
        if url:
            return url
    return ""


def _user_subjects(user):
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
                    label = _first_text(value, SUBJECT_NAME_KEYS)
                    names.append(label or child_key)
                elif value is True:
                    names.append(child_key)
        if names:
            break
    unique = []
    for n in names:
        if n not in unique:
            unique.append(n)
    return unique


class DurbarEngine:
    def __init__(self, data, knowledge_path=None):
        self.data = data
        path = knowledge_path or config.KNOWLEDGE_FILE
        with open(path, encoding="utf-8") as f:
            self.kb = json.load(f)

        self.msg = self.kb.get("messages", {})
        self.smalltalk = []
        for entry in self.kb.get("smalltalk", []):
            for phrase in entry["phrases"]:
                self.smalltalk.append((normalize(phrase).split(), entry))
        self.smalltalk.sort(key=lambda pair: len(pair[0]), reverse=True)

        lang_kb = self.kb.get("language", {})
        self.rn_words = {normalize(w) for w in lang_kb.get("romanized_words", [])}
        self.en_words = {normalize(w) for w in lang_kb.get("english_words", [])}

        self.tenses = {
            name: [normalize(w) for w in words] for name, words in self.kb.get("tenses", {}).items()
        }

        intents = self.kb.get("intents", {})
        self.notes_words = [normalize(w) for w in intents.get("notes_words", [])]
        self.profile_words = [normalize(w) for w in intents.get("profile_words", [])]
        self.profile_drop = {normalize(f) for f in intents.get("profile_fillers", [])}
        for phrase in self.profile_words:
            self.profile_drop |= set(phrase.split())
        self.calendar_kinds = [
            {**k, "words": [normalize(w) for w in k["words"]]} for k in intents.get("calendar", [])
        ]
        self.type_names = self.kb.get("type_names", {})

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
        self.format_labels = self.kb.get("format_labels", {})
        self.format_names = self.kb.get("format_names", {})
        self.stopwords = {normalize(w) for w in self.kb.get("stopwords", [])}

        self.drop = set(self.notes_words)
        for words in self.format_words.values():
            self.drop |= set(words)
        for words in self.tenses.values():
            self.drop |= set(words)

    def _t(self, key, lang, **kw):
        text = _pick(self.msg.get(key, {}), lang)
        return text.format(**kw) if kw else text

    def answer(self, message: str) -> str:
        norm = normalize(message or "")
        if not norm:
            return self._t("empty", "en")
        tokens = norm.split()
        lang = self._language(tokens, norm)
        try:
            return self._respond(norm, tokens, lang)
        except DataUnavailable:
            return self._t("db_unavailable", lang)
        except Exception:
            log.exception("Unexpected error while answering")
            return self._t("error", lang)

    def _respond(self, norm, tokens, lang):
        if _has_phrase(norm, tokens, self.profile_words):
            return self._profile_reply(tokens, lang)
        if _has_phrase(norm, tokens, self.notes_words):
            return self._notes_reply(norm, tokens, lang)
        kind = self._calendar_kind(norm, tokens)
        if kind:
            return self._calendar_reply(kind, self._tense(tokens), lang)
        reply = self._smalltalk(tokens, lang)
        return reply if reply else self._t("fallback", lang)

    def _language(self, tokens, norm):
        if _is_deva(norm):
            return "ne"
        rn = sum(1 for t in tokens if t in self.rn_words)
        en = sum(1 for t in tokens if t in self.en_words)
        if rn and rn >= en:
            return "rn"
        return "en"

    def _tense(self, tokens):
        for t in tokens:
            for name, words in self.tenses.items():
                for w in words:
                    if t == w or (_is_deva(w) and t.startswith(w)):
                        return name
        return "auto"

    def _smalltalk(self, tokens, lang):
        for phrase, entry in self.smalltalk:
            n = len(phrase)
            if n == 0 or len(tokens) - n > 2:
                continue
            if _seq_index(tokens, phrase) is not None:
                return _pick(entry["reply"], lang)
        return None

    @staticmethod
    def _name_matches(query, name):
        name_tokens = normalize(name).split()
        if not name_tokens:
            return False
        for q in query:
            hit = False
            for nt in name_tokens:
                if nt == q or nt.startswith(q) or (_is_deva(q) and q.startswith(nt) and len(nt) >= 2):
                    hit = True
                    break
            if not hit:
                return False
        return True

    def _profile_reply(self, tokens, lang):
        query = [t for t in tokens if t not in self.stopwords and t not in self.profile_drop]
        if not query:
            return self._t("ask_person", lang)

        found = []
        for uid, user in children(self.data.get_users()):
            if not isinstance(user, dict):
                continue
            name = _first_text(user, NAME_KEYS)
            if name and self._name_matches(query, name):
                exact = normalize(name).split() == query
                found.append((0 if exact else 1, name, user))
        if not found:
            return self._t("profile_none", lang, query=" ".join(query))

        found.sort(key=lambda item: (item[0], normalize(item[1])))
        blocks = []
        for _, name, user in found[:MAX_PROFILES]:
            lines = [self._t("profile_name", lang, value=name)]
            role = _first_text(user, ROLE_KEYS)
            if role:
                lines.append(self._t("profile_role", lang, value=role.capitalize()))
            class_name = _first_text(user, CLASS_KEYS)
            if class_name:
                lines.append(self._t("profile_class", lang, value=class_name))
            subjects = _user_subjects(user)
            if subjects:
                lines.append(self._t("profile_subjects", lang, value=", ".join(subjects)))
            image = _user_image(user) or self._t("profile_no_picture", lang)
            lines.append(self._t("profile_picture", lang, value=image))
            blocks.append("\n".join(lines))
        if len(found) > MAX_PROFILES:
            blocks.append(self._t("profile_more", lang, count=len(found) - MAX_PROFILES))
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

    def _calendar_kind(self, norm, tokens):
        for kind in self.calendar_kinds:
            if _has_phrase(norm, tokens, kind["words"]):
                return kind
        return None

    @staticmethod
    def _parse_calendar(year, node, wanted_types):
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

    def _fmt_date(self, d, lang):
        year, month, day = d
        year, day = str(year), str(day)
        if lang == "ne":
            year, day = year.translate(DEVA_DIGITS), day.translate(DEVA_DIGITS)
        return self._t("date_fmt", lang, day=day, month=MONTHS[lang][month - 1], year=year)

    def _type_name(self, etype, lang):
        names = self.type_names.get(etype)
        if names:
            return _pick(names, lang)
        return etype.replace("_", " ")

    def _calendar_reply(self, kind, tense, lang):
        today = self.today_bs()
        if today is None:
            return self._t("date_unavailable", lang)
        types = set(kind["types"])
        label = _pick(kind["labels"], lang)
        prefix = ""

        found = self._collect(types, tense, today)
        if tense == "present" and not found:
            prefix = self._t("cal_now_none", lang, label=label) + "\n"
            found = self._collect(types, "future", today)

        if not found:
            return prefix + self._t("cal_none", lang, label=label)

        ev = found[0]
        type_name = self._type_name(ev["type"], lang)
        title = ev["title"] or self._t("untitled", lang, type=type_name)
        if ev["start"] == ev["end"]:
            date_text = self._fmt_date(ev["start"], lang)
        else:
            date_text = self._t("date_range", lang,
                                start=self._fmt_date(ev["start"], lang),
                                end=self._fmt_date(ev["end"], lang))

        if ev["start"] <= today <= ev["end"]:
            head = self._t("cal_now", lang, title=title, end=self._fmt_date(ev["end"], lang))
        elif ev["end"] < today:
            head = self._t("cal_prev", lang, label=label, title=title, type=type_name)
        else:
            head = self._t("cal_next", lang, label=label, title=title, type=type_name)

        lines = [head, self._t("cal_date", lang, date=date_text)]
        if ev["description"]:
            lines.append(self._t("cal_details", lang, text=ev["description"]))
        return prefix + "\n".join(lines)

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

    def _notes_reply(self, norm, tokens, lang):
        wanted_formats = {f for f, words in self.format_words.items() if _has_phrase(norm, tokens, words)}
        terms = self._query_terms(tokens, self.drop)

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

        subjects_hint = ""
        if subject_keys:
            subjects_hint = self._t("notes_subjects", lang, subjects=", ".join(subject_keys[:15]))

        if not terms:
            return self._t("ask_subject", lang) + subjects_hint

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
            return self._t("notes_none", lang, topic=topic) + subjects_hint

        format_note = ""
        if wanted_formats:
            attr = {"pdf": "pdfs", "photo": "photos", "youtube": "youtube"}
            filtered = [e for e in pool if all(e[attr[f]] for f in wanted_formats)]
            if filtered:
                pool = filtered
            else:
                names = self.format_names.get(lang) or self.format_names.get("en", {})
                joined = self._t("and_word", lang).join(names[f] for f in sorted(wanted_formats))
                format_note = self._t("notes_format_missing", lang, formats=joined) + " "

        pool.sort(key=lambda e: (-score(e), -e["created"]))
        shown = pool[:MAX_NOTES]

        if relaxed_for:
            intro = self._t("notes_intro_relaxed", lang, other=relaxed_for, topic=topic)
        else:
            intro = self._t("notes_intro", lang, topic=topic)

        labels = self.format_labels.get(lang) or self.format_labels.get("en", {})
        lines = [format_note + intro, ""]
        for i, e in enumerate(shown, 1):
            lines.append(self._t("notes_item", lang, i=i, title=e["title"], subject=e["subject"], unit=e["unit"]))
            if e["description"]:
                desc = e["description"]
                lines.append("   " + (desc if len(desc) <= 200 else desc[:197] + "..."))
            for key, fmt in (("pdfs", "pdf"), ("photos", "photo"), ("youtube", "youtube")):
                for url in e[key][:3]:
                    lines.append(f"   {labels.get(fmt, fmt)}: {url}")
            lines.append("")
        if len(pool) > len(shown):
            lines.append(self._t("notes_more", lang, count=len(pool) - len(shown)))
        return "\n".join(lines).strip()