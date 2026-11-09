import { EVENT_TYPES, ROLES } from "../lib/helpers.js";

export const tools = [
  {
    type: "function",
    function: {
      name: "get_calendar_events",
      description:
        "Read the Durbar school calendar (Bikram Sambat dates). Use for exam schedules, tests, festivals, school events, emergencies and vacations. For exam questions use type exam.",
      parameters: {
        type: "object",
        properties: {
          type: { type: "string", enum: EVENT_TYPES, description: "Event type. Omit to search all types." },
          bs_year: { type: "integer", description: "BS year, e.g. 2083. Omit to search the latest years." },
          month: { type: "integer", description: "BS month number 1-12 (1 Baisakh, 7 Kartik, 12 Chaitra)" },
          day: { type: "integer", description: "BS day of month" },
          subject: { type: "string", description: "Subject name filter for exams and tests" },
          keyword: { type: "string", description: "Keyword to match in title or description" },
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
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_study_material",
      description:
        "List or show units and notes (PDFs, photos, YouTube lectures) by subject. The app shows the notes as note cards automatically. Call without a subject to list available subjects. Use this only to show or list notes, not to read what is inside the PDFs.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Subject name, e.g. Computer Science" },
          unit_name: { type: "string", description: "Unit name filter" },
          keyword: { type: "string", description: "Keyword to match in note title or description" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "read_pdf_notes",
      description:
        "Open and read the text inside the PDF notes of a subject and return the most relevant pages. Use when the user asks what a PDF or note says, asks to explain, summarize or check a PDF, or asks a study question that the subject notes may answer. Call without a subject to list available subjects.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Subject name, e.g. Computer Science" },
          unit_name: { type: "string", description: "Unit name filter, e.g. Unit 1" },
          note_keyword: { type: "string", description: "Keyword to match in note title or description" },
          question: { type: "string", description: "The user's question or topic to find inside the PDFs" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_mock_questions",
      description:
        "Get random multiple choice mock test questions for a subject. Call without a subject to list available subjects.",
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
      name: "get_app_update",
      description: "Get the latest app version, what's new and the download link.",
      parameters: { type: "object", properties: {} },
    },
  },
  {
    type: "function",
    function: {
      name: "get_people",
      description:
        "Look up people in the Durbar app: students, professors, captains and moderators. Use for questions like who is the captain, list of captains, professor of a subject, find a student, how many students, who teaches X. The app shows profile cards automatically when 12 or fewer people match.",
      parameters: {
        type: "object",
        properties: {
          role: { type: "string", enum: ROLES, description: "Role filter" },
          name: { type: "string", description: "Part of the person's name" },
          subject: { type: "string", description: "Assigned subject (professors)" },
          class_level: { type: "string", description: "Class level, e.g. 11" },
          section: { type: "string", description: "Section, e.g. A or B" },
        },
      },
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
        },
      },
    },
  },
];