export const BS_MONTHS = [
  "Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Ashwin",
  "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
];
export const EVENT_TYPES = ["exam", "test", "festival", "school_event", "emergency", "vacation"];
export const ROLES = ["student", "professor", "captain", "moderator"];
export const VERIFIED_ROLES = ["professor", "captain", "moderator"];

export const norm = (v) => String(v ?? "").toLowerCase().trim();
export const has = (v, q) => norm(v).includes(norm(q));
export const seg = (...parts) => parts.map((x) => encodeURIComponent(String(x))).join("/");
export const clip = (v, n) => String(v ?? "").slice(0, n);

export const cleanUrl = (u) =>
  typeof u === "string" && /^https?:\/\//i.test(u.trim()) ? u.trim() : "";

export function matchKey(keys, input) {
  if (!input) return null;
  const q = norm(input);
  return (
    keys.find((k) => norm(k) === q) ||
    keys.find((k) => norm(k).includes(q) || q.includes(norm(k))) ||
    null
  );
}

export function bsDateText(month, day, year) {
  const name = BS_MONTHS[Number(month) - 1];
  if (!name || !day) return "";
  return year ? `${name} ${day}, ${year}` : `${name} ${day}`;
}

export function cleanReply(text) {
  return String(text ?? "")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, "$1: $2")
    .replace(/\*\*|__/g, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*[*•]\s+/gm, "- ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}