# Build Phases

Paste one phase at a time into Claude Code. Review, test in the browser (light mode, dark mode, and a 360px-wide viewport), and commit before starting the next phase. Every phase assumes CLAUDE.md has been read.

Every phase ends with the same closing steps, so they are not repeated in each prompt:
- Run `make check` and fix failures.
- Regenerate the frontend API types if the backend API changed.
- Stop, summarize what was built, and list anything that deviates from CLAUDE.md.

| Phase | Scope |
|---|---|
| 0 | Scaffolding, conventions, tooling |
| 1 | Database models, migrations, seed |
| 2 | Auth and invites (backend) |
| 3 | Frontend foundation, auth UI, themes |
| 4 | Admin: teams, users, invites, password resets |
| 5 | Admin: dropdowns and projects |
| 6 | Tasks |
| 7 | Prod logs and team logs |
| 8 | Daily plan (manual) |
| 9 | Personal processes |
| 10 | Personal dashboard |
| 11 | Team and admin dashboards |
| 12 | AI provider layer |
| 13 | AI natural-language log entry |
| 14 | Linked dropdowns + import of the sheet's Data tab |
| 15 | Prod log fields: activity, work set-up, O&M project, planned/actual hours |
| 16 | Weekly planning: Friday deadline, planned/unplanned, lock, /today, copy plan, status (daily plan removed) |
| 17 | Export prod logs to CSV (sheet format) |
| 18 | Support dictionary (replaces personal processes) |
| 19 | AI multi-row log entry and planning (replaces AI daily plan) |
| 20 | AI team summary |
| 21 | Hardening |
| 22 | Deployment to the staging VM |

Phases 14 to 19 were added after Phase 13 to match the team's real productivity-log spreadsheet and support dictionary; they rework parts of Phases 7 to 10 and 13.

Phase 22 depends only on Phases 0 to 3. It can be run early to confirm that login, cookies, and Google OAuth work behind cloudflared, then re-run for later releases.

---

## Phase 0 — Scaffolding, Conventions, Tooling

```
Read CLAUDE.md fully. Then do Phase 0 only.

Goal: running project skeleton with the API conventions and tooling in place.

Build:
1. Repository structure from CLAUDE.md.
2. backend: FastAPI app managed with uv.
   - GET /api/health returning {"status": "ok"} plus a DB connectivity check.
   - Global exception handlers producing the error format in "API Conventions" (including FastAPI validation errors).
   - Shared pagination params and response model.
   - Structured logging to stdout with a request ID.
3. frontend: Vite + React + TypeScript (strict). Tailwind v4 via @tailwindcss/vite and daisyUI 5 in src/index.css with both themes from CLAUDE.md (verify syntax against current daisyUI docs first). One temporary page showing buttons, badges, a card, and an alert in primary, secondary, accent, and neutral, with a temporary theme switch, so both themes can be checked.
4. Vite proxy: /api -> backend service.
5. docker-compose.yml (development): db (postgres, named volume, healthcheck), backend (uvicorn --reload, source mounted), frontend (vite dev, source mounted).
6. Tooling: ruff (lint + format), ESLint + Prettier, tsc type check.
7. Makefile targets: dev, test, lint, check (lint + types + tests), migrate, seed, types (regenerate OpenAPI TS types).
8. .env.example exactly as in CLAUDE.md. .gitignore covering .env and .env.prod.
9. README.md: setup and the Makefile commands.

Acceptance:
- docker compose up starts all three services without errors.
- http://localhost:5173 shows the theme test page; colors are correct in light and dark.
- http://localhost:5173/api/health returns ok through the proxy.
- A request to an unknown /api route returns the standard error format.
- make check passes.
```

---

## Phase 1 — Database Models, Migrations, Seed

