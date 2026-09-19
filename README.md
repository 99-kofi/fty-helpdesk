# FTY Customer Experience Platform — HelpDesk

Omnichannel helpdesk for Free The Youth: Instagram, WhatsApp, Facebook, Email, and Website conversations flow through a single pipeline → unified customer identity → assignment engine → live agent workspace.

> **Architecture:** Channels → Integration Layer (adapters) → Webhook Gateway (validate → queue → 200 OK) → Message Worker → Conversation Engine → Assignment Engine → Automation/SLA → REST + WebSocket → Dashboard. Full spec in the workspace root conversation.

---

## Stack (No Docker required)

| Layer | Tech |
|-------|------|
| Backend | Python 3.12+ · FastAPI · SQLAlchemy 2.0 · SQLite (dev) → PostgreSQL (prod) · APScheduler (SLA) |
| Auth | JWT + bcrypt, roles `admin` / `manager` / `agent` |
| Frontend | React 18 + TypeScript + Vite — dark cinematic “Midnight Youth” theme |
| Realtime | WebSockets (`/ws/inbox`) + polling fallback + `GET /api/v1/conversations/updates` notifications |
| Channels | Meta Graph API (IG/FB), WhatsApp Cloud API, SMTP, embeddable `widget.js` |
| Storage | S3-compatible only when configured — local dev needs nothing |

---

## 1) Prerequisites

- **Node.js 18+** (`node --version`) and **Python 3.12+** (`python --version`)
- **Git**
- No Docker, no Postgres/Redis needed for local dev — SQLite + in-process queue are the defaults.

---

## 2) One-Time Setup

```powershell
# from repo root
git clone https://github.com/99-kofi/fty-helpdesk.git
cd fty-helpdesk

# Windows (PowerShell)
.\scripts\setup.ps1

# macOS / Linux
chmod +x scripts/*.sh   # if present, else run the steps below manually
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example backend/.env
cd frontend; npm install; cd ..
```

What `setup.ps1` does:
- Creates `backend/.venv` and installs `backend/requirements.txt`
- Copies `.env.example` → `backend/.env` (SQLite defaults)
- Runs `npm install` in `frontend`

---

## 3) Configure Channels (optional for local dev)

Edit `backend/.env`:

```ini
# Meta (Instagram/Facebook OAuth + webhooks)
META_APP_ID=928724823633091
META_APP_SECRET=your_app_secret      # never commit
META_VERIFY_TOKEN=any-random-string
META_OAUTH_REDIRECT_BASE=http://localhost:8000
FRONTEND_URL=http://localhost:5173

# WhatsApp + Email as needed
WHATSAPP_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=support@fty.local

# SLA (minutes/hours)
SLA_FIRST_RESPONSE_MINUTES=30
SLA_RESOLUTION_HOURS=24
```

For Meta OAuth, whitelist these in the Meta Dashboard → Facebook Login → Valid OAuth Redirect URIs:
- `http://localhost:8000/api/v1/channels/instagram/oauth/callback`
- `http://localhost:8000/api/v1/channels/facebook/oauth/callback`

Restart the backend after any `.env` change.

---

## 4) Run the System

**Fast (Windows):**
```powershell
.\scripts\start-dev.ps1
# opens backend on http://localhost:8000/docs and frontend on http://localhost:5173
```

**Manual (any OS):**

```powershell
# Terminal 1 — backend
cd backend
.\.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate           # macOS/Linux
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

```powershell
# Terminal 2 — frontend
cd frontend
npm run dev                           # http://localhost:5173
```

Build for production:
```powershell
cd frontend; npm run build   # outputs to frontend/dist
```

---

## 5) First Login & Roles

- Open `http://localhost:5173` — the login screen owns the full viewport (no sidebar until you sign in).
- Local development only: `ALLOW_DEFAULT_ADMIN_BOOTSTRAP=true` in `backend/.env` permits the first-run **`admin@fty.local` / `admin123`** account. This switch is disabled by default in deployments; provision an administrator through your deployment process instead.
- **Admin** sees all nav items: Inbox, Tickets, Customers, Knowledge, Automation, Analytics, Settings.
- **Workers** (any non-admin) see only **Inbox, Tickets, Customers**, each scoped to customers assigned to them. Knowledge/Automation/Analytics/Settings are admin-only (hidden + API 403).

Create worker logins:

1. As admin → **⚙ Settings → Teams & Workers → Create worker login** (name, email, password 6+ chars, role).
2. Workers sign in on the same Login page with those credentials.
3. Everyone sets their own **🟢 Available / 🟡 Away / 🔴 Offline** in Settings → My status. Offline removes them from auto-assignment.

---

## 6) Typical Daily Flow

1. **Connect a channel** (Settings → Channels): click **🔗 Connect Instagram/Facebook** → Meta Login → authorize, or paste a WhatsApp token, or embed the website `widget.js` snippet.
2. **Customer message arrives** → classified (sales/order/return/complaint/urgent), triaged to a team, auto-assigned to the least-loaded available worker (or left in **🆕 Unassigned** for manager review).
3. **Inbox:** Work top-down — 🔴 urgent first. Reply in-thread, move status as you go: `in_progress → waiting_for_customer → resolved`. Use **🤖 Suggest** for knowledge-base replies.
4. **SLA watchdog** (`POST /api/v1/automation/sla-check` or every `SLA_CHECK_MINUTES`) escalates unanswered customers and stale tickets to urgent + on-duty manager, exactly once per wait.
5. **Analytics** (📊) shows open/unassigned/urgent counts, avg first-response & resolution, 14-day volume, breakdowns by channel/team/category, and per-worker scorecards.

