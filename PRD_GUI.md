# AutoApply — Windows Desktop App PRD
## Inspired by Tsenta.com · Phase 3

**Date:** 2026-04-14  
**Status:** In Progress

---

## 1. Problem

AutoApply's pipeline (scrape → tailor → track → submit) already works end-to-end via CLI.
The gap: there is **no user-facing interface**. The user must open a terminal, run commands,
and manually inspect `output/tracker_v2.xlsx` to see results. This creates friction and
makes the tool feel unfinished compared to Tsenta ($9.99/mo) and LazyApply ($99–$249).

Tsenta's key insight: users want **visibility and control**, not a black box.
Their live-browser visualization and dashboard are the product, not just the automation.

---

## 2. Goals

| Goal | Measure |
|---|---|
| Replace terminal workflow with a desktop app | Zero terminal commands needed for normal use |
| Surface job pipeline status at a glance | Dashboard shows counts by status in <1 second |
| One-click pipeline execution | Single button starts scrape → tailor → track |
| Live log visibility | All pipeline output streams into the app in real time |
| Background operation | App lives in system tray; runs scheduled pipeline silently |
| Jobs browser | Full table view with filter/search replacing Excel as primary view |
| Settings UI | Edit config.yaml through a form, no YAML knowledge needed |

**Non-goals (this phase):**
- Replacing the Playwright submission flow (already works, keep as-is)
- Web/cloud dashboard (Phase 4)
- Mobile app

---

## 3. Target User

A technical job seeker running AutoApply locally on Windows 11 during an active job search.
Needs something that runs quietly in the background, alerts on new matches, and allows
reviewing and submitting applications from a clean UI without touching a terminal.

---

## 4. Feature Spec

### 4.1 System Tray App

- App starts minimized to system tray on launch
- Tray icon: AutoApply logo (blue circle with "AA")
- Left-click: toggle main window visibility
- Right-click menu:
  - **Show / Hide Window**
  - **Run Pipeline** (triggers immediately)
  - **Run Pipeline + Submit** (pipeline + auto-submit)
  - **---**
  - **Quit AutoApply**
- Toast notification on pipeline completion (already in `notifier.py`)
- Tray tooltip shows last run time + new jobs count

### 4.2 Main Window

Two-panel layout: **sidebar navigation** + **content area**

**Sidebar** (left, ~180px):
- App name + version at top
- Nav items: Dashboard · Jobs · Logs · Settings
- Bottom: Run Pipeline button (always visible)

**Header bar**:
- Current view title
- Status indicator (Idle / Running / Error)
- Last run timestamp

**Window behavior**:
- Close button minimizes to tray (does not quit)
- `Ctrl+Q` / right-click Quit to actually exit
- Remembers window size and position
- Default size: 1100 × 700

### 4.3 Dashboard Tab

**Stats row** (5 cards):
- Total Discovered · Queued · Applied · Interviewing · Offers/Rejected

**Action buttons**:
- `▶ Run Pipeline` — runs scrape + tailor + track in background thread
- `▶ Run + Submit` — pipeline + auto-submit all Queued jobs
- Progress bar that fills during pipeline execution
- Cancel button (stops pipeline cleanly after current job)

**Recent matches** (last 10 jobs added):
- Title, Company, Match Score, Status, Date Added
- Click row → open job URL in browser

**Schedule status**:
- Shows next scheduled run time
- Toggle: enable/disable auto-run

### 4.4 Jobs Tab

**Full tracker table** reading from `output/tracker_v2.xlsx`:
- Columns: Title · Company · Location · Score · Source · Status · Date Added · Resume Type
- Color-coded status rows (mirrors Excel colors)
- Sort by any column (click header)
- Filter bar: text search + Status dropdown + Source dropdown + Resume Type dropdown
- Row count label ("Showing 47 of 312 jobs")

**Row actions** (right-click context menu or toolbar):
- Open URL in browser
- Open Resume (.docx)
- Open Cover Letter (.txt)
- Change Status → submenu (Queued / Applied / Skipped / Interviewing / Offer / Rejected)
- Copy job URL

**Toolbar buttons**:
- Refresh (reload from Excel)
- Export to CSV
- Open tracker in Excel

### 4.5 Logs Tab

**Live log stream**:
- All pipeline output rendered in real time
- Colored lines: INFO (white) · WARNING (yellow) · ERROR (red)
- Auto-scroll to bottom (toggle-able)
- Timestamp prefix per line

**Controls**:
- Clear log
- Copy all to clipboard
- Save log to file

### 4.6 Settings Tab

**Search section**:
- Query list: add / remove / reorder queries with resume type (ML/PM) per query
- Sources: checkboxes (LinkedIn · Indeed · ZipRecruiter · Glassdoor · Google · Dice · RemoteOK · Wellfound)
- Location field, Remote Only toggle
- Results per query (slider 5–50)
- Hours old (slider 6–168)