```
Do Phase 1 only.

Goal: complete database schema and seed data.

Build:
1. SQLAlchemy 2.0 async models for every table in the CLAUDE.md data model, with all constraints, unique keys, foreign keys, the ON DELETE behaviour from the "Delete behaviour" table, and indexes on foreign keys plus (user_id, log_date) and (team_id, log_date) on prod_logs and (user_id, plan_date) on daily_plans.
2. Partial unique indexes so only one active row can have is_default = true in statuses and in priorities.
3. Alembic configured for async, one initial migration. Review it and fix anything autogenerate missed (CHECK constraints, enums, partial indexes).
4. app/scripts/seed.py (idempotent):
   - Admin user from ADMIN_* env vars.
   - Statuses: To Do (is_default), In Progress, Blocked, Done (is_done).
   - Priorities: Low, Medium (is_default), High, Urgent.
   - Categories: Development, Bug Fix, Code Review, Meeting, Documentation, Research.
   These labels appear only in the seed, nowhere else in the code.
5. Test setup: separate test database, async fixtures, rollback per test, factory helpers for users/teams/tasks/logs.

Acceptance:
- make migrate applies cleanly on an empty database.
- make seed twice creates no duplicates.
- Tests prove: hours_spent CHECK rejects 0 and 25; a second active default status is rejected; deleting a task nulls prod_logs.task_id; deleting a team with users fails.
```

---

## Phase 2 — Authentication and Invites (Backend)

```
Do Phase 2 only. Backend only.

Goal: auth as described in the Auth section of CLAUDE.md.

Build:
1. Password hashing with pwdlib[argon2].
2. Sessions: create, validate, revoke. httpOnly SameSite=Lax cookie, Secure flag from COOKIE_SECURE.
3. CSRF double-submit protection on all non-GET requests.
4. Dependencies: get_current_user (rejects inactive users), require_role(*roles).
5. Endpoints:
   - POST /api/auth/login
   - POST /api/auth/logout
   - GET  /api/auth/me
   - POST /api/auth/change-password (current + new; revokes other sessions)
   - GET  /api/auth/google/login (optional ?invite={token})
   - GET  /api/auth/google/callback
   - POST /api/admin/invites, GET /api/admin/invites, DELETE /api/admin/invites/{id}
   - GET  /api/invites/{token} (public)
   - POST /api/invites/{token}/accept (public)
   - POST /api/admin/users/{id}/password-reset (admin; returns reset URL)
   - GET  /api/password-resets/{token} (public; valid or not)
   - POST /api/password-resets/{token} (public; sets password, revokes all sessions)
6. Google rules exactly as in CLAUDE.md.
7. Login rate limiting, in-memory, keyed by client IP; read CF-Connecting-IP only when TRUST_PROXY_HEADERS=true.

Acceptance (all as automated tests):
- Login success and failure; inactive user blocked; logout revokes the session.
- Missing or wrong CSRF token rejected on non-GET requests.
- Invite: create, accept, reuse rejected, expired rejected, duplicate email rejected, non-admin cannot create.
- Password reset: single use, expiry enforced, sessions revoked after use, non-admin cannot generate.
- Change password requires the correct current password.
- Google callback (OAuth exchange mocked): unknown email rejected, unverified email rejected, invite email accepted, existing account linked.
```

---

## Phase 3 — Frontend Foundation, Auth UI, Themes

```
Do Phase 3 only.

Goal: authenticated, themed, responsive app shell. Follow the UI/UX section of CLAUDE.md.

Build:
1. API client (fetch wrapper): sends credentials, attaches X-CSRF-Token on non-GET requests, parses the standard error format, redirects to /login on 401.
2. Generated TS types from OpenAPI (make types).
3. TanStack Query setup; useCurrentUser hook.
4. Theme: remove the temporary switch from Phase 0. Add the navbar theme toggle, localStorage persistence, system-preference fallback, and the inline script in index.html that sets data-theme before first paint.
5. Pages: /login, /invite/:token, /reset-password/:token, /profile (change password, theme choice).
6. Route guards: RequireAuth, RequireRole.
7. App layout: daisyUI drawer + navbar. Sidebar permanent from lg, slide-over below lg. Links shown per role. Pages not built yet use one shared placeholder component. User menu with profile and logout.
8. Shared components used by later phases: PageHeader, DataTable that renders stacked cards below md, Pagination, ConfirmModal, Toast provider, EmptyState, Skeleton loaders, FormField wrappers.

Acceptance:
- Admin logs in with seeded credentials and sees admin links.
- Invite acceptance and password reset work end to end from links created via the API.
- Logged-out users are redirected to /login.
- Theme toggle works, survives reload, and shows no flash of the wrong theme.
- Every page built so far is usable at 360px width in both themes with no horizontal page scroll.
```

---

## Phase 4 — Admin: Teams, Users, Invites, Password Resets

