import { useRef, useState } from "react";
import { bot } from "../api/bot.js";
import { parseAgenda } from "../api/agenda.js";

const MEET_RE = /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}(\?.*)?$/i;

// UI mock only: these sounds are not real yet and the choice is not sent to the bot.
const SOUNDS = [
  { id: "default", label: "Default alert" },
  { id: "chime", label: "Soft chime" },
  { id: "buzzer", label: "Buzzer" },
];

const MODES = {
  easy: {
    label: "Easy",
    text: "A starting topic is optional. The talk can move between connected topics as often as you like. A sudden unrelated jump triggers an alert.",
  },
  medium: {
    label: "Medium",
    text: "Pick a starting topic. You may move to one connected topic, once. A second switch, or a sudden unrelated jump, triggers an alert.",
  },
  high: {
    label: "High",
    text: "Pick one topic and stay on it. Any switch to another topic triggers an alert.",
  },
};

export default function Setup({ onStarted }) {
  const [agenda, setAgenda] = useState([]);
  const [meta, setMeta] = useState(null); // meeting title + goal from the imported file
  const fileRef = useRef(null);
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState("medium");
  const [noStart, setNoStart] = useState(false);
  const [start, setStart] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importError, setImportError] = useState("");
  const [sound, setSound] = useState(SOUNDS[0].id);

  async function importAgenda(e) {
    const file = e.target.files && e.target.files[0];
    e.target.value = ""; // lets the same file be picked again
    if (!file) return;
    setImportError("");
    try {
      const parsed = parseAgenda(await file.text());
      setAgenda(parsed.items);
      setMeta(parsed.title || parsed.goal ? { title: parsed.title, goal: parsed.goal } : null);
      setStart(0);
    } catch (err) {
      setImportError(`Import failed: ${err.message}`);
    }
  }

  const edit = (i, patch) => setAgenda((a) => a.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const remove = (i) => {
    setAgenda((a) => a.filter((_, j) => j !== i));
    setStart((s) => (i < s ? s - 1 : i === s ? 0 : s));
  };
  const add = () => setAgenda((a) => [...a, { title: "", description: "", minutes: 0 }]);

  const skipTopic = mode === "easy" && noStart;
  const cleaned = agenda.filter((it) => it.title.trim());
  const chosen = agenda[start] || null;
  const startItem = chosen && chosen.title.trim() ? chosen : cleaned[0];
  const urlOk = MEET_RE.test(url.trim());
  const canStart = urlOk && !busy && (skipTopic || cleaned.length > 0);

  async function startMeeting() {
    setBusy(true);
    setError("");
    try {
      const clean = (it) => ({
        title: it.title.trim(),
        description: (it.description || "").trim(),
        minutes: Number(it.minutes) || 0,
      });
      let payload = [];
      let startIndex = 0;
      if (!skipTopic) {
        if (mode === "high") {
          payload = [clean(startItem)]; // High mode uses exactly one topic
        } else {
          payload = cleaned.map(clean);
          startIndex = Math.max(0, cleaned.indexOf(startItem));
        }
      }
      const session = await bot.createSession(url.trim(), payload, mode, startIndex);
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
        <h1>Keep the meeting on its topic.</h1>
        <p className="lede">
          Choose how strict the bot is, review the topics, paste the Google Meet link, and the bot will join and
          nudge the group in chat when the talk drifts.
        </p>
      </section>

      <section className="card">
        <h2>Meeting style</h2>
        <label className="field">
          <span>Strictness</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Strictness">
            {Object.entries(MODES).map(([key, m]) => (
              <option key={key} value={key}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <p className="mode-text">{MODES[mode].text}</p>
        {mode === "easy" && (
          <label className="pick" style={{ marginTop: 12 }}>
            <input type="checkbox" checked={noStart} onChange={(e) => setNoStart(e.target.checked)} />
            Don't set a starting topic
          </label>
        )}
      </section>

      {skipTopic ? (
        <section className="card">
          <h2>Topic</h2>
          <p className="muted small">
            No starting topic. The bot follows the conversation and only alerts on sudden jumps to an unrelated subject.
          </p>
        </section>
      ) : (
        <section className="card">
          <div className="card-head">
            <div>
              <h2>{mode === "high" ? "Topic" : "Topics"}</h2>
              <p className="muted small">
                Descriptions matter: the bot judges "on topic" against them, so list the words people would use.
                {mode === "high" && " Only the selected item is used."}
              </p>
            </div>
            <button className="btn ghost" onClick={() => fileRef.current.click()} disabled={busy}>
              Import agenda
            </button>
            <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={importAgenda} />
          </div>

          {importError && (
            <p className="banner bad" role="alert" style={{ marginTop: 12 }}>
              {importError}
            </p>
          )}

          {meta && (
            <p className="mode-text">
              {meta.title && <strong>{meta.title}</strong>}
              {meta.title && meta.goal && " · "}
              {meta.goal}
            </p>
          )}

          {agenda.length === 0 ? (
            <p className="muted small" style={{ marginTop: 14 }}>
              No topics yet. Import an agenda file (.json) or add an item by hand.
            </p>
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
                    <label className={`pick ${start === i ? "on" : ""}`}>
                      <input type="radio" name="start" checked={start === i} onChange={() => setStart(i)} />
                      Starting topic
                    </label>
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
          <button className="btn ghost add" onClick={add}>
            + Add item
          </button>
        </section>
      )}

      <section className="card">
        <h2>Alert sound</h2>
        <label className="field">
          <span>Sound played in the meeting when an alert fires</span>
          <select value={sound} onChange={(e) => setSound(e.target.value)} aria-label="Alert sound">
            {SOUNDS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
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
        <button className="btn primary" disabled={!canStart} onClick={startMeeting}>
          {busy ? "Sending the bot…" : "Start meeting"}
        </button>
      </section>
    </div>
  );
}