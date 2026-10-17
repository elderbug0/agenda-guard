// Thin wrapper around the Agenda Guard bot API.
// In dev, Vite forwards /api/* to the bot (see vite.config.js), so there is no CORS to deal with.
const BASE = import.meta.env.VITE_BOT_API || "/api";

async function call(method, path, body) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Can't reach the bot. Is uvicorn running on port 8000?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const bot = {
  createSession: (meeting_url, agenda, mode = "medium", start_index = 0) =>
    call("POST", "/sessions", { meeting_url, agenda, mode, start_index }),
  start: (id) => call("POST", `/sessions/${id}/start`),
  get: (id) => call("GET", `/sessions/${id}`),
  transcript: (id, last = 30) => call("GET", `/sessions/${id}/transcript?last=${last}`),
  testAlert: (id, level = 1) => call("POST", `/sessions/${id}/test-alert?level=${level}`),
  end: (id) => call("POST", `/sessions/${id}/end`),
  report: (id) => call("GET", `/sessions/${id}/report`),
};