```
Do Phase 4 only.

Backend (admin only):
1. Teams: list, create, rename, delete (blocked when users or prod logs reference the team).
2. Users: paginated list with filters (team, role, active); update role and team; activate/deactivate. Admin cannot deactivate or demote themselves. Deactivation revokes sessions.

Frontend (/admin, tabs: Overview placeholder, Teams, Users, Invites):
1. Teams tab: list, create, rename, delete with confirmation.
2. Users tab: table/cards with filters, edit role and team, activate/deactivate with confirmation, "Generate password reset link" with copy button.
3. Invites tab: create form (email, role, team), list with status (pending/accepted/expired), "Copy link" button, revoke pending invites.

Acceptance:
- Tests: manager and dev get 403/404 on every admin endpoint; self-deactivate and self-demote rejected; team delete blocked when in use.
- In the browser: create a team, invite a manager and a dev into it, accept both invites in private windows, deactivate one and confirm their session ends.
- All three tabs usable at 360px in both themes.
```

---

## Phase 5 — Admin: Dropdowns and Projects

```
Do Phase 5 only.

Backend:
1. Categories, statuses, priorities, projects: list (all roles get active rows; admin can request inactive too), create, update, activate/deactivate. No delete endpoints.
2. Statuses and priorities: set default (moves the flag atomically). The default cannot be deactivated. Statuses: toggle is_done; at least one active is_done status must exist.
3. Reorder endpoint (sort_order) for categories, statuses, priorities.

Frontend (/admin, add tabs: Dropdowns, Projects):
1. Dropdowns tab with sub-tabs Categories, Statuses, Priorities: add, rename, color picker, reorder, toggle active, set default, toggle "counts as done" for statuses.
2. Projects tab: add, edit, toggle active.
3. A shared hook/component for selects that loads active options and can still display an inactive value on an existing record.

Acceptance:
- Tests: non-admin cannot write; default cannot be deactivated; setting a new default leaves exactly one; last active done-status cannot be removed.
- A search of the codebase finds no status, priority, or category label outside the seed script.
- Tabs usable at 360px in both themes.
```

---

## Phase 6 — Tasks

```
Do Phase 6 only.

Backend:
1. Tasks: CRUD for own tasks only. Paginated list with filters: status, priority, project, category, due date range, open/completed, belongs to a process run.
2. New tasks get the default status and priority when none is given.
3. Moving to a status with is_done sets completed_at; moving away clears it.
4. Only active dropdown values and projects are accepted on create; on update, an already-assigned inactive value may stay.

Frontend (/tasks):
1. Table (cards below md) with filters, sorting by due date and priority, pagination.
2. Create/edit modal. Quick status change from the list.
3. Overdue tasks visually marked using semantic colors.

Acceptance:
- Tests: a user cannot read, update, or delete another user's task (404), including admin; completed_at set and cleared correctly; inactive values rejected on create.
- Usable at 360px in both themes.
```

---

## Phase 7 — Prod Logs and Team Logs

```
Do Phase 7 only.

Backend:
1. Prod logs: CRUD for own logs. Paginated list with filters: date range, project, category, task.
2. On create: team_id set from the author's current team; updated_by set to the caller. On update: updated_by set to the caller; team_id never changes.
3. Optional task_id must belong to the log's author. When a task is given and project/category are omitted, copy them from the task.
4. Reject a log when the author's total hours for that log_date would exceed 24.
5. Team access:
   - GET /api/teams/{team_id}/logs — manager for own team (filter on prod_logs.team_id), admin for any team. Filters: member, date range, project, category.
   - Admin can update and delete any log through the normal log endpoints. Managers cannot write to others' logs.

Frontend:
1. /logs: list grouped by date with a daily hours total, create/edit form with optional task link, filters.
2. /team/logs (manager, admin): read-only list with filters; admin gets a team selector plus edit and delete. Show "edited by {name}" when updated_by differs from the author.

Acceptance:
- Tests: dev cannot access any team endpoint; manager cannot access another team; manager PUT/DELETE on a team member's log fails; admin edit sets updated_by; daily 24-hour cap enforced; a user who changes teams keeps old logs under the old team_id and the old team's manager still sees them while the new team's manager does not.
- Usable at 360px in both themes.
```

---

## Phase 8 — Daily Plan (Manual)

