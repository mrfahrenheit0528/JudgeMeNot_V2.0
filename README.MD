<p align="center">
  <h1 align="center">⚖️ JudgeMeNot V2.0</h1>
  <p align="center">
    <strong>A Blockchain-Secured, Real-Time Event Scoring & Tabulation System</strong>
  </p>
  <p align="center">
    Built with Flask · SQLAlchemy · Socket.IO · ReportLab · SHA-256 Ledger
  </p>
</p>

---

## 📖 Table of Contents

1. [Introduction](#-introduction)
2. [The Problem](#-the-problem)
3. [Key Features](#-key-features)
4. [Technology Stack](#-technology-stack)
5. [Architecture Overview](#-architecture-overview)
6. [Data Layer](#-data-layer)
7. [Emerging Tech — Decentralized Score Ledger](#-emerging-tech--decentralized-score-ledger)
8. [Authentication & Role-Based Access](#-authentication--role-based-access)
9. [Core User Flows](#-core-user-flows)
10. [Navigation Structure](#-navigation-structure)
11. [Configuration & Settings Panel](#-configuration--settings-panel)
12. [Error Handling & Input Validation](#-error-handling--input-validation)
13. [Analytics & Dashboard Metrics](#-analytics--dashboard-metrics)
14. [Export — PDF Reports](#-export--pdf-reports)
15. [Installation & Setup](#-installation--setup)
16. [Admin Guide](#-admin-guide)
17. [Judge / Tabulator Guide](#-judge--tabulator-guide)
18. [Project Structure](#-project-structure)
19. [License](#-license)

---

## 🌟 Introduction

**JudgeMeNot V2.0** is a full-stack web application designed to digitize and secure the scoring process for competitive events — from beauty pageants to academic quiz bees. It replaces error-prone paper-based tabulation with a real-time, multi-device system where judges score from their own devices while administrators maintain full control and visibility over every data point.

What sets V2.0 apart is its **blockchain-inspired Score Ledger** — every score submitted is cryptographically chained into an immutable ledger, making post-submission tampering detectable and auditable. This is not a gimmick; it directly solves the trust problem inherent in subjective scoring events.

The system supports **two fundamentally different event types** within a single unified platform:

| Event Type | Example | Scoring Model |
|---|---|---|
| **Score-Based** | Pageants, talent shows | Judges assign decimal scores per criteria; weighted averages produce rankings |
| **Point-Based** | Quiz bees, olympiads | Tabulators mark correct/wrong per question; points accumulate per round |

---

## 🎯 The Problem

Manual event scoring suffers from several critical issues:

1. **Human Calculation Error** — Weighted averages, cross-judge normalization, and multi-round accumulation are done by hand, leading to frequent arithmetic mistakes.
2. **Tampering & Bias** — Paper scoresheets can be altered after submission. There is no verifiable chain of custody for scores.
3. **Slow Tabulation** — Results take minutes to hours as tabulators manually collect and compute sheets, causing awkward delays during live events.
4. **No Audit Trail** — When disputes arise, there is no timestamped record of who submitted what and when.
5. **Tiebreaker Chaos** — Multi-way ties at qualification boundaries require ad-hoc sudden-death rounds that are difficult to manage on paper.

**JudgeMeNot V2.0** eliminates all five problems through real-time digital scoring, automated weighted computation, cryptographic integrity verification, full audit logging, and an automated tiebreaker engine.

---

## ✨ Key Features

- **Dual Event Engine** — Score-Based (pageants) and Point-Based (quiz bees) in one platform
- **Real-Time Scoring** — Judges score from any device; results update instantly via Socket.IO
- **Blockchain Score Ledger** — SHA-256 chained, tamper-evident record of every score
- **Automated Tiebreaker Engine** — Detects ties at qualification boundaries and auto-generates Clincher rounds
- **PDF Export** — Official results with signatory blocks, per-segment matrices, and overall rankings
- **Role-Based Access Control** — Admin, Judge, Tabulator, and Viewer roles with route-level enforcement
- **Live Leaderboard** — Public-facing, auto-refreshing scoreboard for audiences
- **Full Audit Log** — Every login, score submission, user creation, and event change is recorded
- **Dark/Light Theme** — System-wide toggle with persistent preference
- **QR Code Device Pairing** — Settings panel generates a QR code for judges to connect to the server
- **Animated UI** — Particle canvas backdrop, glassmorphism widgets, and aurora gradients

---

## 🛠 Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.x, Flask 3.1 |
| **Database** | MySQL (via XAMPP), SQLAlchemy ORM |
| **Real-Time** | Flask-SocketIO, Eventlet |
| **Frontend** | Jinja2 templates, Bootstrap 5, Font Awesome 6 |
| **Cryptography** | SHA-256 (hashlib), bcrypt (password hashing) |
| **PDF Generation** | ReportLab |
| **Environment** | python-dotenv, PyMySQL |

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                   Browser Clients               │
│  (Admin Dashboard, Judge Scoring, Leaderboard)  │
└────────────┬────────────────────┬───────────────┘
             │ HTTP/REST          │ WebSocket
             ▼                    ▼
┌─────────────────────────────────────────────────┐
│              Flask Application (main.py)        │
│  ┌──────────┬──────────┬──────────┬───────────┐ │
│  │ auth_bp  │ events_bp│ judge_bp │ scores_bp │ │
│  │ admin_bp │leaderb_bp│          │           │ │
│  └──────────┴──────────┴──────────┴───────────┘ │
│  ┌──────────────────────────────────────────┐   │
│  │         services.py (Business Logic)     │   │
│  │   Ledger · Ranking · Dashboard Calcs     │   │
│  └──────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────┐   │
│  │     Socket.IO (ledger_node.js client)    │   │
│  └──────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────┘
                     │ SQLAlchemy ORM
                     ▼
┌─────────────────────────────────────────────────┐
│          MySQL Database (judgemenot_v2_db)       │
│  users · events · segments · criteria ·         │
│  contestants · scores · score_ledger ·          │
│  audit_logs · event_judges · judge_progress     │
└─────────────────────────────────────────────────┘
```

The app follows a **Blueprint-based modular architecture**. Each functional area (auth, events, judges, scores, admin, leaderboard) is an independent Flask Blueprint with its own routes, registered in `main.py`.

---

## 💾 Data Layer

The database is defined via SQLAlchemy ORM models in `webapp/python/models.py`. The schema auto-creates on startup via `Base.metadata.create_all()`, and the database itself is auto-created if it doesn't exist.

### Entity-Relationship Summary

| Model | Purpose |
|---|---|
| `User` | Stores all accounts (admin, judge, tabulator, viewer) with bcrypt-hashed passwords |
| `Event` | Top-level container; defines event type (Score-Based / Point-Based) and status |
| `Segment` | Rounds within an event (e.g., "Swimwear", "Easy Round"); holds weight/points config |
| `Criteria` | Pageant-only; sub-dimensions within a segment (e.g., "Poise" at 60% weight) |
| `Contestant` | Participants; for quiz bees, each contestant is linked 1:1 to a tabulator |
| `Score` | The core data record — links contestant + judge + segment + criteria/question |
| `ScoreLedger` | Blockchain — each row is a block with `block_index`, `data_snapshot`, `previous_hash`, `current_hash` |
| `AuditLog` | Timestamped record of every significant action (login, score, CRUD) |
| `EventJudge` | Many-to-many assignment of judges to events; tracks chairman designation |
| `JudgeProgress` | Tracks whether a judge has finished/locked their scores for a segment |

### Key Relationships

- `Event` → has many `Segment` → has many `Criteria` (pageant) or questions (quiz bee)
- `Event` → has many `Contestant` (each optionally linked to a tabulator via `assigned_judge_id`)
- `Score` references `Contestant`, `User` (judge), `Segment`, and optionally `Criteria`
- `ScoreLedger` references `Score` and stores a JSON snapshot of the score data at write time

---

## 🔗 Emerging Tech — Decentralized Score Ledger

The standout technical feature is a **blockchain-inspired integrity ledger** built directly into the scoring pipeline.

### How It Works

1. **On every score submission**, `append_to_ledger()` in `services.py` creates a new `ScoreLedger` block containing:
   - A JSON snapshot of the score data
   - The `previous_hash` (linking to the prior block)
   - A `current_hash` computed via SHA-256 over the block content
2. **The block is broadcast** to all connected clients via Socket.IO (`new_ledger_block` event)
3. **Each browser runs a witness node** (`ledger_node.js`) that independently validates chain continuity
4. **Verification is two-layered** (`verify_ledger_integrity()`):
   - **Layer 1 — Chain Check**: Walks all blocks verifying hash links
   - **Layer 2 — Data Check**: Cross-references each ledger snapshot against the actual `scores` table to detect direct DB tampering

### Ledger Explorer

Admins can browse the full chain at `/admin/ledger` — a visual blockchain explorer showing every block, its hash, the score it recorded, and whether integrity is intact. Compromised blocks are highlighted in red.

### Local Ledger Node Widget

A glassmorphic floating widget (bottom-left corner) shows real-time ledger status on admin screens:
- Block count witnessed
- Truncated latest hash
- Integrity badge (Verified ✅ / Broken! 🔴)
- Pulse animation on each new block

---

## 🔐 Authentication & Role-Based Access

### Authentication Flow

1. User submits credentials at `/login`
2. `authenticate_user()` queries the database and verifies the bcrypt hash
3. On success, user data is stored in the Flask `session` and an `AuditLog` entry is created
4. On failure, a generic error message is shown (no username enumeration)

### Password Security

- Passwords are hashed with **bcrypt** (salt auto-generated per password)
- Plaintext passwords are never stored or logged

### Roles

| Role | Permissions |
|---|---|
| `admin` | Full CRUD on events, segments, criteria, contestants, users. Access to control panel, scores, audit logs, ledger explorer, PDF export. Can launch/pause events and toggle segments. |
| `judge` | Score pageant events they are assigned to. View their own dashboard. Lock/submit scores per segment. |
| `tabulator` | Score quiz bee events for their assigned team. View leaderboards. |
| `viewer` | Read-only access (limited routes) |

### Route Protection

Every protected route uses the `@require_role()` decorator:

```python
@require_role(['admin'])          # Admin only
@require_role(['judge', 'tabulator'])  # Judges and tabulators
@require_role()                   # Any authenticated user
```

Unauthorized access attempts are logged to console and redirected with a flash message.

---

## 🔄 Core User Flows

### Flow 1 — Pageant Scoring (Score-Based)

```
Admin creates event (Score-Based)
  → Adds segments (Swimwear 50%, Evening Gown 50%)
  → Adds criteria per segment (Poise 60%, Beauty 40%)
  → Adds contestants (with optional photos)
  → Assigns judges (designates chairman)
  → Launches event → activates first segment

Judge opens dashboard → sees assigned events
  → Enters scoring page for active segment
  → Scores each contestant on each criteria (0–max_score)
  → Scores auto-save via AJAX + ledger broadcast
  → Locks segment when finished (irreversible)

Admin activates next segment → reveals scores
  → Generates PDF export → announces results
```

### Flow 2 — Quiz Bee Scoring (Point-Based)

```
Admin creates event (Point-Based, scoring_type: hybrid/cumulative/per_round)
  → Adds rounds (Easy Round: 5Q × 1pt, Hard Round: 5Q × 3pt)
  → Adds teams + assigns each to a tabulator (1:1)
  → Launches event → activates first round

Tabulator opens dashboard → enters their team's scoring page
  → Marks each question correct/wrong
  → Submits → scores broadcast to ledger

Admin views Mission Control (live polling)
  → Sees all teams' progress and cumulative scores
  → Clicks "Evaluate" when round is complete
    → System checks for ties at qualification boundary
    → If tie: auto-generates Clincher round (sudden death)
    → If clean: advances qualifiers to next round

Cycle repeats until Final Round → results are official
```

### Flow 3 — Tiebreaker Resolution (Automated)

```
Admin evaluates a round with qualifying_count = 5
  → 4th and 5th place are tied with 6th place
  → System creates "Tie Breaker (Round Name)" with 1 question
  → Only tied contestants participate
  → Tabulators score the tie-breaker question
  → Admin re-evaluates
    → If still tied: "Clincher 2" is created (repeat)
    → If resolved: winners advance, next round auto-starts
```

---

## 🗺 Navigation Structure

### Navbar (role-dependent)

| Element | Visible To | Route |
|---|---|---|
| **JudgeMeNot** (brand) | All | `/` (dashboard) |
| **Control Panel** | Admin | `/control-panel` → redirects to latest event manage page |
| **Leaderboards** | Tabulator, Public | `/leaderboard/` |
| **Theme Toggle** | All | Client-side dark/light switch |
| **User Dropdown** | Authenticated | System settings, Logout |
| **Login Button** | Unauthenticated | `/login` |

### Admin Sidebar (within admin pages)

| Page | Route | Description |
|---|---|---|
| Events | `/admin/events` | List all events with status |
| Users | `/admin/users` | CRUD user accounts |
| Participants | `/events/participants_directory` | Cross-event contestant directory |
| Scores | `/admin/scores/` | Score analytics hub |
| Audit Logs | `/admin/logs` | Recent 150 system actions |
| System Settings | `/admin/settings` | QR code, connection info |
| Ledger Explorer | `/admin/ledger` | Full blockchain viewer |

---

## ⚙ Configuration & Settings Panel

### Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `db_username` | `root` | MySQL username |
| `db_pass` | (empty) | MySQL password |
| `db_host` | `localhost` | MySQL host |

### Settings Panel (`/admin/settings`)

The settings page provides:

- **Server Connection URL** — Displays the LAN IP and port for network access
- **QR Code** — Auto-generated QR code (via `qrcode` library) that judges can scan to connect their devices to the server
- Accessible to admins, judges, and tabulators

### Application Config

- `SECRET_KEY` is set in the Flask config (defaults to `'dev'` — should be changed for production)
- Database name is hardcoded as `judgemenot_v2_db`
- Server runs on `0.0.0.0:5000` for LAN accessibility

---

## 🛡 Error Handling & Input Validation

### Server-Side Validation

| Area | Validation |
|---|---|
| **Login** | Checks user existence, active status, and password hash match. Returns generic error to prevent enumeration. |
| **User Creation** | Rejects duplicate usernames before insert. |
| **User Editing** | Prevents renaming to an existing username. Blocks deletion of the primary admin account. |
| **Score Submission** | Validates criteria existence. Checks `JudgeProgress.is_submitted` to prevent scoring on locked segments. |
| **Quiz Bee Access** | Verifies tabulator is assigned to a team, the segment is active, and the team qualifies for the round. |
| **Pageant Access** | Filters contestants server-side via `is_contestant_allowed()` — eliminated contestants are never sent to the client. |
| **Event Status** | Judges cannot score if event is not `Ongoing` or segment is not `is_active`. |

### Error Recovery

- All database operations use `try/finally` blocks ensuring `db.close()` is always called
- Score submission uses `db.rollback()` on failure to prevent partial writes
- Socket.IO broadcast failures are silently caught to prevent scoring failures
- The database auto-creates on startup if it doesn't exist
- Flash messages provide user-friendly feedback for all error conditions

### Confirmation Modals

Destructive actions (delete user, delete contestant, etc.) require a custom confirmation modal where the user must type `CONFIRM` — preventing accidental data loss.

---

## 📊 Analytics & Dashboard Metrics

### Admin Dashboard (`/`)

The admin dashboard displays:

- **Active Events Count** — Number of events with status `Ongoing`
- **Total Participants** — Global contestant count across all events
- **Global Scoring Progress** — Percentage of expected scores that have been submitted (across all events)
- **Per-Event Progress Bars** — Individual completion percentage for the 3 most recent events
- **Recent Events List** — Quick access to the most recently active events

### Score Analytics (`/admin/scores/<event_id>`)

For Score-Based events, the detail page computes:

- **Top Scorer** — Contestant with the highest weighted total
- **Lowest Scorer** — Contestant with the lowest weighted total
- **Per-Segment Averages** — Average score across all judges and contestants
- **Toughest Segment** — Segment with the lowest average score
- **Easiest Segment** — Segment with the highest average score
- **Judge Progress Map** — Which judges have submitted/locked per segment
- **Full Score Matrix** — Per-judge, per-contestant, per-segment breakdown

### Quiz Bee Mission Control (`/events/api/<event_id>/pb_mission_control`)

Real-time polling endpoint that returns:
- Per-team answered count vs total questions
- Progress percentage per team
- Cumulative scores (respecting scoring type: per_round, cumulative, hybrid)
- Ranking with visual indicators (gold for 1st, green for qualifiers, red for eliminated)

---

## 📄 Export — PDF Reports

The system generates professional PDF reports via **ReportLab** with two export targets:

### 1. Overall Results PDF

- Event title, type, and generation timestamp
- Ranked table with per-segment scores and total prelim/final scores
- Supports dual-category events (Male/Female) with automatic page breaks
- Signatory blocks for all assigned judges/tabulators with role labels

### 2. Segment Matrix PDF

- Per-segment breakdown showing each judge's score for each contestant
- Criteria weights applied; average column computed
- Signatory blocks matching the segment's assigned panel

### Export Route

```
GET /admin/scores/<event_id>/export/overall       → Full results PDF
GET /admin/scores/<event_id>/export/segment_<id>   → Segment matrix PDF
```

All PDFs use landscape orientation with dynamic column widths, professional styling (dark headers, grid lines), and are served as downloadable attachments.

---

## 🚀 Installation & Setup

### Prerequisites

- **Python 3.9+**
- **XAMPP** (or any MySQL server) with MySQL service running
- **Git**

### Step-by-Step

```bash
# 1. Clone the repository
git clone https://github.com/mrfahrenheit0528/JudgeMeNot_V2.0.git
cd JudgeMeNot_V2.0

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Optional: install QR code support
pip install qrcode Pillow

# 5. Configure the database connection
# Edit the .env file in the project root:
#   db_pass=your_mysql_password
#   db_username=root        (optional, defaults to root)
#   db_host=localhost        (optional, defaults to localhost)

# 6. Start your MySQL server (XAMPP → Start MySQL)

# 7. (Optional) Seed the database with sample data
python seed.py

# 8. Run the application
python main.py
```

### After Starting

```
 --- SERVER STARTED ---
 * Local:    http://127.0.0.1:5000
 * Network:  http://192.168.x.x:5000
 ----------------------
```

- Open the **Local** URL on the host machine
- Share the **Network** URL (or scan the QR code from Settings) with judges on the same LAN

### Default Seed Accounts

| Username | Name | Role | Password |
|---|---|---|---|
| `mj` | Michael Jackson | Admin | `pass123` |
| `sc` | Sabrina Carpenter | Judge | `pass123` |
| `ts` | Taylor Swift | Judge | `pass123` |
| `bm` | Bruno Mars | Tabulator | `pass123` |
| `ag` | Ariana Grande | Tabulator | `pass123` |

---

## 👑 Admin Guide

### Creating an Event

1. Navigate to **Control Panel** or `/events/create`
2. Enter the event name
3. Select event type:
   - **Score-Based** for pageants (weighted criteria scoring)
   - **Point-Based** for quiz bees (correct/wrong per question)
4. Set category count (1 = single, 2 = Male/Female divisions)
5. Click **Create** → you'll be redirected to the Event Management page

### Setting Up a Score-Based Event (Pageant)

1. **Add Segments** — e.g., "Swimwear" at 50%, "Evening Gown" at 50%. Mark one as "Final" if using elimination.
2. **Add Criteria** per segment — e.g., "Poise" at 60% weight, max score 10.
3. **Add Contestants** — Name, candidate number, category (if dual), optional photo upload.
4. **Assign Judges** — Select from existing judge accounts or quick-create new ones. Designate one as Chairman.
5. **Launch** the event → status changes to `Ongoing`.
6. **Activate segments** one at a time → judges can now score.

### Setting Up a Point-Based Event (Quiz Bee)

1. **Add Rounds** — e.g., "Easy Round" (5 questions × 1 point), "Hard Round" (5Q × 3pts). Set qualifying count per round.
2. **Add Teams** — Each team must be linked to a tabulator (1:1 assignment).
3. **Launch** the event and activate the first round.
4. **Monitor** via the Mission Control live dashboard.
5. **Evaluate** when all tabulators finish → system auto-handles ties and round advancement.

### Managing Users

- Navigate to **Admin → Users** (`/admin/users`)
- **Add** new accounts with name, username, password, and role
- **Edit** existing accounts (password update is optional — leave blank to keep current)
- **Delete** accounts (the primary admin account is protected)

### Viewing Audit Logs

- Navigate to **Admin → Logs** (`/admin/logs`)
- Shows the 150 most recent actions with timestamps
- Actions tracked: LOGIN, LOGOUT, CREATE_EVENT, CREATE_USER, EDIT_USER, DELETE_USER, CREATE_SEGMENT, CREATE_CONTESTANT, CREATE_CRITERIA, and more

### Exporting Results

1. Go to **Admin → Scores** → select an event
2. Click **Export Overall** for the full ranked results PDF
3. Click **Export** on any segment for the per-judge matrix PDF
4. PDFs include signatory blocks for official documentation

### Verifying Score Integrity

1. Go to **Admin → Ledger Explorer** (`/admin/ledger`)
2. The page displays all blocks in the chain with integrity status
3. If tampering is detected, compromised blocks are highlighted
4. The Local Ledger Node widget (bottom-left) provides passive real-time monitoring

---

## 📱 Judge / Tabulator Guide

### For Pageant Judges

1. **Log in** with your credentials at the login page
2. Your **Judge Dashboard** shows all events you're assigned to
3. When an event is live and a segment is active, click **Score Now**
4. You'll see all contestants with input fields for each criteria
5. Enter scores (0 to max) — they auto-save on change
6. When finished with all contestants, click **Lock & Submit** (this is irreversible)
7. Wait for the admin to activate the next segment

### For Quiz Bee Tabulators

1. **Log in** with your credentials
2. Your dashboard shows events where your team is participating
3. When a round is active, click **Score Now**
4. For each question, mark **Correct** ✅ or **Wrong** ❌
5. Click **Save** to submit all answers
6. If your team qualifies for the next round, it will appear automatically
7. If your team is eliminated, you'll see a notification

### Tips

- Use the **Leaderboard** page (`/leaderboard/`) to follow live rankings
- Access **System Settings** from the user dropdown to see the connection QR code
- Toggle **Dark/Light mode** using the moon/sun button in the navbar

---

## 📁 Project Structure

```
JudgeMeNot_V2.0/
├── main.py                    # App factory, SocketIO setup, root routes
├── seed.py                    # Database seeder with sample data
├── requirements.txt           # Python dependencies
├── .env                       # Database credentials (gitignored)
├── .gitignore
│
├── webapp/
│   ├── __init__.py
│   │
│   ├── python/                # Backend modules
│   │   ├── auth.py            # Login, logout, password hashing, role decorator
│   │   ├── admin.py           # Admin panel routes (users, logs, settings, ledger)
│   │   ├── events.py          # Event CRUD, segment/criteria/contestant management
│   │   ├── judge.py           # Judge scoring UI and API endpoints
│   │   ├── leaderboard.py     # Public leaderboard with real-time API
│   │   ├── scores.py          # Score analytics, matrix view, PDF export
│   │   ├── services.py        # Core business logic (ledger, ranking, dashboard)
│   │   ├── reporting.py       # Standalone PDF report generator
│   │   ├── tiebreaker.py      # Clincher round generation and tie detection
│   │   ├── models.py          # SQLAlchemy ORM models (10 tables)
│   │   └── database.py        # Engine, session factory, auto-create DB
│   │
│   ├── templates/             # Jinja2 HTML templates
│   │   ├── base.html          # Master layout (navbar, theme, ledger widget)
│   │   ├── login.html         # Authentication page
│   │   ├── index.html         # Admin dashboard
│   │   ├── judge_dashboard.html
│   │   ├── judge_scoring.html # Pageant scoring interface
│   │   ├── pb_scoring.html    # Quiz bee scoring interface
│   │   ├── event_create.html
│   │   ├── event_manage.html  # Event control panel
│   │   ├── leaderboard_main.html
│   │   ├── leaderboard_detail.html
│   │   ├── scores_main.html
│   │   ├── scores_detail.html # Analytics + export
│   │   ├── ledger_explorer.html
│   │   ├── admin_users.html
│   │   ├── admin_events.html
│   │   ├── admin_logs.html
│   │   ├── admin_settings.html
│   │   ├── admin_participants.html
│   │   ├── about.html
│   │   └── manage_partials/   # Reusable template fragments
│   │
│   └── static/
│       ├── css/               # Stylesheets
│       │   ├── main.css       # Core layout and component styles
│       │   ├── dark-mode.css  # Dark theme overrides
│       │   ├── universe.css   # Particle/aurora backdrop
│       │   ├── admin.css      # Admin-specific styles
│       │   ├── judge.css      # Judge interface styles
│       │   └── style.css      # Page-specific styles
│       ├── js/
│       │   ├── universe.js    # Particle canvas animation
│       │   └── ledger_node.js # Client-side blockchain witness
│       └── images/            # Static assets
│
├── reports/                   # Generated PDF reports (gitignored)
├── logs/                      # Application logs (gitignored)
├── instance/                  # Flask instance config
└── scripts/                   # Utility scripts and model extractors
```

---

## 📜 License

This project is developed for educational and institutional use. Please refer to the repository for specific licensing terms.

---

<p align="center">
  <sub>Built with ❤️ for fair and transparent event scoring</sub>
</p>
