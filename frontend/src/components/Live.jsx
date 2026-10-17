import { useEffect, useRef, useState } from "react";
import { bot } from "../api/bot.js";
import { usePoll } from "../usePoll.js";
import { clock, kind, kindLabel, pct } from "../format.js";

export default function Live({ sessionId, onEnded }) {
  const [s, setS] = useState(null);
  const [segments, setSegments] = useState([]);
  const [partial, setPartial] = useState(null); // the sentence being spoken right now
  const listRef = useRef(null);
  const [error, setError] = useState("");
  const [showText, setShowText] = useState(true);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  usePoll(async () => {
    try {
      const [session, tr] = await Promise.all([bot.get(sessionId), bot.transcript(sessionId, 12)]);
      setS(session);
      setSegments(tr.segments);
      setPartial(tr.partial);
      setError("");
      if (session.status === "ended") onEnded();
    } catch (e) {
      setError(e.message);
    }
  }, 1000);

  // Keep the newest line (including the live one) in view.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [segments, partial]);

  async function testAlert() {
    setBusy("test");
    setNote("");
    try {
      const r = await bot.testAlert(sessionId, 1);
      const bad = Object.entries(r.outcome).filter(([, v]) => v !== "ok");
      setNote(bad.length ? `Test alert: ${bad.map(([k, v]) => `${k} ${v}`).join(", ")}` : "Test alert sent to the meeting.");
    } catch (e) {
      setNote(e.message);
    } finally {
      setBusy("");
    }
  }

  async function end() {
    if (!window.confirm("End the session and remove the bot from the meeting?")) return;
    setBusy("end");
    try {
      await bot.end(sessionId);
      onEnded();
    } catch (e) {
      setNote(e.message);
      setBusy("");
    }
  }

  if (!s) {
    return <p className={`muted center ${error ? "bad-text" : ""}`}>{error || "Connecting to the bot…"}</p>;
  }

  const events = s.recent_events;
  const last = events[events.length - 1];
  const state = s.status === "waiting" ? "wait" : last ? kind(last.status) : "listen";
  const headline = {
    wait: "Waiting for the bot to be admitted",
    listen: "Listening…",
    on: "On topic",
    moved: "Moved to another item",
    off: "Drifting off topic",
  }[state];
  const sub = {
    wait: "Open the Meet and admit “Agenda Guard” from the lobby.",
    listen: "The bot is in. The first verdict arrives after a few seconds of speech.",
    on: last?.reason,
    moved: last?.reason,
    off: last?.reason,
  }[state];

  return (
    <div className="live">
      {error && (
        <p className="banner bad" role="alert">
          {error} <span className="muted">(retrying)</span>
        </p>
      )}

      <section className={`status ${state}`} aria-live="polite">
        <div className="status-main">
          <span className="dot" aria-hidden="true" />
          <div>
            <h1>{headline}</h1>
            {sub && <p className="reason">{sub}</p>}
          </div>
        </div>
        <dl className="stats">
          <div>
            <dt>Alerts sent</dt>
            <dd>{s.alert_count}</dd>
          </div>
          <div>
            <dt>Off-topic streak</dt>
            <dd>{s.off_track_streak}</dd>
          </div>
          <div>
            <dt>Verdicts</dt>
            <dd>{events.length >= 20 ? "20+" : events.length}</dd>
          </div>
        </dl>
      </section>

      <div className="grid">
        <section className="card">
          <h2>Agenda</h2>
          <ol className="agenda">
            {s.agenda.map((it) => (
              <li key={it.id} className={it.id === s.current_item.id ? "current" : ""}>
                <span className="marker" aria-hidden="true" />
                <div>
                  <strong>{it.title}</strong>
                  {it.description && <p className="muted small">{it.description}</p>}
                </div>
                {it.minutes > 0 && <span className="muted small nowrap">{it.minutes} min</span>}
              </li>
            ))}
          </ol>
        </section>

        <section className="card">
          <h2>Verdict timeline</h2>
          {events.length === 0 ? (
            <p className="muted small">Nothing yet.</p>
          ) : (
            <>
              <div className="strip" role="img" aria-label="Recent verdicts, oldest to newest">
                {events.map((e, i) => (
                  <span key={i} className={`bar ${kind(e.status)} ${e.alert_level ? "alert" : ""}`} title={`${clock(e.ts)} · ${kindLabel[kind(e.status)]}`} />
                ))}
              </div>
              <ul className="feed">
                {[...events].reverse().slice(0, 6).map((e, i) => (
                  <li key={`${e.ts}-${i}`}>
                    <span className={`tag ${kind(e.status)}`}>{kindLabel[kind(e.status)]}</span>
                    <span className="feed-reason">{e.reason || "–"}</span>
                    <span className="muted small nowrap mono">
                      {pct(e.confidence)} · {clock(e.ts)}
                    </span>
                    {e.alert_level ? <span className="tag alert">Alert sent</span> : null}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <h2>Live transcript</h2>
          <button className="btn ghost" onClick={() => setShowText((v) => !v)}>
            {showText ? "Hide" : "Show"}
          </button>
        </div>
        {showText &&
          (segments.length === 0 && !partial ? (
            <p className="muted small">No speech heard yet.</p>
          ) : (
            <ul className="transcript" ref={listRef}>
              {segments.map((g, i) => (
                <li key={`${g.ts}-${i}`}>
                  <span className="muted small mono">{clock(g.ts)}</span>
                  <span>
                    <b>{g.speaker}</b> {g.text}
                  </span>
                </li>
              ))}
              {partial && (
                <li className="live-line">
                  <span className="muted small mono">…</span>
                  <span>
                    <b>{partial.speaker}</b> {partial.text}
                  </span>
                </li>
              )}
            </ul>
          ))}
      </section>

      <footer className="actions">
        {note && <span className="muted small">{note}</span>}
        <button className="btn ghost" onClick={testAlert} disabled={!!busy || s.status !== "active"} title={s.status !== "active" ? "Available once the bot is in the call" : ""}>
          {busy === "test" ? "Sending…" : "Send test alert"}
        </button>
        <button className="btn danger" onClick={end} disabled={!!busy}>
          {busy === "end" ? "Ending…" : "End meeting"}
        </button>
      </footer>
    </div>
  );
}