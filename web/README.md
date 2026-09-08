# Researcher workspace frontend

React + TypeScript UI for the local Research Hub server. Six pages share project
records and task state. English and Traditional Chinese dictionaries are checked
for parity. Vite outputs the complete application to
`src/research_hub/workspace_static/` with `/app/` asset URLs; the Python runtime
does not need Node or a remote CDN.

## Development

Run `npm ci`, `npm run typecheck`, `npm test`, and `npm run build` here. `npm run dev`
starts Vite on localhost and proxies `/api` to `http://127.0.0.1:8765`. Normal
mutations require the CSRF metadata injected by the Python server, so use the
built application from that server for complete integration testing. Human
decisions additionally require its interactive local approval session.

## Accessibility and performance

- Semantic navigation and headings, a skip link, associated visible form labels,
  keyboard controls, visible focus, live error/success messages, and reduced motion.
- Responsive single-column pages and mobile navigation; no hover-only controls.
- Source links allow HTTP(S) only. Authorization tokens stay in the document and
  request headers; no local storage, URL tokens, remote fonts, telemetry, or auto-run.
- Plain fetch with abortable project requests. Polling runs every three seconds
  only for running tasks, stops on errors, and cancels on unmount or project switch.
- One small application bundle; no chart, icon, routing, or state management packages.
- Automated checks cover API errors, token scope, locale parity, task state meaning,
  retained input, source links, and the question/task/output workflows. Parent
  integration testing owns real server checks, screen-reader testing, and visual
  checks at mobile size and 200% zoom.

Preparing a task never runs an agent. Imported output remains awaiting human review.
The server's `completed` task status denotes human acceptance.

The Manuscript page binds the external manuscript state and shows writing-adapter
checks and change-impact reports. Audit findings remain visible even when a check
returns `ok: false`; no check grants semantic acceptance. The Review & delivery
page prepares a local proposal bundle from accepted candidate files, records a
separate human decision, and exposes explicit execution and receipt reconciliation.
A local ZIP does not authorize publication or certify every manuscript release
check. Receipt paths identify local files and are not download links.