```
Do Phase 8 only.

Backend:
1. Get or create the plan for a date (own plans only).
2. Add, remove, and reorder items; set suggested_hours. Items must be the user's own open tasks; no duplicates in a plan.
3. Replace-all endpoint (used later by the AI plan) that swaps a plan's items in one transaction.

Frontend (/today):
1. Today's plan: ordered list with up/down reorder (drag is optional), hours per item, total hours against WORKDAY_HOURS.
2. Add tasks from a searchable picker of open tasks.
3. "Log work" on an item opens the log form pre-filled with that task.
4. Mark a task done from the plan.
5. Date navigation to view other days.

Acceptance:
- Tests: cannot add another user's task; cannot add a completed task; duplicate rejected; another user's plan returns 404.
- Usable at 360px in both themes.
```

---

## Phase 9 — Personal Processes

```
Do Phase 9 only.

Backend:
1. Processes: CRUD, owner only. Delete allowed only with no runs; otherwise deactivate.
2. Steps: create, update, delete, reorder within an owned process.
3. POST /api/processes/{id}/runs: creates a run and one task per step (title, description, step's default category, default status, default priority, process_run_id, process_step_id). Optional due date applied to all generated tasks. One transaction.
4. A run completes automatically when all its tasks are done; reopening a task reopens the run. Manual cancel keeps the tasks.
5. Run detail with progress (done / total).

Frontend:
1. /processes: list, create/edit with an ordered step editor.
2. /processes/:id: steps, "Start run", list of runs with progress bars.
3. /runs/:id: the run's tasks with status changes.

Acceptance:
- Tests: ownership (404 for others, including admin); editing or deleting template steps does not alter existing run tasks; auto-complete and reopen; process with runs cannot be deleted.
- Usable at 360px in both themes.
```

---

## Phase 10 — Personal Dashboard

```
Do Phase 10 only.

Backend (own data only, SQL aggregation, APP_TIMEZONE, Monday week start):
1. Hours per day for a given week.
2. Hours per week for the last 8 weeks.
3. Hours by project and hours by category for a date range.
4. Task completion counts for a date range (completed, open, overdue).
5. Active process runs with progress.

Frontend (/dashboard):
1. Recharts: bar chart (hours per day), line chart (hours per week), charts by project and by category, stat cards for task counts, progress list for active runs.
2. Shared date range picker.
3. Chart colors read from daisyUI CSS variables and update on theme change.
4. Responsive: single column on mobile, grid from md.

Acceptance:
- Tests: aggregations return correct numbers for seeded fixtures, including a week boundary; a user never receives another user's numbers.
- Charts readable in both themes and at 360px.
```

---

## Phase 11 — Team and Admin Dashboards

```
Do Phase 11 only.

Backend:
1. Team endpoints (manager own team, admin any team): hours per day/week for the team and per member, hours by project and category — all filtered on prod_logs.team_id. Task completion counts per current team member (counts only).
2. Admin overview: counts of users, teams, pending invites; AI usage per user for the last 30 days from ai_requests (empty until Phase 12).

Frontend:
1. /team/dashboard: team charts, per-member comparison, date range picker; admin gets a team selector.
2. /admin Overview tab: stat cards and the AI usage table.

Acceptance:
- Tests: dev forbidden; manager other team forbidden; numbers follow the team_id snapshot after a user changes teams; no task titles or descriptions appear in any team response.
- Usable at 360px in both themes.
```

---

## Phase 12 — AI Provider Layer

```
Do Phase 12 only.

Goal: LLM infrastructure, no user-facing feature yet.

Before coding: read LLM_PROVIDER from .env. If it is empty, stop and ask which provider to use. Then read that provider's current official Python SDK docs; do not rely on memory for method names or model names.

Build:
1. LLMProvider protocol and Usage type as in CLAUDE.md.
2. One adapter, for the provider in LLM_PROVIDER, using its native structured output or tool calling.
3. Factory selecting the adapter. Clear startup error if the API key is missing or the provider has no adapter.
4. Shared wrapper: Pydantic validation, one retry on validation failure, typed errors, ai_requests logging (success and failure), per-user daily limit returning 429.
5. FakeProvider for tests. No real API calls in tests.
6. README section: how to add another provider.

Acceptance:
- Tests: validation retry then typed error; limit returns 429; every call writes an ai_requests row.
- A manual script (not part of tests) makes one real structured call and prints the validated result and token usage.
```

