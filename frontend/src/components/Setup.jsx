import { useEffect, useState } from "react";
import { bot } from "../api/bot.js";
import { fetchAgenda } from "../api/agenda.js";

const MEET_RE = /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}(\?.*)?$/i;

export default function Setup({ onStarted }) {
  const [agenda, setAgenda] = useState(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadAgenda = () => {
    setAgenda(null);
    fetchAgenda().then(setAgenda);
  };
  useEffect(loadAgenda, []);

  const edit = (i, patch) => setAgenda((a) => a.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const remove = (i) => setAgenda((a) => a.filter((_, j) => j !== i));
  const add = () => setAgenda((a) => [...a, { title: "", description: "", minutes: 0 }]);

  const cleaned = (agenda || []).filter((it) => it.title.trim());
  const urlOk = MEET_RE.test(url.trim());
  const canStart = cleaned.length > 0 && urlOk && !busy;

  async function start() {
    setBusy(true);
    setError("");
    try {
      const payload = cleaned.map((it) => ({
        title: it.title.trim(),
        description: (it.description || "").trim(),
        minutes: Number(it.minutes) || 0,
      }));
      const session = await bot.createSession(url.trim(), payload);
      await bot.start(session.id);
      onStarted(session.id);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="setup">
      <section className="hero">
        <h1>Keep the meeting on its agenda.</h1>
        <p className="lede">
          Review the agenda, paste the Google Meet link, and the bot will join and nudge the group in chat when
          the talk drifts away.
        </p>
      </section>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>Agenda</h2>
            <p className="muted small">
              Descriptions matter: the bot judges "on topic" against them, so list the words people would use.
            </p>
          </div>
          <button className="btn ghost" onClick={loadAgenda} disabled={busy}>
            Regenerate
          </button>
        </div>

        {agenda === null ? (
          <p className="muted">Generating agenda…</p>
        ) : (
          <ol className="items">
            {agenda.map((it, i) => (
              <li key={i} className="item">
                <span className="idx">{i + 1}</span>
                <div className="fields">
                  <input
                    className="title"
                    placeholder="Item title"
                    value={it.title}
                    onChange={(e) => edit(i, { title: e.target.value })}
                    aria-label={`Item ${i + 1} title`}
                  />
                  <textarea
                    rows={2}
                    placeholder="What belongs to this item?"
                    value={it.description}
                    onChange={(e) => edit(i, { description: e.target.value })}
                    aria-label={`Item ${i + 1} description`}
                  />
                </div>
                <label className="mins">
                  <input
                    type="number"
                    min="0"
                    value={it.minutes}
                    onChange={(e) => edit(i, { minutes: e.target.value })}
                    aria-label={`Item ${i + 1} minutes`}
                  />
                  <span>min</span>
                </label>
                <button className="icon" onClick={() => remove(i)} aria-label={`Remove item ${i + 1}`} title="Remove">
                  ×
                </button>
              </li>
            ))}
          </ol>
        )}
        {agenda && (
          <button className="btn ghost add" onClick={add}>
            + Add item
          </button>
        )}
      </section>

      <section className="card">
        <h2>Meeting</h2>
        <label className="field">
          <span>Google Meet link</span>
          <input
            type="url"
            placeholder="https://meet.google.com/abc-defg-hij"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={url !== "" && !urlOk}
          />
          {url !== "" && !urlOk && <em className="hint bad">That doesn't look like a Meet link (abc-defg-hij).</em>}
        </label>
        <p className="consent">
          Everyone in the meeting should know the bot is transcribing. It posts a neutral chat reminder and an
          alert sound, never speaks, and doesn't store audio.
        </p>
        {error && (
          <p className="banner bad" role="alert">
            {error}
          </p>
        )}
        <button className="btn primary" disabled={!canStart} onClick={start}>
          {busy ? "Sending the bot…" : "Start meeting"}
        </button>
      </section>
    </div>
  );
}
