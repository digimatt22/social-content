# Getting Started

Use this guide to test the Phase 1 MattMadeMe Marketing OS locally.

## Requirements

- Python 3.11 or newer
- Terminal access from the repository root

Check Python:

```bash
python --version
```

## 1. Open The Project

From the repository root:

```bash
cd /Users/matt/Documents/marketing-os
```

Check the repo is clean:

```bash
git status --short --branch
```

Expected output:

```text
## main
```

## 2. Verify Business Context Loads

Run:

```bash
python -m marketing_os.cli --check-context
```

Expected output should look like:

```text
Loaded 6 business files
Products: 36
Audiences: 5
Goals: 5
```

This confirms the app is reading from `docs/business`.

## 3. Generate A Marketing Plan

Run:

```bash
python -m marketing_os.cli --start-date 2026-06-17 --output outputs/test-marketing-plan.md
```

Expected output:

```text
Wrote marketing plan to outputs/test-marketing-plan.md
```

Open the generated plan:

```bash
open outputs/test-marketing-plan.md
```

The file should include:

- 30-day content calendar
- 30 Instagram post ideas
- 30 Facebook post ideas
- 10 Instagram Reel ideas
- 10 Etsy promotion ideas
- 10 blog topic ideas
- 10 email newsletter ideas
- prioritized recommendations
- weekly marketing report

## 4. Run The End-To-End Demo

Run:

```bash
python demo.py
```

Expected output:

```text
Demo workflow completed successfully.
Output: outputs/demo-marketing-plan.md
```

Open the demo output:

```bash
open outputs/demo-marketing-plan.md
```

## 5. Run The Tests

Run:

```bash
python -m unittest discover -s tests
```

Expected output:

```text
........
----------------------------------------------------------------------
Ran 8 tests

OK
```

## 6. Confirm Business Docs Update Without Code Changes

Open `docs/business/products.md` and temporarily add a new duck under `Current Public Ducks And Themes`:

```markdown
- Test Launch Duck
```

Then run:

```bash
python -m marketing_os.cli --check-context
```

The product count should increase.

Generate another plan:

```bash
python -m marketing_os.cli --start-date 2026-06-17 --output outputs/test-updated-context-plan.md
```

Then search for the new product:

```bash
rg "Test Launch Duck" outputs/test-updated-context-plan.md
```

Remove the temporary product from `docs/business/products.md` when finished.

## 7. Common Commands

Print a plan to the terminal:

```bash
python -m marketing_os.cli --start-date 2026-06-17
```

Write a plan for today:

```bash
python -m marketing_os.cli --output outputs/today-marketing-plan.md
```

Use a different business-docs folder:

```bash
python -m marketing_os.cli --business-dir docs/business --check-context
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

### Output Files Dirty The Repo

Generated files in `outputs/` are ignored by git. They are safe to create while testing.

### Business Context Fails To Load

Confirm these files exist:

```bash
ls docs/business
```

Required files:

- `company-profile.md`
- `business-goals.md`
- `products.md`
- `audiences.md`
- `brand-voice.md`
- `marketing-channels.md`

