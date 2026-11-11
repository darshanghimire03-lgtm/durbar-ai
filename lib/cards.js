import { VERIFIED_ROLES, norm, cleanUrl, bsDateText } from "./helpers.js";
import { buildTable } from "./table.js";

export const CARD_TYPES = [
  "people", "notes", "events", "national_days", "mock", "posts", "app_update", "table",
];
export const DEFAULT_SUPPORTED = ["people", "notes"];

export const MAX_CARD_PEOPLE = 12;
export const MAX_CARD_NOTES = 10;
export const MAX_CARD_EVENTS = 15;

const isVerified = (role) => VERIFIED_ROLES.includes(norm(role));

export function peopleCard(list) {
  if (!list.length) return null;
  return {
    type: "people",
    people: list.map((u) => ({
      uid: String(u.uid || ""),
      name: String(u.fullName || ""),
      role: norm(u.role) || "student",
      subject: String(u.assignedSubject || ""),
      class_level: String(u.classLevel || ""),
      section: String(u.section || ""),
      photo_url: cleanUrl(u.profileImageUrl),
      verified: isVerified(u.role),
    })),
  };
}

export function notesCard(subjectKey, units) {
  const groups = [];
  let total = 0;
  for (const u of units) {
    const room = MAX_CARD_NOTES - total;
    if (room <= 0) break;
    const notes = u.notes.slice(0, room).map((n) => ({
      ...n,
      description: n.description.slice(0, 2000),
    }));
    total += notes.length;
    groups.push({
      subject_key: subjectKey,
      unit_id: u.unit_id,
      unit_name: u.unit_name,
      notes,
    });
  }
  if (!groups.length) return null;
  return { type: "notes", subject: subjectKey, groups };
}

export function timeText(ev) {
  const s = ev.startTime ?? ev.start_time ?? ev.start;
  const e = ev.endTime ?? ev.end_time ?? ev.end;
  if (s && e) return `${s} - ${e}`;
  return String(s ?? ev.time ?? "");
}

export function eventDateText(ev) {
  if (ev.startMonth != null && ev.endMonth != null) {
    const sameDay =
      Number(ev.startMonth) === Number(ev.endMonth) && Number(ev.startDay) === Number(ev.endDay);
    const end = bsDateText(ev.endMonth, ev.endDay, ev.bs_year);
    if (sameDay) return end;
    return `${bsDateText(ev.startMonth, ev.startDay)} - ${end}`;
  }
  return bsDateText(ev.month, ev.day ?? ev.startDay, ev.bs_year);
}

export function subjectsText(ev) {
  return Array.isArray(ev.subjects) ? ev.subjects.join(", ") : "";
}

export function eventsCard(events) {
  if (!events.length) return null;
  return {
    type: "events",
    calendar: "Bikram Sambat (BS)",
    events: events.slice(0, MAX_CARD_EVENTS).map((ev) => ({
      event_type: ev.event_type,
      title: String(ev.title || ev.subject || ""),
      subject: String(ev.subject || subjectsText(ev) || ""),
      description: String(ev.description || "").slice(0, 400),
      date_text: eventDateText(ev),
      time_text: timeText(ev),
      bs_year: ev.bs_year,
      month: ev.month,
      day: Number(ev.day ?? ev.startDay) || 0,
    })),
  };
}

export function nationalDaysCard(list) {
  if (!list.length) return null;
  return {
    type: "national_days",
    calendar: "Bikram Sambat (BS)",
    national_days: list.slice(0, MAX_CARD_EVENTS).map((n) => ({
      title: String(n.title || ""),
      description: String(n.description || "").slice(0, 400),
      month: Number(n.month) || 0,
      day: Number(n.day) || 0,
      date_text: bsDateText(n.month, n.day),
    })),
  };
}

export function mockCard(subjectKey, questions) {
  if (!questions.length) return null;
  return {
    type: "mock",
    subject: subjectKey,
    questions: questions.map((q, i) => ({
      number: i + 1,
      question: String(q.question),
      options: q.options.map(String),
    })),
  };
}

export function eventsTable(events) {
  return buildTable({
    title: "Events",
    columns: ["No", "Type", "Title", "Subject", "Date", "Time"],
    rows: events.map((ev, i) => [
      i + 1,
      ev.event_type,
      ev.title || "",
      ev.subject || subjectsText(ev),
      eventDateText(ev),
      timeText(ev),
    ]),
  });
}

export function nationalDaysTable(list) {
  return buildTable({
    title: "National days",
    columns: ["No", "Title", "Date", "Description"],
    rows: list.map((n, i) => [i + 1, n.title, bsDateText(n.month, n.day), n.description]),
  });
}

export function postsCard(posts) {
  if (!posts.length) return null;
  return {
    type: "posts",
    posts: posts.map(({ created, ...p }) => ({
      ...p,
      verified: isVerified(p.author_role),
    })),
  };
}

export function appUpdateCard(update) {
  if (!update) return null;
  return { type: "app_update", ...update };
}

export function introFor(card) {
  switch (card.type) {
    case "people":
      return card.people.length === 1 ? "Here is what I found:" : "Here are the people I found:";
    case "notes": return `Here are the notes for ${card.subject}:`;
    case "events": return "Here are the events I found:";
    case "national_days": return "Here are the national days:";
    case "mock": return `Here are the mock questions for ${card.subject}:`;
    case "posts": return "Here are the latest posts:";
    case "app_update": return "Here is the latest app update:";
    case "table": return card.title ? `Here is the table: ${card.title}` : "Here is the table:";
    default: return "Here you go:";
  }
}