import { searchMocks } from "../db/firebase.js";
import { mockCard } from "../lib/cards.js";

const TTL_MS = 60 * 60 * 1000;
const LETTERS = "ABCDEFGH";
const sessions = new Map();

const HIDDEN_NOTE =
  "Correct answers are kept on the server. Never state, hint or guess them. After the user answers, call check_mock_answers.";

export const definitions = [
  {
    type: "function",
    function: {
      name: "get_mock_questions",
      description:
        "Get random multiple choice mock test questions for a subject. Answers are hidden from users and from you. Call without a subject to list available subjects.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Subject name" },
          count: { type: "integer", description: "Number of questions, 1-10, default 5" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "check_mock_answers",
      description:
        "Check the user's answers for the latest mock test. Pass each question number with the selected option letter. Set reveal true only when the user asks to see the answers. Returns correctness and the right option for the answered questions.",
      parameters: {
        type: "object",
        properties: {
          answers: {
            type: "array",
            items: {
              type: "object",
              properties: {
                number: { type: "integer", description: "Question number shown to the user" },
                selected: { type: "string", description: "Option letter A, B, C or D" },
              },
            },
            description: "The user's answers",
          },
          reveal: { type: "boolean", description: "Show the right answers for all questions" },
        },
      },
    },
  },
];

function save(key, subject, questions) {
  sessions.set(key, { subject, questions, at: Date.now() });
  if (sessions.size > 500) sessions.delete(sessions.keys().next().value);
}

function load(key) {
  const s = sessions.get(key);
  if (!s) return null;
  if (Date.now() - s.at > TTL_MS) {
    sessions.delete(key);
    return null;
  }
  return s;
}

function toIndex(v) {
  const t = String(v ?? "").trim().toUpperCase();
  if (/^[A-H]$/.test(t)) return LETTERS.indexOf(t);
  if (/^[1-8]$/.test(t)) return Number(t) - 1;
  return -1;
}

async function getMockQuestions(args, ctx) {
  const res = await searchMocks(args);
  if (res.error || !res.questions) return { data: res, card: null };
  save(ctx.sessionKey, res.subject_key, res.questions);
  const questions = res.questions.map((q, i) => ({
    number: i + 1,
    question: q.question,
    options: q.options,
  }));
  return {
    data: { subject: res.subject_key, total_available: res.total_available, note: HIDDEN_NOTE, questions },
    brief: { subject: res.subject_key, count: questions.length, note: HIDDEN_NOTE },
    card: mockCard(res.subject_key, questions),
  };
}

async function checkMockAnswers(args, ctx) {
  const s = load(ctx.sessionKey);
  if (!s) {
    return { data: { error: "No active mock test. Ask the user to start a new one." }, card: null };
  }
  const given = Array.isArray(args.answers) ? args.answers : [];
  const answered = new Set();
  const results = [];

  for (const a of given) {
    const number = Number(a?.number);
    const q = s.questions[number - 1];
    if (!q) {
      results.push({ number, error: "No such question" });
      continue;
    }
    answered.add(number);
    const idx = toIndex(a.selected);
    results.push({
      number,
      selected: idx >= 0 ? LETTERS[idx] : null,
      correct: idx === q.answer_index,
      right_option: LETTERS[q.answer_index],
      right_text: q.options[q.answer_index],
    });
  }

  if (args.reveal === true) {
    s.questions.forEach((q, i) => {
      if (answered.has(i + 1)) return;
      results.push({
        number: i + 1,
        selected: null,
        right_option: LETTERS[q.answer_index],
        right_text: q.options[q.answer_index],
      });
    });
  }

  results.sort((a, b) => a.number - b.number);
  const score = results.filter((r) => r.correct === true).length;
  return {
    data: { subject: s.subject, total_questions: s.questions.length, answered: answered.size, score, results },
    card: null,
  };
}

export const handlers = { get_mock_questions: getMockQuestions, check_mock_answers: checkMockAnswers };