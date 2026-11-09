import { BS_MONTHS } from "../lib/helpers.js";
import {
  searchEvents, searchNationalDays, searchNotes, searchMocks,
  getAppUpdate, searchPeople, searchPosts,
} from "../db/firebase.js";
import {
  MAX_CARD_PEOPLE,
  peopleCard, notesCard, eventsCard, nationalDaysCard, mockCard, postsCard, appUpdateCard,
} from "../lib/cards.js";

/*
  Every handler returns:
    data  - full result, used by the model when the app cannot show a card
    brief - small result, used by the model when the app shows the card
    card  - ready-made JSON pack sent to the app (or null)
*/

const BS_NOTE = "All dates are Bikram Sambat (BS)";

async function getCalendarEvents(args) {
  const events = await searchEvents(args);
  return {
    data: { note: BS_NOTE, count: events.length, events: events.slice(0, 40) },
    brief: { note: BS_NOTE, count: events.length },
    card: eventsCard(events),
  };
}

async function getNationalDays(args) {
  const list = await searchNationalDays(args);
  const shown = list.slice(0, 40).map((n) => ({
    title: n.title,
    description: n.description,
    month_name: BS_MONTHS[Number(n.month) - 1],
    day: n.day,
  }));
  return {
    data: { note: BS_NOTE, count: list.length, national_days: shown },
    brief: { note: BS_NOTE, count: list.length },
    card: nationalDaysCard(list),
  };
}

async function getStudyMaterial(args) {
  const res = await searchNotes(args);
  if (res.error || !res.units) return { data: res, card: null };

  const noteCount = res.units.reduce((sum, u) => sum + u.notes.length, 0);
  const data = {
    subject: res.subject_key,
    unit_names: res.unit_names,
    note_count: noteCount,
    units: res.units.map((u) => ({
      unit: u.unit_name,
      notes: u.notes.map((n) => ({
        title: n.title,
        description: n.description.slice(0, 300),
        pdfs: n.pdfs.map((p) => ({ name: p.name, url: p.url })),
        youtube: n.youtube.map((y) => y.url),
        photo_count: n.photos.length,
      })),
    })),
  };
  const brief = {
    subject: res.subject_key,
    note_count: noteCount,
    units: res.units.map((u) => ({ unit: u.unit_name, titles: u.notes.map((n) => n.title) })),
  };
  return { data, brief, card: notesCard(res.subject_key, res.units) };
}

async function getMockQuestions(args) {
  const res = await searchMocks(args);
  if (res.error || !res.questions) return { data: res, card: null };
  return {
    data: { subject: res.subject_key, total_available: res.total_available, questions: res.questions },
    brief: { subject: res.subject_key, count: res.questions.length },
    card: mockCard(res.subject_key, res.questions),
  };
}

async function getAppUpdateTool() {
  const update = await getAppUpdate();
  if (!update) return { data: { error: "No update info available" }, card: null };
  return { data: update, brief: { version_name: update.version_name }, card: appUpdateCard(update) };
}

const publicPerson = (u) => ({
  name: u.fullName || null,
  role: u.role || null,
  subject: u.assignedSubject || null,
  class: u.classLevel || null,
  section: u.section || null,
});

async function getPeople(args) {
  const list = await searchPeople(args);
  return {
    data: { count: list.length, people: list.slice(0, 40).map(publicPerson) },
    brief: {
      count: list.length,
      people: list.slice(0, MAX_CARD_PEOPLE).map((u) => `${u.fullName} - ${u.role}`),
    },
    card: list.length <= MAX_CARD_PEOPLE ? peopleCard(list) : null,
  };
}

async function getPosts(args) {
  const posts = await searchPosts(args);
  return {
    data: {
      count: posts.length,
      posts: posts.map((p) => ({
        author: p.author,
        text: p.text,
        posted_on: p.posted_on,
        likes: p.likes,
        comments: p.comments,
        has_images: p.image_urls.length > 0,
      })),
    },
    brief: { count: posts.length },
    card: postsCard(posts),
  };
}

export const handlers = {
  get_calendar_events: getCalendarEvents,
  get_national_days: getNationalDays,
  get_study_material: getStudyMaterial,
  get_mock_questions: getMockQuestions,
  get_app_update: getAppUpdateTool,
  get_people: getPeople,
  get_posts: getPosts,
};