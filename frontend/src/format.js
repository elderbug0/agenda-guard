export const clock = (ts) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export const clockIso = (iso) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "–";

export const duration = (s) => {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m ? `${m}m ${String(sec).padStart(2, "0")}s` : `${sec}s`;
};

export const pct = (x) => `${Math.round((x || 0) * 100)}%`;

// One of: "on" | "moved" | "off" – used for colour and wording everywhere.
export const kind = (status) => (status === "off_track" ? "off" : status === "moved_on" ? "moved" : "on");
export const kindLabel = { on: "On topic", moved: "Next item", off: "Off topic" };
