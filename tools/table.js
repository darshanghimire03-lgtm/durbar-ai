import { buildTable } from "../lib/table.js";

export const definitions = [
  {
    type: "function",
    function: {
      name: "send_table",
      description:
        "Send a table with column headers and filled rows to the app. Use it whenever the answer is a list of items with several fields (comparisons, schedules, student lists, study plans, search results, definitions) or when the user asks for a table. Fill every cell.",
      parameters: {
        type: "object",
        properties: {
          title: { type: "string", description: "Short table title" },
          columns: { type: "array", items: { type: "string" }, description: "Column header names" },
          rows: {
            type: "array",
            items: { type: "array", items: { type: "string" } },
            description: "Each row is an array of cell values in the same order as columns",
          },
        },
        required: ["columns", "rows"],
      },
    },
  },
];

async function sendTable(args) {
  const table = buildTable(args);
  if (!table) return { data: { error: "columns and at least one row are required" }, card: null };
  return { data: { rows: table.rows.length }, brief: { rows: table.rows.length }, card: null, table };
}

export const handlers = { send_table: sendTable };