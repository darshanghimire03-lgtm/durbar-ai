import re

TENSES = {
    "simple present": ("subject + base verb (add -s/-es for he, she, it)", "habits, routines and general facts", "She plays football every day."),
    "present continuous": ("subject + am/is/are + verb-ing", "actions happening right now", "She is playing football now."),
    "present perfect": ("subject + have/has + past participle", "finished actions that matter now, and life experiences", "She has finished her homework."),
    "present perfect continuous": ("subject + have/has been + verb-ing", "actions that started in the past and are still going on", "She has been playing for two hours."),
    "simple past": ("subject + past form (verb-ed or irregular)", "actions that finished in the past", "She played football yesterday."),
    "past continuous": ("subject + was/were + verb-ing", "an action in progress at a moment in the past", "She was playing when it started to rain."),
    "past perfect": ("subject + had + past participle", "an action finished before another past action", "She had played before I arrived."),
    "past perfect continuous": ("subject + had been + verb-ing", "an action that continued up to a point in the past", "She had been playing for an hour before it rained."),
    "simple future": ("subject + will + base verb", "decisions, promises and predictions", "She will play tomorrow."),
    "future continuous": ("subject + will be + verb-ing", "an action in progress at a future moment", "She will be playing at 5 pm."),
    "future perfect": ("subject + will have + past participle", "an action that will be finished by a future time", "She will have played by 6 pm."),
    "future perfect continuous": ("subject + will have been + verb-ing", "how long an action will have continued by a future time", "She will have been playing for two hours by 6 pm."),
}

IRREGULAR = {
    "go": ("went", "gone"), "eat": ("ate", "eaten"), "see": ("saw", "seen"), "do": ("did", "done"),
    "have": ("had", "had"), "take": ("took", "taken"), "give": ("gave", "given"), "write": ("wrote", "written"),
    "read": ("read", "read"), "run": ("ran", "run"), "come": ("came", "come"), "make": ("made", "made"),
    "get": ("got", "got"), "know": ("knew", "known"), "speak": ("spoke", "spoken"), "buy": ("bought", "bought"),
    "bring": ("brought", "brought"), "drink": ("drank", "drunk"), "sing": ("sang", "sung"), "swim": ("swam", "swum"),
    "begin": ("began", "begun"), "break": ("broke", "broken"), "choose": ("chose", "chosen"), "drive": ("drove", "driven"),
    "fall": ("fell", "fallen"), "find": ("found", "found"), "fly": ("flew", "flown"), "forget": ("forgot", "forgotten"),
    "say": ("said", "said"), "sit": ("sat", "sat"), "sleep": ("slept", "slept"), "stand": ("stood", "stood"),
    "tell": ("told", "told"), "think": ("thought", "thought"), "win": ("won", "won"), "wear": ("wore", "worn"),
    "teach": ("taught", "taught"), "catch": ("caught", "caught"), "leave": ("left", "left"), "meet": ("met", "met"),
    "pay": ("paid", "paid"), "put": ("put", "put"), "send": ("sent", "sent"), "build": ("built", "built"),
    "lose": ("lost", "lost"), "sell": ("sold", "sold"), "keep": ("kept", "kept"), "feel": ("felt", "felt"),
    "hear": ("heard", "heard"), "hold": ("held", "held"), "draw": ("drew", "drawn"), "grow": ("grew", "grown"),
    "throw": ("threw", "thrown"), "steal": ("stole", "stolen"), "wake": ("woke", "woken"), "cut": ("cut", "cut"),
    "hit": ("hit", "hit"), "let": ("let", "let"),
}

PAST_WORDS = {p for p, _ in IRREGULAR.values() if p not in IRREGULAR} | {"was", "were"}
PP_WORDS = {pp for _, pp in IRREGULAR.values()} | {"been"}
NOT_ED = {"need", "feed", "speed", "seed", "bleed", "breed", "indeed", "proceed", "succeed", "exceed", "red", "bed", "shed", "weed", "hundred", "sacred", "naked", "wicked"}
NOT_ING = {"thing", "king", "ring", "sing", "bring", "spring", "string", "morning", "evening", "during", "nothing", "something", "anything", "everything", "wing", "swing", "sting"}

