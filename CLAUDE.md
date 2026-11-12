# Project Context

AI-powered productivity app for a small dev team (1 admin, up to ~5 users). Users plan tasks, run reusable personal processes, write daily productivity logs (prod logs), and view dashboards. Managers get read-only visibility into their team. AI assists with log entry, daily planning, and team summaries.

Environments:
- **Development:** owner's PC, Docker Compose, hot reload.
- **Staging (shared with teammates):** a small VM (assumed 2 GB RAM) exposed through an existing cloudflared tunnel. Images are built on the PC and transferred to the VM. Nothing is built on the VM.

---

## Stack

Use current stable versions of everything. Check the latest version at install time; do not rely on memory.

### Frontend
- React + TypeScript (strict mode) + Vite
- Tailwind CSS v4 via `@tailwindcss/vite`
- daisyUI 5 (requires Tailwind v4). Before writing UI code, read https://daisyui.com/llms.txt or https://daisyui.com/SKILL.md for current class names and theme syntax.
- React Router
- TanStack Query for server state
- React Hook Form + Zod for forms (`@hookform/resolvers` connects them)
- Recharts for charts
- `openapi-typescript` to generate TS types from the FastAPI OpenAPI schema
- ESLint + Prettier

### Backend
- Python + FastAPI
- `uv` for dependency management
- SQLAlchemy 2.0 (async, asyncpg driver) + Alembic
- Pydantic v2 + pydantic-settings
- `pwdlib[argon2]` for password hashing
- Authlib for Google OAuth
- pytest + httpx for tests
- ruff for lint and format

### Database
- PostgreSQL (Docker)

---

## Decisions and Reasons

| Decision | Reason |
|---|---|
| FastAPI backend | Owner's choice. Type sharing with the frontend is handled by generating TS types from OpenAPI. |
| PostgreSQL | Owner wants to learn it; one database is enough for this user count. |
| daisyUI 5 | Owner's choice for a more colorful UI; theme defined in CSS. |
| Server-side sessions in httpOnly cookies | Sessions can be revoked immediately when a user is deactivated; token is not readable by JavaScript. |
| Invite-only, links copied manually | Small known user group; avoids running an email service. |
| Separate tables for categories, statuses, priorities | Foreign keys guarantee a category column can only point at a category. |
| `team_id` snapshot on prod logs | Team history stays correct when a user changes teams. |
| LLM behind a provider interface, one adapter built | Provider undecided; extra adapters would be unused and untested. |
| Single production image (FastAPI serves the built frontend) | One container and one port behind cloudflared; lowest memory use on a 2 GB VM; same origin so no CORS. |
| Build on PC, transfer image to VM | VM is too small to build images. |

---

## Repository Structure

```
/
├── CLAUDE.md
├── PHASES.md
├── Makefile                  # dev, test, lint, migrate, seed, deploy targets
├── docker-compose.yml        # development
├── docker-compose.prod.yml   # staging VM
├── Dockerfile.prod           # multi-stage: build frontend, then Python runtime
├── .env.example
├── scripts/                  # deploy.sh, backup.sh, rollback.sh
├── backend/
│   ├── Dockerfile            # development
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/          # config, security, csrf, dependencies, errors, pagination
│   │   ├── db/            # engine, session, base
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── api/routers/   # thin: validate -> call service -> return
│   │   ├── services/      # business logic + RBAC-scoped queries
│   │   ├── ai/
│   │   │   ├── providers/ # LLMProvider protocol + adapter(s)
│   │   │   ├── features/  # nl_log_entry, daily_plan, team_summary
│   │   │   └── prompts/
│   │   └── scripts/       # seed.py
│   └── tests/
└── frontend/
    ├── Dockerfile            # development
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── index.css      # tailwind + daisyui + light and dark themes
        ├── api/           # fetch client, generated types, query hooks
        ├── components/    # shared UI
        ├── features/      # auth, admin, tasks, logs, processes, daily-plan, dashboard, ai
        ├── layouts/
        ├── routes/        # route config + role guards
        └── lib/
```

---

## Hard Rules

