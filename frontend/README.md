# Agenda Guard – frontend

A small React (Vite) UI for the Agenda Guard bot: set up the meeting, watch it live, read the report.

## Run it

You need Node.js 18 or newer (https://nodejs.org).

```bash
# terminal 1: the bot, as usual
uvicorn app.main:app --reload --port 8000

# terminal 2: the UI (from the agenda-guard folder)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The UI forwards `/api/*` to the bot on port 8000 (see `vite.config.js`),
so **you do not need to change the bot's code** and there is no CORS setup.
ngrok is still needed for Recall's webhooks, exactly as before.

If your bot runs on another port: `BOT_URL=http://localhost:9000 npm run dev`.

## The three screens

1. **Set up:** an editable agenda and the Meet link. "Start meeting" calls `POST /sessions` and then
   `POST /sessions/{id}/start`.
2. **Live:** polls `GET /sessions/{id}` and `/transcript` every 2 seconds. Shows the current verdict, agenda
   item, off-topic streak, alert count, a verdict timeline and the live transcript. Buttons: send a test alert,
   end the meeting.
3. **Report:** loads `GET /sessions/{id}/report` when the meeting ends (from the button, or when Recall reports
   the call is over).

A refresh during a meeting resumes it (the session id is kept in the browser's localStorage).

## Connecting the agenda generator later

Everything agenda-related goes through **`src/api/agenda.js`**. Today `fetchAgenda()` returns a hard-coded
mock. Replace its body with a call to your generator, returning items shaped like
`{ title, description, minutes }`. The "Regenerate" button already calls it.

## Files

```
src/api/bot.js       all calls to the bot
src/api/agenda.js    mock agenda (replace later)
src/components/      Setup, Live, Report, Stepper
src/styles.css       all styling (light and dark)
```
