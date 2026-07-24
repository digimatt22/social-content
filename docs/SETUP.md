# Setup

## Local Marketing OS

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python run_local.py --host 127.0.0.1
```

Local startup defaults to `data/marketing_os.sqlite`. Set `MARKETING_OS_DB_PATH` for another SQLite database. Do not point production at SQLite.

## PostgreSQL development

Set `MARKETING_OS_DB_URL` to a PostgreSQL SQLAlchemy URL, then:

```sh
.venv/bin/alembic upgrade head
.venv/bin/python -m marketing_os.jobs.capability_preflight --profile foundation
```

PostgreSQL application startup requires the current Alembic head. Use `MARKETING_OS_TEST_POSTGRES_URL` to enable PostgreSQL integration tests.

## Authenticated service

Required production variables:

- `MARKETING_OS_ENV=production`
- `MARKETING_OS_DB_URL`
- `MARKETING_OS_SECRET`
- `MARKETING_OS_TRUSTED_HOSTS`
- `MARKETING_OS_PROXY_HOPS`

After migration:

```sh
marketing-os-admin create-admin owner
gunicorn --bind 127.0.0.1:8080 --workers 2 marketing_os.wsgi:app
```

Never pass a human password as a command argument. The admin CLI prompts interactively.

## Containers

```sh
docker build -t marketing-os .
MARKETING_OS_SECRETS_FILE=/absolute/protected/secrets.env \
  docker compose -f deploy/sheldon/compose.yml up --build
```

Use `deploy/sheldon/secrets.env.example` only as a field list. The actual Sheldon file belongs under `~/.config/sheldon/secrets/` with mode `0600`.

## Remote state

Marketing OS has no `origin` remote as of 2026-07-24. Do not invent one. Once the owner supplies the repository:

```sh
git remote add origin <approved-private-remote>
git push -u origin <phase-branch>
```

The MattMadeMe website is a separate Git repository and must use its own branch, validation, commit, and deployment workflow.

See `docs/operating-guides/permanent-service-operations.md` for cutover, identities, jobs, backups, and Sheldon gates.
