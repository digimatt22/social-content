import os

from sqlalchemy import create_engine, text

REVISION = "studio_0001"
TABLES = """
CREATE TABLE social_studio.assignment (
  id TEXT PRIMARY KEY, brief TEXT NOT NULL, created BIGINT NOT NULL
);
CREATE TABLE social_studio.copy (
  id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES social_studio.assignment(id),
  caption TEXT NOT NULL, origin TEXT NOT NULL, job_id TEXT UNIQUE, created BIGINT NOT NULL
);
CREATE TABLE social_studio.job (
  id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES social_studio.assignment(id), state TEXT NOT NULL,
  model TEXT NOT NULL, input TEXT NOT NULL, provider_id TEXT UNIQUE, usage TEXT,
  detail TEXT, next_poll BIGINT NOT NULL, created BIGINT NOT NULL
);
CREATE UNIQUE INDEX active_copy_job ON social_studio.job(assignment_id)
  WHERE state IN ('queued','submitting','running','uncertain');
CREATE TABLE social_studio.proposal (
  id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES social_studio.assignment(id),
  settings TEXT NOT NULL, quote TEXT, approved BIGINT, started BIGINT, created BIGINT NOT NULL
);
CREATE UNIQUE INDEX one_started_proposal ON social_studio.proposal(assignment_id) WHERE started IS NOT NULL;
CREATE TABLE social_studio.artifact (
  id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES social_studio.assignment(id),
  proposal_id TEXT UNIQUE REFERENCES social_studio.proposal(id), provider_id TEXT UNIQUE,
  flags TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT, bytes BYTEA, created BIGINT NOT NULL
);
CREATE TABLE social_studio.review (
  id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES social_studio.assignment(id),
  copy_id TEXT NOT NULL REFERENCES social_studio.copy(id), artifact_id TEXT NOT NULL REFERENCES social_studio.artifact(id),
  judgment TEXT NOT NULL, owner_decision TEXT, owner_note TEXT, owner_at BIGINT, created BIGINT NOT NULL
);
CREATE TABLE social_studio.source_image (
  id TEXT PRIMARY KEY,
  product_id INTEGER NOT NULL,
  file TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('etsy', 'original')),
  sha256 TEXT NOT NULL,
  mime TEXT NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp')),
  bytes BYTEA NOT NULL,
  created BIGINT NOT NULL
);
CREATE INDEX source_product ON social_studio.source_image(product_id, created DESC);
CREATE TABLE social_studio.revision (version TEXT PRIMARY KEY);
"""


def migrate() -> None:
    engine = create_engine(os.environ["MARKETING_OS_DB_MIGRATION_URL"])
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(2143189417)"))
        applied = connection.execute(text("SELECT to_regclass('social_studio.revision')")).scalar_one()
        if applied:
            revision = connection.execute(text("SELECT version FROM social_studio.revision")).scalar_one()
            if revision != REVISION:
                raise RuntimeError("Unexpected Social Studio schema revision")
            return
        connection.execute(text("CREATE SCHEMA social_studio"))
        for statement in TABLES.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        connection.execute(text("INSERT INTO social_studio.revision VALUES (:revision)"), {"revision": REVISION})
        connection.execute(text("GRANT USAGE ON SCHEMA social_studio TO marketing_os_runtime"))
        connection.execute(text("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA social_studio TO marketing_os_runtime"))


if __name__ == "__main__":
    migrate()
