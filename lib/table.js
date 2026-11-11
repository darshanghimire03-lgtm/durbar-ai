const esc = (v) =>
  String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export const AS_TABLE = {
  type: "boolean",
  description: "Set true when the user asks for a table or the answer is a list of rows with several fields",
};

export function buildTable({ title, columns, rows } = {}) {
  const cols = (Array.isArray(columns) ? columns : [])
    .map((c) => String(c ?? "").slice(0, 60))
    .filter(Boolean)
    .slice(0, 12);
  if (!cols.length) return null;

  const body = (Array.isArray(rows) ? rows : []).slice(0, 100).map((r) => {
    const cells = Array.isArray(r) ? r : cols.map((c) => r?.[c]);
    return cols.map((_, i) => String(cells[i] ?? "").slice(0, 300));
  });
  if (!body.length) return null;

  return { type: "table", title: String(title || "").slice(0, 120), columns: cols, rows: body };
}

export function tableToHtml(t) {
  if (!t) return "";
  const cell = "border:1px solid #cfd4dc;padding:6px 10px;text-align:left;vertical-align:top;";
  const head = t.columns
    .map((c) => `<th style="${cell}background:#eef1f6;">${esc(c)}</th>`)
    .join("");
  const rows = t.rows
    .map((r) => `<tr>${r.map((c) => `<td style="${cell}">${esc(c)}</td>`).join("")}</tr>`)
    .join("");
  const caption = t.title ? `<caption style="text-align:left;font-weight:bold;padding:6px 0;">${esc(t.title)}</caption>` : "";
  return `<div style="overflow-x:auto;"><table style="border-collapse:collapse;width:100%;font-size:14px;">${caption}<thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}