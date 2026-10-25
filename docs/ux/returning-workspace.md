# Returning to saved Workspace work

Scope: small, reversible `/app/` Overview change, based on `f4fd94d6`.
This does not implement the complete import/read/summary journey or integration setup.

## Pain-point brief (source-backed; usability benefit remains a hypothesis)

1. **Who / when:** a researcher returning to an existing selected Workspace
   project, locating unfinished tasks and checking what was accepted or bundled.
2. **Current workflow:** Overview displays five task records, then Review &
   delivery displays every task and local bundle action. The researcher must
   locate the desired task again and inspect delivery receipts separately.
3. **Friction:** the old Overview slices the creation-ordered task list before
   reversing it. A recently updated older-created task can be absent. No update
   timestamp or local receipt is shown there; the generic link selects no task.
4. **Evidence:** `web/src/Pages.tsx` Overview, `workspace/tasks.py:TaskService.list`
   (rowid descending, with stored `updated_at`), `workspace/core.py:snapshot`
   (project-scoped tasks/actions), `workspace/actions.py:execute/reconcile` (local
   ZIP and durable receipt). Component regression tests reproduce omission and
   absence of targeted navigation. No observed human task timing is claimed.
5. **Work potentially removed:** one manual task re-location after moving from
   Overview to Review; reading stored bundle state no longer requires opening
   Review. Baseline: Overview → Review → locate task/receipt. Candidate:
   Overview → chosen task, or read receipt on Overview. These are source/DOM
   observations, not proof of fewer user errors or faster completion.
6. **New cost:** more text in the existing activity panel, up to five tasks and
   five actions. No setup, new authorization, background requests or persistent
   session state. Existing human acceptance and delivery confirmations remain.
7. **Non-users:** cold projects retain the existing Literature source-record /
   metadata-search path and project creation. Registration is not a PDF reader
   or evidence that AI/humans read full text. Existing task creation remains.
8. **Acceptance:** newest updated older-created task is visible; timestamp
   absence is explicit; targeted Review focus and Overview return retain the
   selected project; removed targets do not select another task; project switch
   and newer hash navigation invalidate old focus. Acceptance history stays
   separate from bundle outcomes. No replay, new mutations or provider probes.

## Inventory and truth boundaries

- `workspace/server.py` serves `/app/` and its bundled assets. Legacy dashboard
  is separate (`dashboard/`); it is not silently redirected or removed.
- `App.tsx` holds selected project in memory and page in the URL hash. Backend
  `Workspace.list_projects` sorts by ID, not recency. No persisted last-visited
  project, reading position or session resume is available in this contract.
- `Task.updated_at` is saved activity time, not page-view time or provider-health
  freshness. Overview sorts a copy of tasks, then limits to five; unknown times
  follow known times, preserving API order among ties.
- All task states are historical/current server projections, not execution
  capability promises. Overview never decides artifact eligibility. Existing
  Review / Delivery gates remain authoritative, including the separate
  freshness fix when integrated; this branch does not duplicate that work.
- The task count covers unfinished/revisit states including failed and blocked;
  completed count is acceptance history, not proof every candidate remains valid.
- Actions are shown in API creation order, explicitly not a latest-delivery
  timeline. Receipts have path/hash/verified_at; opening Overview does not
  reconcile or re-verify them. Missing action/receipt is not failure or success.
- `ActionService` currently creates only local ZIP files. No Zotero, Obsidian or
  NotebookLM destination outcome is supplied here. External delivery remains
  unknown and cannot demote accepted content.
- Existing readiness visibility remains unchanged. New key forms, session login,
  integration probes, backend ledgers and source/vault scans are out of scope.

## Verification boundaries

Synthetic DOM/component tests and TypeScript/build checks are distinct from
browser observation and user acceptance. Chromium in the supplied VM was already
blocked by the execution environment; no sandbox workaround is attempted here.
Real keyboard/zoom/layout, native Back/Forward history, Windows and Muse/user
usability review remain required. No live provider, private vault or paid model
is used. Publication, integration with other candidates, merge and release are
outside this VM-only candidate.
