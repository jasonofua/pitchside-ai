# Demo video: script and shot list (1:55)

From the spec: judges may stop at 2:00, so the strongest moment comes before 1:00. Record at
1080p with a large browser zoom (125%), no music or royalty-free music only, and no real
club, league or player names anywhere on screen.

## Setup before recording

1. Deploy (`azd up`) or run locally (`docker compose up`); use the Foundry models for the
   real recording (the offline mock writes from a fixed phrase bank).
2. Start the **comeback** story at **5×** (`/director/`, or the home page). Harbour City score
   at about 17' (3.5 minutes in) and 53'; the Lions answer at 71' and 88'. For a rehearsal,
   20× reaches the first goal in under a minute.
3. Open three windows: `/three/?id=<match>` (full screen), `/director/?id=<match>`, and the
   Azure portal on the Application Insights *Transaction search* for the gateway.
4. Raw footage without voice-over can be captured automatically:
   `node web/scripts/record-demo.mjs http://localhost:8000` (Playwright; WebM files in
   `web/recordings/`; needs `pnpm exec playwright install ffmpeg`, which Playwright does not
   offer on macOS 13: record there with QuickTime or OBS instead).

## Script

| Time | Shot | Voice-over |
| --- | --- | --- |
| 0:00–0:10 | Match screen. The Lions' 71' goal lands: full card, the clock, the 2D pitch. | "Every fan saw the same goal. Pitchside AI tells each one a different story." |
| 0:10–0:40 | Three Fans view on that goal: Analyst (English) with xG and the tactical why; Casual fan in Pidgin; Player Cam in Yorùbá following the Lions' number 9. Hold on each pane for a beat. | "An analyst gets the xG and why the press worked. A Lagos fan gets it in Pidgin. Player Cam follows one player, in Yorùbá. Same goal, same numbers, written live for each of them." |
| 0:40–1:05 | Director panel: the live agent trace (Moment Detector → Analyst → Narrator → Fan Lens ×3 → Localizer → Fact Checker → Producer), MCP tool calls in green. Click *Inject a wrong number*: the trace shows the Fact Checker reject it, the Fan Lens regenerate, the card pass. | "Seven agents on Microsoft Agent Framework. Every number comes from one MCP server over a deterministic stats engine. Here I slip a wrong number past the writers: the Fact Checker catches it, the card is rewritten, and only the corrected version reaches viewers." |
| 1:05–1:20 | Click *Kill the Narrator*. Cards keep arriving as stats-only cards; the trace shows the open breaker; after 20 s the Narrator is back and explained cards return. | "Models fail. Kill the Narrator and the screen keeps working on stats-only cards, then recovers on its own." |
| 1:20–1:40 | `docs/architecture.svg`, then the Azure portal: the Container Apps, and an App Insights trace of one moment across the agents. | "It runs on Azure: Foundry models, Agent Framework, Container Apps, Event Hubs, Cosmos DB and Web PubSub, traced end to end in Application Insights." |
| 1:40–1:55 | Recap page at full time: headline, key moments, player of the match; switch to Pidgin and Yorùbá; click *Copy as JSON*. | "At full time, a recap in any language, ready for studio, broadcast and streaming." |

## Checklist

- [ ] 1080p, under 2:00, captions on.
- [ ] Nothing real on screen: only the four fictional clubs; no browser bookmarks or tabs
      with real club names.
- [ ] Upload to YouTube (public or unlisted) and put the link in the README and on the
      submission page.