ALT = {}
for _name in TENSES:
    _parts = _name.split()
    if _parts[0] == "simple":
        ALT[" ".join(_parts[1:]) + " simple"] = _name
    if _name.endswith("continuous"):
        ALT[_name[: -len("continuous")] + "progressive"] = _name
    ALT[_name] = _name


def _vowel_groups(v):
    return len(re.findall(r"[aeiouy]+", v))


def _double(v):
    if not re.search(r"[^aeiou][aeiou][^aeiouwxy]$", v):
        return False
    return _vowel_groups(v) == 1 or v in {"begin", "forget", "admit", "prefer", "occur", "refer"}


def _third(v):
    if v == "have":
        return "has"
    if re.search(r"(s|sh|ch|x|z|o)$", v):
        return v + "es"
    if re.search(r"[^aeiou]y$", v):
        return v[:-1] + "ies"
    return v + "s"


def _ing(v):
    if v.endswith("ie"):
        return v[:-2] + "ying"
    if v.endswith("e") and not v.endswith(("ee", "ye", "oe")):
        return v[:-1] + "ing"
    if _double(v):
        return v + v[-1] + "ing"
    return v + "ing"


def _ed(v):
    if v.endswith("e"):
        return v + "d"
    if re.search(r"[^aeiou]y$", v):
        return v[:-1] + "ied"
    if _double(v):
        return v + v[-1] + "ed"
    return v + "ed"


def forms(v):
    past, pp = IRREGULAR.get(v, (None, None))
    return {
        "base": v,
        "third": _third(v),
        "ing": _ing(v),
        "past": past or _ed(v),
        "pp": pp or _ed(v),
    }


def conjugate(verb):
    v = verb.lower().strip()
    if not v.isalpha():
        return "Please give me one English verb, for example: conjugate go."
    if v in ("be", "am", "is", "are", "was", "were", "been"):
        return "The verb be is special: am/is/are (present), was/were (past), been (perfect), being (-ing)."
    f = forms(v)
    rows = [
        ("simple present", f"she {f['third']}"),
        ("present continuous", f"she is {f['ing']}"),
        ("present perfect", f"she has {f['pp']}"),
        ("present perfect continuous", f"she has been {f['ing']}"),
        ("simple past", f"she {f['past']}"),
        ("past continuous", f"she was {f['ing']}"),
        ("past perfect", f"she had {f['pp']}"),
        ("past perfect continuous", f"she had been {f['ing']}"),
        ("simple future", f"she will {f['base']}"),
        ("future continuous", f"she will be {f['ing']}"),
        ("future perfect", f"she will have {f['pp']}"),
        ("future perfect continuous", f"she will have been {f['ing']}"),
    ]
    head = f"The verb \"{v}\": {f['base']} / {f['past']} / {f['pp']} / {f['ing']}"
    return head + "\n" + "\n".join(f"{n.capitalize()}: {s}" for n, s in rows)


def _expand(text):
    t = text.lower().replace("’", "'")
    t = t.replace("won't", "will not").replace("can't", "can not").replace("shan't", "shall not")
    t = re.sub(r"\b(\w+)'s been\b", r"\1 has been", t)
    t = re.sub(r"'s (\w+ing)\b", r" is \1", t)
    t = re.sub(r"'d been\b", " had been", t)
    t = t.replace("'ll", " will").replace("'ve", " have").replace("'m", " am").replace("'re", " are")
    t = t.replace("n't", "")
    return re.findall(r"[a-z]+", t)


def _is_ing(w):
    return w.endswith("ing") and len(w) > 4 and w not in NOT_ING


def _is_pp(w):
    return w in PP_WORDS or (w.endswith("ed") and len(w) > 3 and w not in NOT_ED)


