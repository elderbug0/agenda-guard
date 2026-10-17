# Agenda Guard

Agenda Guard joins a Google Meet through Recall.ai, compares its live transcript with a supplied agenda, and posts a neutral chat reminder plus an optional alert sound when the group stays off topic. It does not speak and does not store audio.

## Before you start

You need Python 3.11 or newer, a Recall.ai account/API key, an OpenAI API key for classification, and a public HTTPS URL that Recall.ai can reach. ngrok is convenient for local development.

Everyone in the meeting should know that transcription is enabled before the bot joins.

## Quick start

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `RECALL_API_KEY`, `OPENAI_API_KEY`, and your Recall region. Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

In a second terminal, expose it publicly:

```bash
ngrok http 8000
```

Copy the `https://...` URL reported by ngrok into `WEBHOOK_BASE_URL` in `.env`, then restart Uvicorn. Your URL must be reachable by Recall.ai; `localhost` will not work.

Check that the service is up:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"ok": true}
```

## Run a meeting

### 1. Create a session

Replace the Meet URL and agenda items with your own.

```bash
curl -X POST http://localhost:8000/sessions \
  -H 'content-type: application/json' \
  -d '{
    "meeting_url": "https://meet.google.com/abc-defg-hij",
    "agenda": [
      {"title": "Q3 roadmap", "description": "Decide which features ship in Q3", "minutes": 20},
      {"title": "Hiring plan", "description": "Discuss open roles and interviews", "minutes": 15}
    ]
  }'
```

Copy the returned `id`; it is referred to below as `SESSION_ID`.

### 2. Send the bot to the meeting

```bash
curl -X POST http://localhost:8000/sessions/SESSION_ID/start
```

Admit **Agenda Guard** from the Google Meet lobby. The session becomes `active` when Recall sends the first transcript or `bot.in_call_recording` event.

### 3. Confirm alerts work

After the bot has joined, trigger a harmless test alert:

```bash
curl -X POST 'http://localhost:8000/sessions/SESSION_ID/test-alert?level=1'
```

It should post a Meet chat message and play the configured MP3 through the bot. The response reports each outcome separately, so a sound failure does not hide a successful chat message.

### 4. Monitor the session

```bash
curl http://localhost:8000/sessions/SESSION_ID
curl 'http://localhost:8000/sessions/SESSION_ID/transcript?last=50'
```

The first endpoint shows session state, current agenda item, current off-topic streak, alert count, and recent decisions. The second returns recent, in-memory transcript segments.

### 5. End and retrieve the report

```bash
curl -X POST http://localhost:8000/sessions/SESSION_ID/end
curl http://localhost:8000/sessions/SESSION_ID/report
```

Ending the session asks Recall.ai to remove the bot and saves a JSON report in `agenda_guard.db`. Transcript data stays only in memory and is lost on restart; the report does not include transcript text.

## How classification and alarms work

Recall sends `transcript.data` events to `POST /webhooks/recall`. Each word is retained with its `text`, `start_timestamp`, and `end_timestamp`.

1. Duplicate retries are ignored and late words are ordered by their media timestamp.
2. Every 10 seconds, when at least 8 new words and 15 stable words are available, the service sends the latest stable 30-second window to OpenAI.
3. The public result is `on_topic` or `off_topic`. Internally, the model can also identify a transition to another agenda item as `moved_on`; that counts as on-topic and switches the active item.
4. Two consecutive confident off-topic windows trigger one alert. Alerts then have a 60-second cooldown.

The default alarm uses both channels in parallel:

- Meet chat: a short, participant-name-free reminder of the active agenda item.
- Audio: [`app/sounds/alert.mp3`](app/sounds/alert.mp3), if present.

## Configuration

All settings are environment variables and can be placed in `.env`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `RECALL_API_KEY` | Recall.ai API key | required |
| `RECALL_REGION` | Recall.ai API region | `us-east-1` |
| `WEBHOOK_BASE_URL` | Public base URL for Recall callbacks | required |
| `RECALL_WORKSPACE_SECRET` | Optional webhook signature secret | empty |
| `OPENAI_API_KEY` | OpenAI key used for classification | required when analysis is enabled |
| `ANALYSIS_ENABLED` | Set `false` for transcript-only testing | `true` |
| `ANALYZER_MODEL` | OpenAI model for classification | `gpt-4o-mini` |
| `ANALYSIS_INTERVAL_S` | Decision cadence | `10` |
| `WINDOW_S` | Timed transcript window length | `30` |
| `MIN_WORDS` | Minimum stable words in a window | `15` |
| `MIN_NEW_WORDS` | New words needed before another decision | `8` |
| `STREAK_NEEDED` | Consecutive off-topic decisions before an alert | `2` |
| `COOLDOWN_S` | Seconds before another alert may fire | `60` |

For a safe first integration, use `ANALYSIS_ENABLED=false`. This verifies Recall delivery and transcript handling without OpenAI calls or meeting alerts. Turn it back on after you confirm that transcript events arrive.

## Recall webhook setup

The bot creation call registers `transcript.data` against:

```text
https://YOUR-PUBLIC-URL/webhooks/recall
```

To have the app close sessions automatically, also configure `bot.in_call_recording`, `bot.call_ended`, `bot.done`, and `bot.fatal` in the Recall.ai dashboard to use the same URL. Without those status events, end meetings through `POST /sessions/SESSION_ID/end`.

Set `RECALL_WORKSPACE_SECRET` when Recall provides a workspace webhook signing secret. The receiver rejects unsigned or invalidly signed requests with HTTP 401 when this setting is present.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `Missing setting(s)` when starting | Set `RECALL_API_KEY` and `WEBHOOK_BASE_URL`; add `OPENAI_API_KEY` unless transcript-only mode is enabled. |
| Bot never becomes active | Admit it to the Meet and check the Uvicorn log for `[transcript ...]`. Confirm that `WEBHOOK_BASE_URL` is public HTTPS. |
| No alert after a short tangent | Expected: the system requires sustained, confident off-topic speech. |
| Chat works but audio does not | Check that `app/sounds/alert.mp3` exists and that Meet noise cancellation is not suppressing it. |
| `401 Invalid webhook signature` | Verify `RECALL_WORKSPACE_SECRET` is the correct Recall workspace secret, without accidental whitespace. |

## Tests and evaluation

```bash
pytest
python -m eval.run_eval
```

`pytest` exercises webhook ingestion, timed-word ordering, the classifier loop, drift gating, and alert delivery with no network calls. The evaluation command calls OpenAI against [`eval/cases.jsonl`](eval/cases.jsonl); add consented, labeled examples there before changing thresholds or prompts. Track false off-topic alarms most closely.