### General
- Only build what the current phase in PHASES.md asks for. Do not add features from later phases.
- Ask before adding any dependency not listed in this file.
- Never commit `.env` or `.env.prod`. Keep `.env.example` updated with every new variable.
- Every schema change goes through an Alembic migration. Never edit an applied migration.
- `make check` (ruff, eslint, type checks, backend tests) must pass before a phase is reported as done.

### Backend
- RBAC is enforced in the backend services layer. Hiding UI is not security.
- Every router endpoint (except login, invite acceptance, password reset acceptance, Google OAuth, health) requires `get_current_user`.
- Every query on user-owned data is scoped according to the permission matrix below. Write the scoping in services, not routers.
- Return 404 (not 403) when a user requests a specific resource they are not allowed to see.
- Dropdown values (categories, statuses, priorities, projects) are never hardcoded and never referenced by label in code. Use the `is_default` and `is_done` flags.
- Dropdown values are deactivated (`is_active = false`), never deleted. Inactive values are hidden from selection but still display on existing records.
- Users are never deleted, only deactivated.
- All LLM output is validated with a Pydantic schema before use. All IDs returned by the LLM are checked against the database and the caller's permissions. AI output is never saved without explicit user confirmation, except `ai_summaries` caching.

### Frontend
- TypeScript strict. No `any`.
- Use daisyUI component classes first, Tailwind utilities for adjustments.
- Use daisyUI semantic colors only (`bg-primary`, `text-base-content`, etc.). Do not use fixed Tailwind color classes like `text-gray-800` or `bg-orange-500`. This is what makes light and dark mode work.
- Always pair a color with its content color (`bg-accent text-accent-content`). Never use `text-secondary` (orange), `text-accent` (light blue) or status text colors (`text-info`, `text-success`, `text-warning`, `text-error`) on `base-100/200/300` surfaces in the light theme; they are too light to read. Use them as backgrounds with their `-content` color.
- Do not create `tailwind.config.js`. Tailwind v4 and daisyUI 5 are configured in CSS.
- API types come from the generated OpenAPI types. Do not hand-write duplicate response types.

---

## API Conventions

Established in Phase 0 and used by every endpoint.

- All routes under `/api`. The OpenAPI schema generated by FastAPI is the API contract.
- **Errors:** every error response has this shape:
  ```json
  { "error": { "code": "snake_case_code", "message": "Human readable", "fields": { "field_name": "message" } } }
  ```
  `fields` is present only for validation errors. Implement with global exception handlers, including for FastAPI's own validation errors.
- **Pagination:** every list endpoint accepts `limit` (default 50, max 200) and `offset`, and returns `{ "items": [...], "total": n, "limit": n, "offset": n }`.
- **Dates:** ISO 8601. `log_date`, `plan_date`, `due_date` are dates without time. Timestamps are UTC.
- **Logging:** structured logs to stdout with a request ID per request. Never log passwords, tokens, session IDs, or API keys.

---

## UI/UX

### Light and dark mode
- Two daisyUI themes: `brand-light` (default) and `brand-dark` (used when the system prefers dark).
- A theme toggle in the navbar. The choice is saved in `localStorage` and applied to `<html data-theme>` before first paint (inline script in `index.html`) to avoid a flash of the wrong theme. With no saved choice, follow the system preference.
- Every screen must be checked in both themes. Charts read their colors from daisyUI CSS variables and update when the theme changes.

### Mobile responsiveness
- Mobile-first. Every screen must work at 360px width with no horizontal page scroll.
- Navigation: daisyUI drawer; permanent sidebar from `lg` up (collapsible to an icon rail, choice saved in `localStorage`), slide-over drawer with a hamburger button below `lg`.
- Tables: below `md`, render rows as stacked cards. Wide tables that cannot be stacked scroll inside their own `overflow-x-auto` container.
- Forms: single column on mobile, two columns from `md` where it helps.
- Modals: `modal-bottom sm:modal-middle`.
- Touch targets at least 44px. Filters collapse into a "Filters" button on mobile.
- Charts use responsive containers and reduce tick density on small screens.

