import { useEffect, useState } from "react";
import { bot } from "../api/bot.js";
import { clockIso, duration, kind, kindLabel, pct } from "../format.js";

const REASONS = {
  ended_by_host: "Ended from this page",
  call_ended: "The call ended",
  done: "The bot finished",
  fatal: "The bot hit an error",
};

export default function Report({ sessionId, onNew }) {
  const [r, setR] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    bot.report(sessionId).then(setR).catch((e) => setError(e.message));
  }, [sessionId]);

  if (error) {
    return (
      <div className="center">
        <p className="banner bad">{error}</p>
        <button className="btn primary" onClick={onNew}>
          New meeting
        </button>
      </div>
    );
  }
  if (!r) return <p className="muted center">Building the report…</p>;

  const share = r.off_track_share;
  const verdict =
    r.windows_analyzed === 0
      ? "No speech was analyzed."
      : share < 0.1
        ? "The group stayed on the agenda."
        : share < 0.3
          ? "A few detours, mostly on track."
          : "The meeting drifted a lot.";

  return (
    <div className="report">
      <section className="hero">
        <h1>{verdict}</h1>
        <p className="lede">{REASONS[r.end_reason] || "Meeting ended"} · {clockIso(r.started_at)} – {clockIso(r.ended_at)}</p>
      </section>

      <dl className="tiles">
        <div>
          <dt>Duration</dt>
          <dd>{duration(r.duration_s)}</dd>
        </div>
        <div>
          <dt>Off-topic share</dt>
          <dd>{pct(share)}</dd>
        </div>
        <div>
          <dt>Alerts sent</dt>
          <dd>{r.alert_count}</dd>
        </div>
        <div>
          <dt>Windows checked</dt>
          <dd>{r.windows_analyzed}</dd>
        </div>
      </dl>

      <div className="grid">
        <section className="card">
          <h2>Alerts</h2>
          {r.alerts.length === 0 ? (
            <p className="muted small">No alerts fired.</p>
          ) : (
            <ul className="feed">
              {r.alerts.map((a, i) => (
                <li key={i}>
                  <span className="tag alert">Level {a.alert_level}</span>
                  <span className="feed-reason">{a.reason || "–"}</span>
                  <span className="muted small nowrap mono">{clockIso(a.time)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <h2>Timeline</h2>
          {r.events.length === 0 ? (
            <p className="muted small">Nothing to show.</p>
          ) : (
            <div className="strip tall" role="img" aria-label="All verdicts, oldest to newest">
              {r.events.map((e, i) => (
                <span key={i} className={`bar ${kind(e.status)} ${e.alert_level ? "alert" : ""}`} title={`${clockIso(e.time)} · ${kindLabel[kind(e.status)]}`} />
              ))}
            </div>
          )}
          <p className="muted small legend">
            <i className="sw on" /> on topic <i className="sw moved" /> next item <i className="sw off" /> off topic
          </p>
        </section>
      </div>

      <footer className="actions">
        <button className="btn primary" onClick={onNew}>
          New meeting
        </button>
      </footer>
    </div>
  );
}