**Filter section**:
- Exclude keywords list (add/remove tags)
- Min description length

**AI/Claude section**:
- Model selector dropdown (haiku / sonnet / opus)
- Auto-generate cover letters toggle

**Notifications section**:
- Windows toast toggle
- Email digest: enable toggle + SMTP host/port/from/to fields

**Submission section**:
- Enabled toggle
- Headless toggle (show/hide browser)
- Profile fields: first name, last name, LinkedIn URL, GitHub URL
- Work authorization type
- Requires sponsorship toggle

**Save** button — writes all changes back to `config.yaml`

---

## 5. Technical Stack

| Component | Technology | Rationale |
|---|---|---|
| GUI framework | CustomTkinter (CTk) | Modern Python GUI, dark theme, Windows-native, zero Electron overhead |
| Jobs table | `tkinter.ttk.Treeview` | Handles 1000+ rows, sortable, native, no extra dependency |
| System tray | `pystray` + `Pillow` | Lightweight, Windows-native tray integration |
| Background pipeline | `threading.Thread` + `queue.Queue` | Non-blocking, no subprocess overhead |
| Log streaming | Python `logging.Handler` → queue | Tap into existing logger, no code changes to pipeline |
| Config persistence | `pyyaml` (already in requirements) | Already used throughout codebase |
| Tracker data | `openpyxl` (already in requirements) | Already used throughout codebase |

### New dependencies:
```
customtkinter>=5.2.0
pystray>=0.19.5
Pillow>=10.0.0
```

### Architecture:

```
app.py
  └── TrayApp (pystray)
       └── MainWindow (CTk toplevel)
            ├── Sidebar navigation
            ├── DashboardFrame
            │    ├── StatsRow (5 stat cards)
            │    ├── ActionBar (Run buttons + progress)
            │    └── RecentJobsTable
            ├── JobsFrame
            │    ├── FilterBar
            │    └── JobsTreeview (ttk.Treeview)
            ├── LogFrame
            │    └── LogTextBox (CTkTextbox, live stream)
            └── SettingsFrame
                 ├── SearchSection
                 ├── FilterSection
                 ├── AISection
                 ├── NotificationsSection
                 └── SubmissionSection

gui/runner.py
  └── PipelineRunner (threading.Thread)
       ├── Injects QueueHandler into root logger
       ├── Calls run_pipeline() and/or run_submission_pass()
       └── Posts log lines + completion event to queue
```

---

## 6. Implementation Plan

### Phase A — Core shell (this session)
- [x] `PRD_GUI.md` — this document
- [ ] `gui/__init__.py` + `gui/runner.py` — pipeline thread + log queue
- [ ] `gui/tray.py` — system tray icon + menu
- [ ] `gui/main_window.py` — window shell + sidebar + frame routing
- [ ] `gui/dashboard_frame.py` — stats + action buttons + recent jobs
- [ ] `gui/jobs_frame.py` — full tracker table with filters
- [ ] `gui/log_frame.py` — live log viewer
- [ ] `gui/settings_frame.py` — config form
- [ ] `app.py` — entry point
- [ ] `requirements.txt` — add CTk + pystray + Pillow
- [ ] `start.bat` — launch `app.py` instead of `main.py`

### Phase B — Polish (next session)
- [ ] Auto-schedule UI (next run countdown)
- [ ] Review panel for pending resumes (replace review.py CLI)
- [ ] Per-job detail drawer (click row → slide-in details panel)
- [ ] Keyboard shortcuts (R = run, J = jump to jobs, etc.)
- [ ] Installer / .exe packaging via PyInstaller

---

## 7. Competitive Positioning vs. Tsenta

| Feature | Tsenta | AutoApply Desktop |
|---|---|---|
| On-device | ✅ | ✅ |
| Live browser automation | ✅ | ✅ (Playwright, headless=false) |
| Resume tailoring per job | ✅ | ✅ (Claude API, superior) |
| Cover letter generation | ❌ | ✅ |
| Multiple job boards | 12 ATS only | LinkedIn, Indeed, ZipRecruiter, Google, Dice, RemoteOK + 8 ATS |
| Screening question answering | ✅ | ✅ (questions.yaml + Claude) |
| Excel/CSV tracker | ❌ | ✅ |
| System tray background | ❌ | ✅ |
| Windows toast notifications | ❌ | ✅ |
| Email digest | ❌ | ✅ |
| Price | $9.99/month | Free (self-hosted) |
| Cross-platform | Win/Mac/Linux | Windows (primary target) |

**AutoApply's unique advantages:**
1. Claude-powered resume tailoring (context-aware, preserves formatting)
2. Semantic similarity scoring (sentence-transformers, not just keywords)
3. Cover letter generation per job
4. Full Excel audit trail
5. Free — no subscription
