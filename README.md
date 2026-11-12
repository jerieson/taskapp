# Taskapp

AI-assisted productivity app for a small dev team: tasks, reusable personal processes,
daily productivity logs, dashboards, and read-only team visibility for managers.

- Project rules and architecture: [CLAUDE.md](CLAUDE.md)
- Build plan: [PHASES.md](PHASES.md)

## Stack

- **Backend:** Python 3.15, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic v2, uv
- **Frontend:** React 19, TypeScript (strict), Vite, Tailwind CSS v4, daisyUI 5, React Router,
  TanStack Query, React Hook Form + Zod
- **Database:** PostgreSQL 18

## Requirements

Only **Docker** (with Compose v2) and **make**. All tooling (uv, ruff, pytest, npm, eslint,
tsc) runs inside containers; nothing else needs to be installed on the host.

## Setup

```bash
cp .env.example .env     # or let `make dev` do it on first run
make dev                 # builds images and starts db, backend, frontend
make migrate             # in a second terminal: create the database schema
make seed                # create the admin (ADMIN_* in .env) and default dropdown values
```

Then open:

| URL | What |
|---|---|
| http://localhost:5173 | Frontend (Vite dev server, hot reload) |
| http://localhost:5173/api/health | Backend health check (through the Vite proxy) |
| http://localhost:5173/api/docs | Interactive API docs |

The browser only talks to the Vite dev server, which proxies `/api` to the backend container.
Neither the backend nor Postgres is published on the host; use `make psql` for a database shell.

Containers run as your host user (`HOST_UID`/`HOST_GID`, set automatically by the Makefile), so
files created inside them (lockfiles, generated types) are owned by you.

### Changing the database password

Postgres reads `POSTGRES_PASSWORD` only when it first creates the `pgdata` volume. If you change
it in `.env` later, `/api/health` returns `database_unavailable` (the db logs show
`password authentication failed`). Update the password inside the running database to match:

```bash
docker compose exec db sh -c 'printf "%s\n" "ALTER USER :\"u\" WITH PASSWORD :'"'"'pw'"'"';" | psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v u="$POSTGRES_USER" -v pw="$POSTGRES_PASSWORD"'
```

Or, if the dev data is disposable, run `docker compose down -v` to delete the volume. It is
recreated with the new password on the next `make dev`.

## Make commands

| Command | Description |
|---|---|
| `make dev` | Start the dev stack with hot reload (Ctrl+C to stop) |
| `make down` | Stop the dev stack |
| `make logs` | Follow logs of all services |
| `make build` | Rebuild dev images |
| `make test` | Run backend tests (pytest) |
| `make lint` | ruff check + ruff format check, eslint, prettier check |
| `make format` | Auto-fix and format backend and frontend code |
| `make typecheck` | TypeScript type check (`tsc -b`) |
| `make check` | lint + typecheck + test. Must pass before a phase is done |
| `make migrate` | Apply Alembic migrations (`alembic upgrade head`) |
| `make migration m="..."` | Autogenerate a new migration from model changes |
| `make seed` | Create the admin and default dropdown values (idempotent) |
| `make types` | Regenerate `frontend/src/api/schema.d.ts` from the FastAPI OpenAPI schema |
| `make lock` | Re-lock backend deps after editing `backend/pyproject.toml` |
| `make psql` | Open `psql` in the running db container |

Run `make` with no target to list them.

## Database and migrations

- Models live in `backend/app/models/`, one module per area. Every schema change goes through
  an Alembic migration (`backend/alembic/versions/`); never edit one that has been applied.
- After changing a model, run `make migration m="describe the change"`, then **review the
  generated file**. Autogenerate does not reliably pick up CHECK constraints, partial indexes,
  or server-side defaults; add those by hand. Then `make migrate`.
- `make test` fails if the models and migrations disagree, and also checks that every
  migration can be rolled back to an empty database and re-applied.
- Role and status columns are `VARCHAR` + `CHECK` constraints rather than native Postgres
  `ENUM` types, so adding a value is a constraint swap in a migration.
- `make seed` is safe to re-run: the admin is created only if no user has `ADMIN_USERNAME` or
  `ADMIN_EMAIL` (an existing password is never changed), and each dropdown table is filled
  only while it is empty.

## Tests

`make test` runs pytest in the backend container against a separate database named after
`POSTGRES_DB` with a `_test` suffix (for example `app_test`). It is dropped, recreated, and
migrated at the start of every run, so the dev database is never touched. Each test runs inside
a transaction that is rolled back afterwards. Factory helpers for common rows (users, teams,
tasks, logs, dropdown values) are in `backend/tests/factories.py`.

## Adding dependencies

- **Backend:** add the package to `backend/pyproject.toml`, run `make lock`, then `make build`.
- **Frontend:** add the package to `frontend/package.json`, update the lockfile with
  `docker compose run --rm --no-deps frontend npm install`, then `make dev` (the
  `--renew-anon-volumes` flag picks up the new `node_modules`).

Ask before adding anything not listed in CLAUDE.md.

## API conventions