### General
- Empty, loading (daisyUI skeleton), and error states for every list and widget.
- Toasts for success and error. Confirmation modal before destructive actions.
- All form inputs have labels. Visible focus states (fields: primary-colored border highlight, not daisyUI's offset outline ring).

### Screens

| Route | Access | Purpose |
|---|---|---|
| `/login` | public | Username + password, Google |
| `/invite/:token` | public | Accept invite |
| `/reset-password/:token` | public | Set a new password |
| `/profile` | all | Change password, theme |
| `/today` | all | Daily plan, quick log, AI plan, AI log entry |
| `/tasks` | all | Own tasks |
| `/logs` | all | Own prod logs |
| `/processes`, `/processes/:id`, `/runs/:id` | all | Personal processes and runs |
| `/dashboard` | all | Personal dashboard |
| `/team/logs` | manager, admin | Read-only team logs (admin can edit) |
| `/team/dashboard` | manager, admin | Team dashboard, AI team summary |
| `/admin` | admin | Overview, Teams, Users, Invites, Dropdowns, Projects |

### Theme

Defined in `frontend/src/index.css`. Brand colors are final: Cloud Burst `#13294B` and orange `#FFA400`. All other colors are derived from them (dark mode uses a slate background, changed at the owner's request after Phase 3) (no stock Tailwind palette colors; yellow is used only for warning); status colors are light tones with dark navy content. Verify the syntax against current daisyUI 5 docs before using it.

```css
@import "tailwindcss";
@plugin "daisyui" {
  themes: false;
}

/*
 * Brand palette: Cloud Burst #13294B + orange #FFA400. Every other color is derived
 * from them (bases, accent and neutral share Cloud Burst's hue). Status colors are
 * light tones that all take dark navy text. The dark theme uses a mid-dark slate (a
 * desaturated Cloud Burst) rather than near-black navy.
 */

@plugin "daisyui/theme" {
  name: "brand-light";
  default: true;
  prefersdark: false;
  color-scheme: light;

  --color-base-100: #FCFDFF;
  --color-base-200: #F2F6FB;
  --color-base-300: #E2E8F2;
  --color-base-content: #14223A;

  --color-primary: #13294B;
  --color-primary-content: #FFFFFF;
  --color-secondary: #FFA400;
  --color-secondary-content: #13294B;
  --color-accent: #B3CCF2;
  --color-accent-content: #13294B;
  --color-neutral: #596475;
  --color-neutral-content: #FFFFFF;

  --color-info: #61C7CC;
  --color-info-content: #13294B;
  --color-success: #65D3A7;
  --color-success-content: #13294B;
  --color-warning: #F6D653;
  --color-warning-content: #13294B;
  --color-error: #EA6A6A;
  --color-error-content: #13294B;

  --radius-selector: 0.5rem;
  --radius-field: 0.5rem;
  --radius-box: 0.75rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 1;
  --noise: 0;
}

@plugin "daisyui/theme" {
  name: "brand-dark";
  default: false;
  prefersdark: true;
  color-scheme: dark;

  --color-base-100: #1E232B;
  --color-base-200: #191D24;
  --color-base-300: #14181E;
  --color-base-content: #E8ECF2;

  --color-primary: #77B0E7;
  --color-primary-content: #0B1A31;
  --color-secondary: #FFA400;
  --color-secondary-content: #0B1A31;
  --color-accent: #C2D6F2;
  --color-accent-content: #0B1A31;
  --color-neutral: #3A4452;
  --color-neutral-content: #F1F4F8;

  --color-info: #68CDD3;
  --color-info-content: #0B1A31;
  --color-success: #6CD9AE;
  --color-success-content: #0B1A31;
  --color-warning: #F3DB65;
  --color-warning-content: #0B1A31;
  --color-error: #F17776;
  --color-error-content: #0B1A31;

  --radius-selector: 0.5rem;
  --radius-field: 0.5rem;
  --radius-box: 0.75rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 1;
  --noise: 0;
}
```

---

## Roles and Permissions

Roles: `admin`, `manager`, `dev`. Global role stored on `users.role`. Each non-admin user belongs to exactly one team (`users.team_id`). Admin has `team_id = NULL`.

| Resource / Action | Admin | Manager | Dev |
|---|---|---|---|
| Manage teams, users, roles, invites, password reset links | CRUD | none | none |
| Manage categories, statuses, priorities, projects | CRUD | read | read |
| Own tasks, processes, process runs, daily plans | CRUD | CRUD | CRUD |
| Other users' tasks, processes, runs, daily plans | none | none | none |
| Own prod logs | CRUD | CRUD | CRUD |
| Other users' prod logs | CRUD, all teams | read, own team only | none |
| Personal dashboard | yes | yes | yes |
| Team dashboard | all teams | own team only | none |
| AI natural-language log entry | yes | yes | yes |
| AI daily plan | yes | yes | yes |
| AI team summary | all teams | own team only | none |

- "Own team" for prod logs means `prod_logs.team_id = manager.team_id` (the snapshot), not the author's current team.
- Deactivated users cannot log in and all their sessions are revoked immediately.

---

## Data Model

```
users
  id, username (unique), email (unique), password_hash (nullable),
  google_sub (nullable, unique), role, team_id (nullable FK teams),
  is_active, created_at, updated_at

teams
  id, name (unique), created_at

sessions
  id, user_id, token_hash, csrf_token, expires_at, created_at, revoked_at

invites
  id, email, role (manager | dev), team_id, token_hash,
  expires_at, accepted_at (nullable), created_by, created_at

password_resets
  id, user_id, token_hash, expires_at, used_at (nullable), created_by, created_at

categories
  id, label (unique), color (nullable), sort_order, is_active

statuses
  id, label (unique), color (nullable), sort_order, is_active,
  is_default (bool), is_done (bool)

priorities
  id, label (unique), color (nullable), sort_order, is_active, is_default (bool)

projects
  id, name (unique), description, is_active, created_at

tasks
  id, user_id, title, description (nullable),
  project_id (nullable), category_id (nullable),
  status_id (required), priority_id (required),
  due_date (nullable), completed_at (nullable),
  process_run_id (nullable), process_step_id (nullable),
  created_at, updated_at

prod_logs
  id, user_id, team_id (nullable, snapshot), task_id (nullable),
  log_date, title, description (nullable),
  project_id (nullable), category_id (required),
  hours_spent NUMERIC(4,2) CHECK (hours_spent > 0 AND hours_spent <= 24),
  created_at, updated_at, updated_by (FK users)

processes
  id, owner_id, name, description (nullable), is_active, created_at, updated_at

process_steps
  id, process_id, step_order, title, description (nullable),
  default_category_id (nullable), estimated_hours (nullable)

process_runs
  id, process_id, user_id, status (in_progress | completed | cancelled),
  started_at, completed_at (nullable)

daily_plans
  id, user_id, plan_date, ai_generated (bool), created_at
  UNIQUE (user_id, plan_date)

daily_plan_items
  id, daily_plan_id, task_id, item_order, suggested_hours (nullable), ai_reason (nullable)
  UNIQUE (daily_plan_id, task_id)

ai_summaries
  id, team_id, requested_by, period_start, period_end,
  summary_text, provider, model, created_at

ai_requests
  id, user_id, feature (nl_log_entry | daily_plan | team_summary),
  provider, model, input_tokens, output_tokens, success (bool), created_at
```

### Rules
- **Defaults:** exactly one active `statuses` row and one active `priorities` row have `is_default = true` (enforce with a partial unique index and in the service). New tasks without an explicit status/priority get the default. Code never looks up a status or priority by label.
- **Done:** a task is completed when its status has `is_done = true`; set `completed_at` then, clear it when moved back.
- **Prod logs hold no status or priority.** Those belong to tasks. A log stores its own `project_id` and `category_id`; when a task is selected they are pre-filled from the task and remain editable. The values on the log are what dashboards report.
- **Team snapshot:** `prod_logs.team_id` is set from the author's `team_id` at creation and never changes afterwards. Manager access and team dashboards filter on this column.
- **Daily hours:** the service rejects a log if the user's total `hours_spent` for that `log_date` would exceed 24.
- **Audit:** `prod_logs.updated_by` is set on every create and update. The UI shows "edited by {admin}" when `updated_by != user_id`.
- **Process runs:** starting a run copies each step into a task (`process_run_id`, `process_step_id`, default status, default priority, step's default category). Editing the template later does not change existing runs. A run completes when all its tasks are done. Cancelling a run keeps its tasks.

### Delete behaviour
| When this is deleted | Then |
|---|---|
| Task | `prod_logs.task_id` SET NULL; its `daily_plan_items` CASCADE |
| Process step | `tasks.process_step_id` SET NULL |
| Process | Allowed only if it has no runs; otherwise deactivate |
| Process run | Not deletable; cancel instead |
| Team | Allowed only if no users and no prod logs reference it (RESTRICT) |
| User | Never deleted; deactivate |
| Category, status, priority, project | Never deleted; deactivate. The default status/priority cannot be deactivated until another is made default. |
| Daily plan | Its items CASCADE |

---

## Auth

- Login: username + password, or Google OAuth.
- Invite-only. The admin creates an invite (email, role, team) and copies the generated link manually. Reject an invite for an email that already has a user or a pending invite.
- Invite link: `{FRONTEND_URL}/invite/{token}`. Store only the token hash. Single use, expires after `INVITE_TTL_HOURS`.
- Accepting an invite: user either sets username + password, or continues with Google. Email is fixed to the invite email.
- Google login is accepted only if Google reports `email_verified = true` AND the email matches an existing active user or a pending invite. Otherwise reject.
- If a password user later signs in with Google using the same verified email, link `google_sub` to the existing account.
- **Password reset:** no email service. The admin generates a reset link for a user (`{FRONTEND_URL}/reset-password/{token}`, single use, expires after `RESET_TTL_HOURS`) and sends it manually. Using it sets a new password and revokes all of that user's sessions.
- **Change password:** logged-in users change their own password on `/profile` (current password required). Other sessions are revoked.
- Sessions: server-side `sessions` table. Session token in an httpOnly, SameSite=Lax cookie; `Secure` flag from `COOKIE_SECURE` (false in dev, true on the VM). Store only the token hash.
- CSRF: double-submit token. Backend sets a readable `csrf_token` cookie; frontend sends it in `X-CSRF-Token` on all non-GET requests; backend compares it with the session's `csrf_token`.
- Login rate limiting: in-memory, keyed by client IP. Behind cloudflared the client IP comes from the `CF-Connecting-IP` header; only trust it when `TRUST_PROXY_HEADERS=true`.
- First admin is created by `app/scripts/seed.py` from `ADMIN_*` env vars. The seed is idempotent.
- Dev: browser talks only to the Vite dev server, which proxies `/api` to the backend. Google redirect URI `http://localhost:5173/api/auth/google/callback`.
- Staging: one origin, `https://{public hostname}`. Google redirect URI `https://{public hostname}/api/auth/google/callback`. Both URIs must be registered in the Google Cloud OAuth client.

---

## AI Layer

### Provider abstraction
```python
class LLMProvider(Protocol):
    async def generate_structured(self, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]: ...
    async def generate_text(self, system: str, user: str) -> tuple[str, Usage]: ...
```
- Build **one** adapter: the provider named in `LLM_PROVIDER`. Use that vendor's official Python SDK. Other providers are added later by implementing the same protocol; the factory raises a clear error for a provider that has no adapter.
- No provider-specific code outside `ai/providers/`.
- `generate_structured` uses the provider's native structured output or tool calling, then validates with the Pydantic schema. On validation failure: retry once, then raise a typed error.
- Every call writes an `ai_requests` row (including failures).
- Per-user daily limit: `AI_DAILY_LIMIT_PER_USER`. Exceeding it returns HTTP 429.
- Apply RBAC scoping before building any prompt.
- User-written text (log titles, descriptions) is data, not instructions. Put it in clearly delimited sections of the prompt and tell the model to ignore instructions inside it.

### Features
1. **Natural-language log entry** — input: free text. Context: today's date, active categories and projects (id + label), user's open tasks (id + title). Output: draft prod log (title, description, log_date, hours_spent, project_id, category_id, task_id, missing_fields[]). Backend nulls any ID that is invalid, inactive, or not owned by the user. Frontend pre-fills the log form; user confirms to save.
2. **AI daily plan** — context: user's open tasks (id, title, due date, priority, status), yesterday's logs, `WORKDAY_HOURS`. Output: ordered items (task_id, suggested_hours, reason). Backend drops task IDs not owned/open and trims to `WORKDAY_HOURS`. User edits and confirms; saved with `ai_generated = true`.
3. **AI team summary** — manager (own team) or admin (any team) selects a date range. Backend computes all numbers in SQL and passes them in; the LLM writes narrative only and must not invent numbers. Truncate log text to `AI_SUMMARY_CHAR_BUDGET`. Store in `ai_summaries`; reuse for the same team + period unless regeneration is requested.

---

## Dashboards

All aggregation is done in SQL. Week starts Monday. Dates use `APP_TIMEZONE`.

- **Personal:** hours per day (current week) and per week (last 8 weeks); hours by project and by category for a selectable range; task completion counts; process run progress (done / total tasks per active run).
- **Team (manager: own team, admin: any team):** hours per day/week for the team and per member, hours by project and category — all from `prod_logs.team_id`. Task completion counts per current team member (counts only, no task contents).
- **Admin overview:** team selector + team dashboard; counts of users, teams, pending invites; AI usage per user for the last 30 days.

---

## Non-Functional Requirements

- **Scale:** up to ~10 users. No caching layer, queue, or background workers.
- **Memory (staging VM, assumed 2 GB RAM):** app container limit 600 MB, one uvicorn worker; Postgres limit 512 MB with `shared_buffers=128MB`, `max_connections=20`; SQLAlchemy pool size 5.
- **Disk:** slim/alpine base images; Docker log rotation (10 MB x 3 files per container); keep only the current and previous app image on the VM.
- **Backups:** `pg_dump` before every deploy and daily via cron on the VM; keep the last 7.
- **Security:** HTTPS terminated by cloudflared; Postgres not published outside the Docker network; secrets only in env files on the machine that runs the containers; app container runs as a non-root user.
- **Privacy:** log content is sent to the configured LLM provider when AI features are used. State this in the README and on the AI inputs.

---

## Deployment Architecture (Staging VM)

```
PC:  docker build (Dockerfile.prod) -> docker save | gzip -> transfer -> VM
VM:  docker load -> backup DB -> alembic upgrade -> restart app container

Internet -> cloudflared tunnel -> http://localhost:{APP_PORT} -> app container
                                                        app container -> db container (internal network only)
```

- `Dockerfile.prod` is multi-stage: Node stage builds the frontend; Python slim stage installs the backend and copies the built frontend. FastAPI serves `/api/*` and the static frontend with an SPA fallback to `index.html`.
- Build for the VM's CPU architecture (`docker buildx build --platform ...`).
- Images are tagged with the git short SHA. Rollback means starting the previous tag.
- Uvicorn runs with proxy headers enabled so generated URLs use `https`.
- An existing app deployed the same way is the reference; its conventions win where they differ on transfer method, directory layout, port mapping, or script style. Details in PHASES.md, final phase.

---

## Environment Variables (.env.example)

```
# Postgres
POSTGRES_USER=app
POSTGRES_PASSWORD=change_me
POSTGRES_DB=app
DATABASE_URL=postgresql+asyncpg://app:change_me@db:5432/app

# App
SECRET_KEY=change_me
FRONTEND_URL=http://localhost:5173
APP_PORT=8000
SESSION_TTL_HOURS=168
COOKIE_SECURE=false
TRUST_PROXY_HEADERS=false
INVITE_TTL_HOURS=72
RESET_TTL_HOURS=24
APP_TIMEZONE=UTC
WORKDAY_HOURS=8
LOG_LEVEL=info

# Seed admin
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change_me

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:5173/api/auth/google/callback

# AI
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
AI_DAILY_LIMIT_PER_USER=50
AI_SUMMARY_CHAR_BUDGET=20000
```

Staging values that differ (in `.env.prod` on the VM only): `FRONTEND_URL=https://{public hostname}`, `GOOGLE_REDIRECT_URI=https://{public hostname}/api/auth/google/callback`, `COOKIE_SECURE=true`, `TRUST_PROXY_HEADERS=true`, strong `SECRET_KEY`, `POSTGRES_PASSWORD`, and `ADMIN_PASSWORD`.
