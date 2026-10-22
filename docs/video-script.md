# A 60-second screen recording of the demo

For the owner to record, with the Windows recorder (Win+G, then Capture) or any free screen recorder. The words are a suggestion in plain language; say them your own way. Every number is on the screen, so read it from there rather than from memory.

**Before recording**

- Open the demo (`https://shubham261299.github.io/agent-blackbox/`, or locally `npm run dev:demo` in `frontend/`) in a window about 1280 pixels wide, at 100% zoom, light theme.
- Close other tabs and notifications. Start on the Runs page with the "Start here" card visible.
- Do one dry run without recording. The pages load instantly; there is nothing to wait for.

**The script**

| Time | On screen | Say |
|---|---|---|
| 0:00 | The Runs page, the "Start here" card | "This is Agent Blackbox. It records everything an AI agent does, then checks the recording. This is a demo built from real runs of a small support agent on a local model. Nothing here is live." |
| 0:10 | Click stop 1, **A run that failed** | "Here the agent was refunding an order and a tool did not answer in time, so the run failed." |
| 0:18 | Point at "Where to look first", then scroll to the trace and the red bar | "The page says which step to look at first, and the trace shows it in red. No guessing." |
| 0:28 | Back, then click stop 3, **A fix that worked** | "I taught the agent to retry a failed step. I planted four faults on purpose." |
| 0:36 | Point at the headline and the cost table | "Three of them stopped mattering, none got worse, and it cost three extra retries." |
| 0:43 | Back, then click stop 4, **A fix that did not** | "Then I tried rewriting the instructions. It looked like an improvement." |
| 0:50 | Point at "fixed" and "broken" | "On 24 cases it fixed two and broke five. The page lists which ones. A fix that breaks working cases is not free, and this is how I found out." |
| 0:57 | Scroll to the "About this demo" line | "Everything is local, free, and the code is on GitHub." |

**After recording**

- Trim the start and end. Keep it under 60 seconds. Export as MP4.
- Add the video to the repository's social posts or the GitHub README as a link; do not commit the video file itself (it is large and the GIF in the README already shows the same tour).
- If a number you read differs from the screen, the screen is right.