---

## Phase 13 — AI Natural-Language Log Entry

```
Do Phase 13 only.

Backend:
1. POST /api/ai/log-draft { text } -> draft log (not saved).
2. Context and output as specified in CLAUDE.md. Post-process: null any ID that is invalid, inactive, or not owned by the user; null hours_spent if out of range; fill missing_fields.
3. System prompt in ai/prompts/: use only provided IDs, leave fields null rather than guess, treat the user's text as data.

Frontend:
1. On /logs and /today: an input "Describe what you worked on". Submitting opens the normal log form pre-filled with the draft, missing fields highlighted. Saving uses the normal create endpoint.
2. Loading and error states, including the 429 message. A short note that the text is sent to the AI provider.

Acceptance:
- Tests with FakeProvider: invalid IDs stripped; another user's task ID stripped; out-of-range hours nulled.
- Manual check with the real provider: five varied sentences produce sensible drafts.
- Usable at 360px in both themes.
```

---

## Phase 14 — Linked Dropdowns and Data Tab Import

```
Do Phase 14 only. Read "Data Model" (categories, projects, project_categories, activity_groups, activities, activity_group_members, om_projects, work_setups) and the "Data tab import" rule in CLAUDE.md first. Sample file: the owner's "Productivity Log - Data" CSV (ask for the path).

Before coding: print the mapping you derive from the sample CSV (category -> projects, project -> activity group, group -> activities, O&M projects) and ask the owner to confirm it.

Backend:
1. Migration: the tables above; categories.requires_om_project; projects.activity_group_id. Seed work set-ups Remote (default), On-Site, Out-of-Office.
2. Admin CRUD for activity groups, activities, O&M projects, work set-ups (same endpoints and rules as categories: activate/deactivate, reorder, single default for work set-ups). Activity group membership: PUT /api/activity-groups/{id}/activities { activity_ids } (ordered). Project: category links and activity group on create/update.
3. Read endpoints for the log form: GET /api/log-options returns active categories, projects (with category_ids and activity_group_id), activity groups with their activity ids, activities, O&M projects, work set-ups, in one response.
4. POST /api/admin/import/data-tab (multipart CSV): idempotent import as described in CLAUDE.md; returns created/linked counts and unrecognised columns.

Frontend:
1. Admin > Dropdowns: tabs for Activities, Activity groups (member picker with order), O&M projects, Work set-ups; Categories get the "Has O&M project" flag; Projects get categories (multi-select) and activity group.
2. Admin > Dropdowns: "Import from sheet" (upload, then show the result counts).

Acceptance:
- Tests: import of the sample is idempotent (second run creates nothing); case-insensitive matching; shared activities linked to several groups; existing values reused, never deleted.
- Usable at 360px in both themes.
```

---

## Phase 15 — Prod Log Fields

```
Do Phase 15 only. Read the prod_logs model and its Rules ("Linked dropdowns", "Planned and actual") in CLAUDE.md.

Backend:
1. prod_logs: add work_setup_id (required), activity_id (required), om_project_id, is_planned, planned_hours, deviation_reason; hours_spent and title become nullable; CHECK planned or actual present. Backfill existing rows: a "General" activity, the default work set-up, is_planned = false.
2. Create/update validate the linked-dropdown rules (project in category, activity in project's group, O&M project only for requires_om_project categories); project required for new rows. For now is_planned = true whenever planned_hours is given (Phase 16 replaces this with the deadline rule). 24-hour caps apply separately to actual and planned totals per day.
3. List/team endpoints and filters return and accept the new fields (activity_id filter).
4. Dashboards: actual hours only; add hours by activity (personal, team); personal daily chart also returns planned hours.
5. Phase 13 AI draft: extend with activity_id, work_setup_id, om_project_id, planned_hours, validated with the same linked rules.

Frontend:
1. Log form in the sheet's order: Date, Work set-up, Planned hours, Actual hours, Category, Project (filtered by category), Activity (filtered by project), Project (For O&M) (only when the category needs it), Task, Note, Remarks, Reason for deviation (when actual differs from planned). Changing category clears an invalid project; changing project clears an invalid activity.
2. Log lists: activity as the main label, project / category, planned vs actual, work set-up and "Unplanned" badges; day totals for actual and planned.
3. Dashboard: hours by activity; planned vs actual on the daily chart.

Acceptance:
- Tests: backfill; each linked-dropdown rule; separate caps; dashboards ignore rows without actual.
- Usable at 360px in both themes.
```