- All routes live under `/api`. The OpenAPI schema (`/api/openapi.json`) is the contract.
- Every error has the shape
  `{"error": {"code": "snake_case", "message": "...", "fields": {...}}}`;
  `fields` appears only on validation errors: request validation (HTTP 422) and rule checks
  tied to a form field, such as a taken username (409) or a wrong current password (400).
- List endpoints take `limit` (default 50, max 200) and `offset` and return
  `{"items": [...], "total": n, "limit": n, "offset": n}`.
- Logs are JSON lines on stdout. Each request gets an `X-Request-ID` (returned in the response
  header and included in every log line for that request).

## Authentication

- **Sessions** are stored server-side (`sessions` table, only the token hash). The token
  travels in an httpOnly, SameSite=Lax `session` cookie; `Secure` is set when
  `COOKIE_SECURE=true`. Sessions expire after `SESSION_TTL_HOURS`. A deactivated user's
  sessions stop working immediately.
- **CSRF (double-submit):** every non-GET request must send the readable `csrf_token` cookie
  back in the `X-CSRF-Token` header. Before the first non-GET request without a session
  (login, invite acceptance, password reset), call `GET /api/auth/csrf` to get the cookie.
  Login replaces it with a token bound to the new session; logged-in requests must send
  that one.
- **Login rate limit:** 10 failed logins per client IP per 15 minutes (in memory, reset on
  restart). The IP comes from `CF-Connecting-IP` only when `TRUST_PROXY_HEADERS=true`.
- **Invites:** the admin creates one with `POST /api/admin/invites` and copies the
  `invite_url` from the response. The link is shown only once because only a hash of the
  token is stored. The invitee opens `{FRONTEND_URL}/invite/{token}` and either sets a
  username and password or continues with Google
  (`/api/auth/google/login?invite={token}`).
- **Password resets:** the admin calls `POST /api/admin/users/{id}/password-reset` and sends
  the returned `reset_url` manually. It can be used once, expires after `RESET_TTL_HOURS`,
  and using it revokes all of the user's sessions.
- **Google login** is off while `GOOGLE_CLIENT_ID` is empty. When enabled, it accepts only a
  verified Google email that matches an active user (and links the Google account) or a
  pending invite. The callback redirects to `/` on success or to `/login?error=<code>`.
- **First admin:** `make seed` creates it from the `ADMIN_*` variables.

## Frontend

```
frontend/src/
├── main.tsx          # providers, router, 401 handler
├── index.css         # Tailwind + daisyUI + brand-light / brand-dark themes
├── api/              # client.ts (fetch wrapper), auth.ts (query hooks), schema.d.ts (generated)
├── components/       # shared UI: PageHeader, DataTable, Pagination, ConfirmModal, toasts, ...
├── features/         # one folder per area (auth for now)
├── layouts/          # AppLayout (drawer + navbar), AuthLayout (public pages)
├── lib/              # theme store, form helpers
└── routes/           # route config, RequireAuth / RequireRole guards, sidebar links
```

- **API client** (`src/api/client.ts`): same-origin `fetch` with cookies. Non-GET requests send
  the `csrf_token` cookie in `X-CSRF-Token` (fetching it from `/api/auth/csrf` first if it is
  missing). Failed requests throw `ApiError` with `status`, `code`, `message` and `fields` from
  the standard error format. A 401 clears cached data and redirects to `/login?next=...`.
- **Types:** request and response types come from `src/api/schema.d.ts` (`Schemas['MeOut']`
  etc.). Run `make types` after any backend API change; never hand-write response types.
- **Server state:** TanStack Query. `useCurrentUser()` returns the logged-in user or `null`.
  4xx errors are not retried.
- **Routes:** public pages are `/login`, `/invite/:token` and `/reset-password/:token`.
  Everything else sits behind `RequireAuth`; `RequireRole` limits team and admin pages and
  shows "not found" to other roles. This only hides UI: the backend enforces permissions.
  Unbuilt pages use the shared `PlaceholderPage`.
- **Theme:** the navbar toggle switches light/dark, and `/profile` also offers "System". The
  choice is stored in `localStorage` (`taskapp-theme`). An inline script in `index.html`
  sets `<html data-theme>` before first paint, so the page never flashes the wrong theme.
  `useTheme()` re-renders on changes, including OS theme changes in System mode and changes
  made in other tabs.
- **Shared components:** `DataTable` shows a table from `md` up and stacked cards below it,
  and handles loading, error and empty states. Form fields (`InputField`, `SelectField`,
  `TextareaField`) accept React Hook Form's `register()` props, and `applyFieldErrors()`
  copies API field errors onto the form. Use `useToast()` for success/error toasts and
  `ConfirmModal` before destructive actions.
- **Colors:** use daisyUI semantic classes only, and pair each background with its
  `-content` color. Status colors are too light for text on base surfaces in the light theme,
  which is why form errors show base-content text next to an error-colored icon.
- **Touch targets:** on touch screens, buttons, inputs and menu items are at least 44px tall
  (rule at the end of `index.css`).
