import { BS_MONTHS, EVENT_TYPES } from "../lib/helpers.js";
import { searchEvents, searchNationalDays, getAppUpdate, searchPosts } from "../db/firebase.js";
import {
  eventsCard, nationalDaysCard, postsCard, appUpdateCard, eventsTable, nationalDaysTable,
} from "../lib/cards.js";
import { AS_TABLE, buildTable } from "../lib/table.js";

const BS_NOTE = "All dates are Bikram Sambat (BS)";

export const definitions = [
  {
    type: "function",
    function: {
      name: "get_calendar_events",
      description:
        "Read the Durbar school calendar (Bikram Sambat dates). Use for exam schedules, tests, festivals, school events, emergencies and vacations. For exam questions use type exam. Set as_table true when the user asks for a table.",
      parameters: {
        type: "object",
        properties: {
          type: { type: "string", enum: EVENT_TYPES, description: "Event type. Omit to search all types." },
          bs_year: { type: "integer", description: "BS year, e.g. 2083. Omit to search the latest years." },
          month: { type: "integer", description: "BS month number 1-12 (1 Baisakh, 7 Kartik, 12 Chaitra)" },
          day: { type: "integer", description: "BS day of month" },
          subject: { type: "string", description: "Subject name filter for exams and tests" },
          keyword: { type: "string", description: "Keyword to match in title or description" },
          as_table: AS_TABLE,
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_national_days",
      description: "Read national days and public observances (Bikram Sambat month and day).",
      parameters: {
        type: "object",
        properties: {
          month: { type: "integer", description: "BS month number 1-12" },
          day: { type: "integer", description: "BS day of month" },
          keyword: { type: "string", description: "Keyword to match in title or description" },
          as_table: AS_TABLE,
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_app_update",
      description: "Get the latest app version, what's new and the download link.",
      parameters: { type: "object", properties: {} },
    },
  },
  {
    type: "function",
    function: {
      name: "get_posts",
      description:
        "Read the latest public posts from the Durbar app feed with author, text, date, likes and comment counts. Use for questions about posts, feed or what someone posted.",
      parameters: {
        type: "object",
        properties: {
          keyword: { type: "string", description: "Keyword to match in post text" },
          author: { type: "string", description: "Part of the author's name" },
          limit: { type: "integer", description: "Number of posts, 1-10, default 5" },
          as_table: AS_TABLE,
        },
      },
    },
  },
];

async function getCalendarEvents(args) {
  const events = await searchEvents(args);
  const table = args.as_table === true && events.length ? eventsTable(events) : null;
  return {
    data: { note: BS_NOTE, count: events.length, events: events.slice(0, 40) },
    brief: { note: BS_NOTE, count: events.length },
    card: table ? null : eventsCard(events),
    table,
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
  const table = args.as_table === true && list.length ? nationalDaysTable(list) : null;
  return {
    data: { note: BS_NOTE, count: list.length, national_days: shown },
    brief: { note: BS_NOTE, count: list.length },
    card: table ? null : nationalDaysCard(list),
    table,
  };
}

async function getAppUpdateTool() {
  const update = await getAppUpdate();
  if (!update) return { data: { error: "No update info available" }, card: null };
  return { data: update, brief: { version_name: update.version_name }, card: appUpdateCard(update) };
}

async function getPosts(args) {
  const posts = await searchPosts(args);
  const table =
    args.as_table === true && posts.length
      ? buildTable({
          title: "Posts",
          columns: ["No", "Author", "Role", "Post", "Date", "Likes", "Comments"],
          rows: posts.map((p, i) => [i + 1, p.author, p.author_role, p.text, p.posted_on, p.likes, p.comments]),
        })
      : null;
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
    card: table ? null : postsCard(posts),
    table,
  };
}

export const handlers = {
  get_calendar_events: getCalendarEvents,
  get_national_days: getNationalDays,
  get_app_update: getAppUpdateTool,
  get_posts: getPosts,
};