def _is_past(w):
    return w in PAST_WORDS or (w.endswith("ed") and len(w) > 3 and w not in NOT_ED)


def detect(sentence):
    t = _expand(sentence)
    if not t:
        return None
    for i, w in enumerate(t):
        rest = t[i + 1:]
        if w in ("will", "shall"):
            if rest[:2] == ["have", "been"] and any(_is_ing(x) for x in rest[2:]):
                return "future perfect continuous"
            if rest[:1] == ["have"] and any(_is_pp(x) for x in rest[1:]):
                return "future perfect"
            if rest[:1] == ["be"] and any(_is_ing(x) for x in rest[1:]):
                return "future continuous"
            return "simple future"
    for i, w in enumerate(t):
        rest = t[i + 1:]
        if w == "had":
            if rest[:1] == ["been"] and any(_is_ing(x) for x in rest[1:]):
                return "past perfect continuous"
            if any(_is_pp(x) for x in rest[:3]):
                return "past perfect"
            return "simple past"
        if w in ("have", "has"):
            if rest[:1] == ["been"] and any(_is_ing(x) for x in rest[1:]):
                return "present perfect continuous"
            if any(_is_pp(x) for x in rest[:3]):
                return "present perfect"
            return "simple present"
    for i, w in enumerate(t):
        rest = t[i + 1:]
        if w in ("was", "were"):
            return "past continuous" if any(_is_ing(x) for x in rest) else "simple past"
        if w in ("am", "is", "are"):
            return "present continuous" if any(_is_ing(x) for x in rest) else "simple present"
    if "did" in t or any(_is_past(w) for w in t[1:]):
        return "simple past"
    return "simple present"


def lesson(name):
    formula, use, example = TENSES[name]
    return f"{name.capitalize()} tense\nFormula: {formula}\nUse: {use}\nExample: {example}"


def _group(word):
    names = [n for n in TENSES if n.split()[0] == word or n.split()[1] == word]
    lines = [f"{n.capitalize()}: {TENSES[n][0]}" for n in names]
    return f"The {word} tense has 4 forms:\n" + "\n".join(lines) + "\nAsk \"explain " + names[0] + "\" for details."


def _find_tense(norm):
    for key in sorted(ALT, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", norm):
            return ALT[key]
    return None


def _sentence(message):
    q = re.search(r"[\"“](.+?)[\"”]", message)
    if q:
        return q.group(1)
    m = re.search(r"\btenses?\b(?:\s+(?:is|of|in|are))?(?:\s+(?:the|this)\b)?(?:\s+sentence\b)?\s*[:\-]?\s*(.+)$", message, re.I)
    if m and not re.match(r"(used|for|do|does)\b", m.group(1), re.I):
        return m.group(1).strip(" ?.!")
    return None


def respond(message, norm):
    m = re.search(r"\b(?:conjugate|conjugation of|forms of|all tenses of|tenses of)\s+(?:the\s+)?(?:verb\s+)?([a-z]+)", norm)
    if m and m.group(1) not in ("the", "verb", "a", "an"):
        return conjugate(m.group(1))
    asks_detect = re.search(r"\b(what|which|identify|find|check|detect|tell)\b.*\btense\b", norm) or re.search(r"[\"“].+[\"”]", message) and "tense" in norm
    if asks_detect:
        s = _sentence(message)
        if s and len(s.split()) >= 2:
            name = detect(s)
            formula, use, _ = TENSES[name]
            return f"\"{s}\" is in the {name} tense.\nFormula: {formula}\nUse: {use}"
    name = _find_tense(norm)
    if name:
        return lesson(name)
    for word in ("present", "past", "future"):
        if re.search(rf"\b{word} tense\b", norm):
            return _group(word)
    if re.search(r"\btenses?\b", norm):
        return (
            "A tense shows when an action happens. English has 3 times (present, past, future) and 4 aspects each, so 12 tenses.\n"
            "Try: \"explain present perfect\", \"what tense is 'She has eaten'\" or \"conjugate go\"."
        )
    return None