---

## Phase 16 — Weekly Planning

```
Do Phase 16 only. Read "Planning deadline", "Planned and actual", "Reminder and status" and "Copy a plan" in CLAUDE.md.

Backend:
1. PLAN_DEADLINE_TIME setting (Friday, APP_TIMEZONE). One helper computes a date's week (Monday to Friday), its deadline and whether it is open; used everywhere.
2. is_planned set by the server on create from the deadline; planned_hours changes and planned-row deletes rejected in locked weeks (422 `week_locked`) for non-admins. Admin can set is_planned.
3. Remove daily plans: drop daily_plans and daily_plan_items (migration), endpoints, services, tests.
4. POST /api/logs/copy { from_date | from_week, to_dates[] } into open weeks only; skips over-cap days and inactive values; reports skipped days. One transaction.
5. GET /api/planning/status?week= : the caller's own status; GET /api/teams/{id}/planning/status?week= for manager (own team) / admin: per member planned hours per day and has_planned.

Frontend:
1. /today: the day's rows (?date=), planned vs actual and totals against WORKDAY_HOURS; inline actual hours, "Actual = planned", edit, delete; "Add unplanned activity". Locked weeks show planned hours read-only.
2. "Plan next week": a week view (Mon to Fri) of next week's planned rows with "Copy this week's plan" and "Copy a day to the week"; deadline countdown.
3. Reminder banner (Friday until the deadline, when next week has no planned rows) on /today and /logs.
4. Team dashboard: "Next week's plan" card per member (manager own team, admin any).
5. Remove the old daily plan UI.

Acceptance:
- Tests: deadline edges (Friday 18:29 vs 18:30 in APP_TIMEZONE); is_planned not settable by users; locked planned hours and deletes; admin override; copy only into open weeks; status scoping.
- Usable at 360px in both themes.
```

---

## Phase 17 — Export Prod Logs

```
Do Phase 17 only. Read "Export" in CLAUDE.md.

Backend:
1. GET /api/logs/export?date_from&date_to[&user_id] -> text/csv attachment, filename "<username>_<from>_<to>_productivity_log.csv". Own logs for everyone; manager: members of own team (rows with that team snapshot); admin: any user; others 404. Columns and formats exactly as in CLAUDE.md. Excel-safe (UTF-8 with BOM; values starting with = + - @ prefixed with ').

Frontend:
1. /logs: "Export CSV" with a month picker (default this month) or custom range.
2. /team/logs: export for the selected member.

Acceptance:
- Tests: column order and formats; scoping; formula-injection escaping.
- Usable at 360px in both themes.
```

---

## Phase 18 — Support Dictionary (replaces personal processes)

```
Do Phase 18 only.

Backend:
1. Remove processes: drop processes, process_steps, process_runs and tasks.process_run_id / process_step_id (migration), their endpoints, services, tests, and the run-progress dashboard data.
2. support_types lookup (admin CRUD like categories). Seed Concern, Inquiry, Bug, Request, Data Modification, Transport.
3. support_entries CRUD: everyone lists and reads all; any user creates; author or admin updates and activates/deactivates. List: search q (concern, cause, resolution, notes, project, module, sub-module; case-insensitive), filters type_id, project, module, include_inactive; paginated, newest first. GET /api/support/facets returns distinct projects and modules for filter and autocomplete.
4. POST /api/admin/support/import (multipart CSV, the team's format): maps Type labels to support_types (case-insensitive, creating missing ones), trims values, skips blank-concern rows, returns created/skipped counts with row-level errors. Author column is kept as text in notes when it does not match a username; created_by = the importing admin.

Frontend:
1. /support: search box, filters (type, project, module, show inactive), result cards (type badge, project / module / sub-module, concern; expand for cause, resolution, notes, query in a monospace block with a Copy button).
2. /support/:id detail and create/edit form (project and module with suggestions from facets). Deactivate/activate with confirmation.
3. Admin: Support import (upload, preview counts, result).
4. Remove /processes and /runs routes, nav entries and the run-progress widget.

Acceptance:
- Tests: a user can edit their own entry; editing someone else's entry returns 403 `not_author` (it is readable, so not 404); admin can edit any; search and filters; import of the sample CSV.
- Usable at 360px in both themes.
```

