# Agenda Guard

A bot that joins a Google Meet through Recall.ai, listens, and compares the discussion to the agenda. When the meeting stays off topic, it does two things at once: it posts a short message in the Meet chat and plays a loud alert sound. It never speaks.

## Setup

You need Python 3.11+, a Recall.ai account, an OpenAI API key and ngrok.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Fill in `.env` (the keys, and the Recall.ai region of your account).

## Run

```bash
# terminal 1
uvicorn app.main:app --reload --port 8000

# terminal 2: gives Recall.ai a public URL to call
ngrok http 8000
```

Put the ngrok `https://...` URL into `WEBHOOK_BASE_URL` in `.env`, then restart uvicorn.

## Test live transcription first (no AI)

`.env.example` ships with `ANALYSIS_ENABLED=false`, so the bot only transcribes: no OpenAI calls, no alerts, and no OpenAI key needed. Do steps 1 and 2 below, admit the bot in the Meet, and talk. Every sentence appears in the uvicorn terminal as a `[transcript ...]` line within a few seconds, and you can also read it with:

```bash
curl localhost:8000/sessions/SESSION_ID/transcript
```

When transcription works, set `ANALYSIS_ENABLED=true` and add `OPENAI_API_KEY` in `.env`, then restart uvicorn.

## Try it

```bash
# 1. create a session
curl -X POST localhost:8000/sessions -H "content-type: application/json" -d '{
  "meeting_url": "https://meet.google.com/abc-defg-hij",
  "agenda": [
    {"title": "Q3 roadmap", "description": "Which features ship in Q3", "minutes": 20},
    {"title": "Hiring plan", "description": "Open roles and interviews", "minutes": 15}
  ]
}'

# 2. send the bot in (use the id from step 1), then admit it in the Meet as the host
curl -X POST localhost:8000/sessions/SESSION_ID/start

# 3. Phase 0 check: does the chat message AND the sound come through in the Meet?
curl -X POST localhost:8000/sessions/SESSION_ID/test-alert

# 4. watch it live, then finish and get the report
curl localhost:8000/sessions/SESSION_ID
curl -X POST localhost:8000/sessions/SESSION_ID/end
```

The report lists every analysis window with the reason the model gave, so you can see why each alert fired. Reports are also saved in `agenda_guard.db` (SQLite).

## How it works

1. Recall.ai sends transcript events to `POST /webhooks/recall`.
2. Every 20 s, per active session, the last 90 s of transcript goes to OpenAI, which answers `on_track`, `moved_on` or `off_track`.
3. The drift engine (`app/drift.py`) alerts after 3 off-track windows in a row (confidence 0.7+), then waits 180 s before the next alert. The first alert is level 1, later ones level 2.
4. The reactor sends the chat message and plays the sound in parallel, so one failing never blocks the other.

All thresholds are in `app/config.py` and can be overridden in `.env`.

## Good to know

- **Sound file:** `app/sounds/alert.mp3` is a synthesized placeholder siren. Replace it with any royalty-free or CC0 horn/siren clip (keep the same file name).
- **Meet limits:** chat messages go to everyone and are cut at 500 characters. Google Meet noise cancellation might suppress the bot's sound, which is why the chat message is always sent too.
- **Bot status events:** the session becomes active when the first transcript arrives. To also get `bot.in_call_recording`, `bot.call_ended` and `bot.done` (which end the session automatically), add a webhook for them in the Recall.ai dashboard pointing at the same `/webhooks/recall` URL. Without it, call `POST /sessions/{id}/end` when the meeting is over.
- **Signatures:** set `RECALL_WORKSPACE_SECRET` to reject webhooks that were not sent by Recall.ai.
- **Sessions live in memory** and are lost on restart (reports are kept). Redis and Postgres come later, as in the plan.

## Tests and evaluation

```bash
pytest                      # drift engine, webhooks, loop, reactor (no network needed)
python -m eval.run_eval     # measures analyzer accuracy on eval/cases.jsonl (uses your OpenAI key)
```

Add your own labeled snippets to `eval/cases.jsonl` to tune the prompt and thresholds. Watch the false-alarm count most closely.
