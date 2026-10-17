import { useEffect, useState } from "react";
import { bot } from "./api/bot.js";
import Setup from "./components/Setup.jsx";
import Live from "./components/Live.jsx";
import Report from "./components/Report.jsx";
import Stepper from "./components/Stepper.jsx";

const KEY = "agenda-guard-session";
const load = () => {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
};
const save = (id) => {
  try {
    id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY);
  } catch {
    /* storage can be blocked; the app still works without it */
  }
};

export default function App() {
  // stage: "setup" -> "live" -> "report"
  const [stage, setStage] = useState("setup");
  const [sessionId, setSessionId] = useState(null);
  const [resuming, setResuming] = useState(true);

  // After a page refresh, pick up the running session instead of losing it.
  useEffect(() => {
    const id = load();
    if (!id) return setResuming(false);
    bot
      .get(id)
      .then((s) => {
        setSessionId(id);
        setStage(s.status === "ended" ? "report" : s.bot_id ? "live" : "setup");
      })
      .catch(() => save(null))
      .finally(() => setResuming(false));
  }, []);

  const started = (id) => {
    save(id);
    setSessionId(id);
    setStage("live");
  };
  const ended = () => setStage("report");
  const reset = () => {
    save(null);
    setSessionId(null);
    setStage("setup");
  };

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <span className="brand-name">Agenda Guard</span>
        </div>
        <Stepper stage={stage} />
      </header>
      <main>
        {resuming ? (
          <p className="muted center">Looking for a running meeting…</p>
        ) : stage === "setup" ? (
          <Setup onStarted={started} />
        ) : stage === "live" ? (
          <Live sessionId={sessionId} onEnded={ended} />
        ) : (
          <Report sessionId={sessionId} onNew={reset} />
        )}
      </main>
    </div>
  );
}
