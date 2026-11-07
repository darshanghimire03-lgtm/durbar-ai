import math
import random
import re
from collections import Counter, defaultdict


STOP = {"what", "is", "a", "an", "the", "of", "to", "do", "does", "i", "me", "my", "can", "tell",
        "about", "please", "in", "on", "for", "and", "it", "this", "that", "whats", "s", "am"}


def features(text):
    words = re.findall(r"[a-z0-9']+", text.lower().replace("'s", " s"))
    content = [w for w in words if w not in STOP] or words
    feats = Counter()
    for w in content:
        feats["w:" + w] += 1.0
        padded = f"<{w}>"
        for i in range(len(padded) - 2):
            feats["c:" + padded[i:i + 3]] += 0.3
    for a, b in zip(content, content[1:]):
        feats["b:" + a + "_" + b] += 1.0
    return feats


class TinyModel:
    def __init__(self, data):
        self.answers = []
        self.index = defaultdict(list)
        docs = []
        for questions, answers in data:
            for q in questions:
                docs.append((features(q), len(self.answers)))
            self.answers.append(answers)
        df = Counter()
        for feats, _ in docs:
            df.update(feats.keys())
        n = len(docs)
        self.idf = {f: math.log((1 + n) / (1 + c)) + 1.0 for f, c in df.items()}
        for feats, answer_id in docs:
            vec = self._weigh(feats)
            for f, w in vec.items():
                self.index[f].append((answer_id, w))

    def _weigh(self, feats):
        vec = {f: v * self.idf[f] for f, v in feats.items() if f in self.idf}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {f: w / norm for f, w in vec.items()}

    def ask(self, text):
        feats = features(text)
        total = math.sqrt(sum((v * self.idf.get(f, 1.0)) ** 2 for f, v in feats.items())) or 1.0
        scores = defaultdict(float)
        for f, v in feats.items():
            if f not in self.idf:
                continue
            q = v * self.idf[f] / total
            best = {}
            for answer_id, w in self.index[f]:
                if w > best.get(answer_id, 0.0):
                    best[answer_id] = w
            for answer_id, w in best.items():
                scores[answer_id] += q * w
        if not scores:
            return None, 0.0
        answer_id = max(scores, key=scores.get)
        return random.choice(self.answers[answer_id]), scores[answer_id]