# Getting Started

Use this guide to test the current MattMadeMe Marketing OS web console locally.

## Requirements

- Python 3.11 or newer
- Terminal access from the repository root
- A trusted local network if opening the app from another device

## 1. Open The Project

```bash
cd /Users/matt/Documents/marketing-os
```

## 2. Install Dependencies

```bash
python -m pip install -e .
```

This installs Flask and SQLAlchemy for the local web console.

## 3. Start The Web Console

```bash
python run_local.py
```

This starts the app with the current local database as-is. It does not seed sample products, plans, or tasks unless you explicitly run:

```bash
python run_local.py --bootstrap-data
```

The server binds to `0.0.0.0` by default so trusted devices on the same network can reach it.

On the same machine, open:

```text
http://127.0.0.1:8000
```

From another device on the same network, open:

```text
http://<this-computer-ip>:8000
```

Use this only on a trusted local network. The app is not meant to be exposed to the public internet.

## 4. Confirm Startup Worked

On first run, the app will:

- initialize `data/marketing_os.sqlite`
- sync business context from `docs/business`
- sync templates from `docs/templates`
- create a default standard plan if no plan exists

You should land on the Today dashboard with an active plan and task cards.

## 5. Test The Operator Workflow

In the browser:

1. Open Today.
2. Click a social operator task.
3. Confirm the page shows product, asset, draft caption, CTA, hashtags, posting steps, preview checklist, status controls, and metric fields.
4. Change status to `posted`.
5. Save a note.
6. Enter a test metric.
7. Open Metrics and confirm the metric appears.

## 6. Generate A New Plan

Open Plans, choose a mode, and generate a new plan.

The new plan is stored in SQLite and appears in the calendar and task views.

## 7. Run Tests

```bash
python -m unittest discover -s tests
```

Expected output:

```text
...................
----------------------------------------------------------------------
Ran 19 tests

OK
```

## Useful Commands

Run the console on another port:

```bash
python run_local.py --port 8080
```

Restrict the console to this computer only:

```bash
python run_local.py --host 127.0.0.1
```

Start through the installed script:

```bash
marketing-os-web
```

## Troubleshooting

### `ModuleNotFoundError: No module named marketing_os`

Make sure you are running commands from the repository root:

```bash
pwd
```

Expected:

```text
/Users/matt/Documents/marketing-os
```

Then install the project:

```bash
python -m pip install -e .
```

### The App Is Not Reachable From Another Device

Confirm the server is running and bound to `0.0.0.0`.

Confirm both devices are on the same trusted network.

Use the computer's local network IP address, not `127.0.0.1`, from the other device.

### Database Files Dirty The Repo

The Phase 3 SQLite database in `data/` is ignored by git.

### Historical CLI Or Demo Commands

Phase 1 and Phase 2 executable entry points are archived in:

```text
archive/phase1-phase2-executables
```

The current supported entry point is the web console.