---

## 7) Website Widget

- Embed: copy the `widget.js` snippet from Settings → Channels → Web → `frontend/public/widget.js` equivalent or `GET /api/v1/web/widget.js`.
- Live demo: `http://localhost:8000/api/v1/web/widget-demo` — send a message and watch it land live in the admin Inbox (polling + WebSocket).
- Guest sessions are stored as `Customer` + `Conversation(channel=web)` + `CustomerIdentity(web-xxx)` → same assignment pipeline as every other channel.

---

## 8) Automation & Knowledge

- **🤖 Automation:** create rules as `IF contains/intent/channel/confidence/priority → THEN set_priority/team/assign/escalate`. Toggle or delete; automation runs after the assignment engine on `message_created` / `ticket_created`.
- **📚 Knowledge:** search, category filter, full CRUD (admin) — the same approved answers power AI suggestions.
- **Tickets & Customers:** admin creates; workers act only on assigned items (status updates, filing tickets on their own conversations).

---

## 9) Fresh Dev Reset

Clears test/dev rows but keeps code, `backend/.env` credentials, and logo assets:

```powershell
# stop backend/frontend first (Ctrl+C), then from repo root:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reset-dev.ps1
.\scripts\start-dev.ps1
# log in again — admin auto-seeds
```

Manual alternative: delete `backend/fty.db` (plus `fty.db-journal/wal/shm`) and restart.

---

## 10) Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q              # 40 tests: smoke, phase2, oauth, assignment, phase3, users, access
# or: python -m pytest test_assignment.py -q -v
```

Frontend type-check + build:
```powershell
cd frontend
npx tsc --noEmit
npm run build
```

---

## 11) Deploy on Vercel

This Vercel configuration deploys the React frontend only. All application data is stored in the signed-in browser's `localStorage`; no database, API environment variables, or server function is deployed.

1. Import `99-kofi/fty-helpdesk` in Vercel. In **Project Settings → General → Root Directory**, set the directory to **`frontend`** and save. This is required: it prevents Vercel from discovering the repository's Python API.
2. Redeploy using `frontend/vercel.json`. Do not set `VITE_API_URL`.
3. Open `https://<your-project>.vercel.app` and log in with **`admin@fty.local` / `admin123`**. Change or create local worker logins from Settings.

The app is fully browser-local: clearing browser site data clears the helpdesk data; data does not sync across browsers, devices, or team members; channel webhooks, OAuth, outbound email, and live shared inbox features require a separately hosted backend and are intentionally unavailable in this deployment.

## 12) Production Without Containers

- **Backend:** native Python runtime (Render / Railway / Fly / VM with `uvicorn` + process manager). Set `DATABASE_URL` to managed Postgres (Neon/Supabase/RDS) and `REDIS_URL` if available.
- **Frontend:** static hosting (Vercel / Netlify) — `npm run build` → deploy `frontend/dist`.
- **Storage:** S3-compatible (R2/S3) via `S3_*` vars; secrets stay in `backend/.env` and are Fernet-encrypted in DB (`TOKEN_ENCRYPTION_KEY` or derived from `JWT_SECRET`).

---

## 12) Security Notes

- Webhook secrets & OAuth tokens live in `backend/.env` and DB as `enc:` ciphertext — never in the frontend.
- JWT roles enforced server-side (`core/security.py` + `require_role`). Hiding nav is not the only protection.
- Assignment history + audit logs on every mutation.
- `backend/.env` is gitignored (`# never commit`) — set secrets per environment.

---

## 13) Project Structure

```
backend/app/
  core/        # config, db, security, vault
  models/      # users, customers, conversations, tickets, teams, history, knowledge, automation
  schemas/     # Pydantic
  api/v1/      # REST: auth/users, conversations, tickets, customers, channels, webchat, oauth, teams, knowledge, automation, analytics
  webhooks/    # /webhooks/instagram|whatsapp|facebook|email (validate → queue → 200 OK)
  services/    # identity_resolution, conversation_engine, assignment, automation, sla, ai_stub
  workers/     # queues (Redis or in-process), message pipeline
  channels/    # adapters: base + instagram/whatsapp/facebook/email, outbound sending
frontend/src/
  pages/ Inbox, Tickets, Customers, Knowledge, Automation, Analytics, Settings, Login
  components/ LogoStage, ui, styles
  api/ client, realtime (WebSocket + polling)
scripts/ setup.ps1, start-dev.ps1, reset-dev.ps1, isolate-logo.py
```

---

## 14) Troubleshooting

| Symptom | Fix |
|--------|-----|
| `META_APP_ID is not configured` | Set it in `backend/.env` and restart backend |
| `exchange_failed` on Connect | Add the matching `META_APP_SECRET`, whitelist callback URIs, keep `META_OAUTH_REDIRECT_BASE=http://localhost:8000` locally |
| `No Page with linked Instagram` | Switch IG to Business/Creator → Facebook Page → Settings → Linked accounts → Connect IG |
| Web messages not in inbox | Restart backend (fix landed in `webchat.py`), hard refresh, Inbox chip now defaults to **📥 All** — check **🆕 Unassigned** / filter `Channel=web` |
| `.env` not picked up | `app/core/config.py` loads `backend/.env` by absolute path — any cwd is fine, but restart after editing |
| Port in use | Kill old `uvicorn` / `vite` processes or change `--port` |

---

Built from WAIT Technologies · FTY HelpDesk — “Support that moves at the speed of youth.”