---

## Phase 19 — AI Multi-Row Log Entry and Planning (replaces AI daily plan)

```
Do Phase 19 only.

Backend:
1. POST /api/ai/log-draft returns { rows: [...] } (max 20 rows). Each row as in CLAUDE.md, AI Layer, feature 1. Context adds activities, work set-ups and the weekday of today; the prompt explains planned (future or "I will") vs actual ("I did") rows, date ranges ("Tuesday to Friday"), and "per day" vs "per week" hours (per week is split evenly across the days and stated in missing_fields if ambiguous).
2. Post-process per row as in Phase 13 and the linked-dropdown rules, plus: drop rows with no date; cap row count; a row in a locked week cannot carry planned hours (if its date is today or earlier, planned becomes actual; otherwise the hours are cleared and listed in missing_fields).
3. Use the existing POST /api/logs/bulk { rows[] } (built in the log UX rework before Phase 18: all or none, same checks as single create, field errors keyed rows.N.field).

Frontend:
1. The AI card opens a review table/cards of draft rows: edit each row inline (same fields as the log form), remove rows, missing fields highlighted; "Save N rows" uses the bulk endpoint.
2. Single-row drafts may still open the normal log form.

Acceptance:
- Tests with FakeProvider: multi-row output validated per row; invalid and inactive values stripped; saving the drafts through bulk create is all-or-nothing with caps enforced.
- Manual check with the real provider: "I will work on the workforce API next week Tuesday to Friday 4 hrs a day" gives four planned rows; "next week 4 hrs a day" gives five (Monday to Friday); five other varied sentences give sensible drafts.
- Usable at 360px in both themes.
```

---

## Phase 20 — AI Team Summary

```
Do Phase 20 only.

Backend:
1. POST /api/ai/team-summary { team_id, period_start, period_end, regenerate }.
2. Permission check before loading any data: manager own team, admin any team.
3. Numbers computed in SQL from prod_logs.team_id and passed to the prompt. The prompt asks for narrative only (overview, per-member highlights, blockers mentioned in logs), forbids producing or changing numbers, and marks log text as data.
4. Truncate log text to AI_SUMMARY_CHAR_BUDGET, most recent first.
5. Cache in ai_summaries; return the cached row for the same team + period unless regenerate = true.
6. GET /api/ai/team-summaries?team_id= (paginated).

Frontend (/team/dashboard):
1. Period selector + "Generate summary". Database numbers shown in stat cards next to the AI narrative (rendered as markdown). Show generated time and model. "Regenerate" button.
2. List of past summaries.

Acceptance:
- Tests: dev forbidden; manager other team forbidden; cache reused; regenerate creates a new row; char budget respected.
- Usable at 360px in both themes.
```

---

## Phase 21 — Hardening

```
Do Phase 21 only.

Build:
1. One parametrised permission test covering every row of the CLAUDE.md permission matrix for admin, manager, and dev.
2. Check every list endpoint is paginated and every error uses the standard format.
3. UI pass on every screen in the Screens table: light mode, dark mode, 360px width, empty/loading/error states, labels, focus states, no light-colored (orange, accent, status) text on base surfaces.
4. README: full setup, Google OAuth client setup (both redirect URIs), AI provider configuration, privacy note about LLM providers.
5. Remove dead code, the placeholder component if unused, and unused dependencies.

Acceptance:
- make check passes.
- A written checklist in the summary showing each screen checked in light, dark, and mobile.
- A list of anything left unfinished.
```

---

## Phase 22 — Deployment to the Staging VM

