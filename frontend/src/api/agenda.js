// Agenda import.
//
// The agenda generator exports a JSON file like agenda_full.json:
//   { meeting_title, meeting_goal, items: [{ title, description, duration_min, ... }], ... }
// `parseAgenda` turns that text into the shape the bot API expects:
//   { title, goal, items: [{ title, description, minutes }] }
// Extra fields (owner, rationale, expected_outcome, ...) are ignored. A bare array of items also works.

export function parseAgenda(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("That file is not valid JSON.");
  }
  const list = Array.isArray(data) ? data : data && data.items;
  if (!Array.isArray(list)) {
    throw new Error('No agenda found. Expected an "items" list.');
  }
  const items = list
    .map((it) => ({
      title: String((it && it.title) || "").trim(),
      description: String((it && it.description) || "").trim(),
      minutes: Math.max(0, Math.round(Number(it && (it.duration_min ?? it.minutes)) || 0)),
    }))
    .filter((it) => it.title);
  if (items.length === 0) {
    throw new Error("The file has no agenda items with a title.");
  }
  return {
    title: String((!Array.isArray(data) && data.meeting_title) || "").trim(),
    goal: String((!Array.isArray(data) && data.meeting_goal) || "").trim(),
    items,
  };
}