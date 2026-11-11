import { ROLES } from "../lib/helpers.js";
import { searchPeople } from "../db/firebase.js";
import { MAX_CARD_PEOPLE, peopleCard } from "../lib/cards.js";
import { AS_TABLE, buildTable } from "../lib/table.js";

export const definitions = [
  {
    type: "function",
    function: {
      name: "get_people",
      description:
        "Look up people in the Durbar app: students, professors, captains and moderators. Use for questions like who is the captain, list of captains, professor of a subject, find a student, student list, how many students, who teaches X. The app shows profile cards when 12 or fewer people match, and a table with column headers when more match or as_table is true.",
      parameters: {
        type: "object",
        properties: {
          role: { type: "string", enum: ROLES, description: "Role filter" },
          name: { type: "string", description: "Part of the person's name" },
          subject: { type: "string", description: "Assigned subject (professors)" },
          class_level: { type: "string", description: "Class level, e.g. 11" },
          section: { type: "string", description: "Section, e.g. A or B" },
          as_table: AS_TABLE,
        },
      },
    },
  },
];

const publicPerson = (u) => ({
  name: u.fullName || null,
  role: u.role || null,
  subject: u.assignedSubject || null,
  class: u.classLevel || null,
  section: u.section || null,
});

function peopleTable(list) {
  return buildTable({
    title: `People (${list.length})`,
    columns: ["No", "Name", "Role", "Subject", "Class", "Section"],
    rows: list.map((u, i) => [i + 1, u.fullName, u.role, u.assignedSubject, u.classLevel, u.section]),
  });
}

async function getPeople(args) {
  const list = await searchPeople(args);
  const wantTable = args.as_table === true || list.length > MAX_CARD_PEOPLE;
  const table = wantTable && list.length ? peopleTable(list) : null;
  return {
    data: { count: list.length, people: list.slice(0, 40).map(publicPerson) },
    brief: {
      count: list.length,
      people: list.slice(0, MAX_CARD_PEOPLE).map((u) => `${u.fullName} - ${u.role}`),
    },
    card: table ? null : peopleCard(list),
    table,
  };
}

export const handlers = { get_people: getPeople };