```
Do Phase 22 only. Read the "Deployment Architecture" and "Non-Functional Requirements" sections of CLAUDE.md first.

Context: the staging VM is small (assumed 2 GB RAM) and is exposed through an existing cloudflared tunnel. Images are built on this PC and transferred to the VM. Nothing is built on the VM.

Step 1 — Study the reference app (do this before writing any file):
- Reference app path on this PC: <REFERENCE_APP_PATH>
- Read its Dockerfile(s), compose file(s), deploy scripts, and env handling.
- Report: how the image is built and tagged, how it is transferred, where it lives on the VM, how the container is restarted, which port cloudflared points at, and how env vars are supplied.
- Where the reference differs from the plan below on transfer method, VM directory layout, port mapping, or script style, follow the reference. For any other difference, ask me.

Step 2 — Ask me for (do not guess):
- VM SSH user and host, target directory on the VM.
- The port cloudflared forwards to for this app, and the public hostname.
- VM CPU architecture (or get it with: ssh <vm> uname -m) and free disk space (df -h).
- Whether cloudflared runs on the VM host or in Docker.

Step 3 — Production image:
1. Dockerfile.prod, multi-stage:
   - Stage 1 (node): install frontend deps, build static files.
   - Stage 2 (python slim): install backend deps with uv (no dev deps), copy backend, copy built frontend to a static directory, run as a non-root user.
2. FastAPI serves the static directory when it exists: /api/* to the routers, real files as-is, every other path returns index.html (SPA fallback). Hashed assets get long cache headers; index.html gets no-cache.
3. Start command: uvicorn, one worker, proxy headers enabled, listening on APP_PORT.
4. .dockerignore so node_modules, .venv, tests, .env files, and .git stay out of the image.

Step 4 — docker-compose.prod.yml (runs on the VM):
1. app: image tag from an APP_IMAGE variable, env_file .env.prod, port bound to match how the reference app is reached by cloudflared, mem_limit 600m, restart unless-stopped, healthcheck on /api/health, depends on db healthy.
2. db: postgres alpine, named volume, not published to the host, mem_limit 512m, started with shared_buffers=128MB, max_connections=20, work_mem=4MB, restart unless-stopped, healthcheck.
3. Log rotation on both: json-file, max-size 10m, max-file 3.
4. SQLAlchemy pool size 5, max overflow 5 (make these env-configurable if they are not already).

Step 5 — Scripts (match the reference app's script language and style):
1. scripts/deploy.sh, run from the PC:
   a. Refuse to run with uncommitted changes. Tag = git short SHA.
   b. make check.
   c. docker buildx build for the VM's platform using Dockerfile.prod.
   d. docker save | gzip, transfer to the VM, docker load there (or the reference app's method).
   e. On the VM: run scripts/backup.sh.
   f. On the VM: run alembic upgrade head in a one-off app container using the new image.
   g. On the VM: set APP_IMAGE to the new tag and docker compose -f docker-compose.prod.yml up -d.
   h. Wait for the healthcheck; on failure print the app logs and exit non-zero.
   i. Remove app images on the VM other than the new and the previous tag; delete the transferred archive.
2. scripts/backup.sh, run on the VM: pg_dump | gzip into a backups directory, keep the last 7.
3. scripts/rollback.sh: start the previous image tag. Print a warning that a migration applied by the failed release is not reverted automatically and may need alembic downgrade or a restore from the pre-deploy backup.

Step 6 — First-time setup runbook (write into README, do not execute without my confirmation):
1. Create the target directory on the VM; copy docker-compose.prod.yml and scripts/backup.sh.
2. Create .env.prod on the VM from .env.example with the staging values listed in CLAUDE.md. Generate strong SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD.
3. Run the deploy script once, then run the seed in a one-off container.
4. Point the cloudflared ingress for the public hostname at the app port (same way as the reference app).
5. Add https://{public hostname}/api/auth/google/callback to the Google Cloud OAuth client.
6. Add a daily cron entry on the VM for scripts/backup.sh.
7. Check: docker stats shows both containers under their memory limits; df -h shows free disk.

Step 7 — README sections: routine deploy, rollback, restore from backup, viewing logs, rotating secrets.

Acceptance:
- The production image builds on the PC for the VM's architecture and runs locally with docker-compose.prod.yml: the frontend loads from the app container, a deep link such as /tasks reloads correctly, /api/health is ok.
- scripts/deploy.sh completes against the VM and the public hostname serves the app over HTTPS.
- Password login works on the public hostname, the session cookie is Secure and httpOnly, and non-GET requests pass CSRF.
- Google login works on the public hostname.
- A second deploy keeps existing data, and a backup file exists from before it.
- rollback.sh returns the app to the previous image.
- After deploy, only two app image tags remain on the VM.
```
