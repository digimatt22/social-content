import { AsyncLocalStorage } from "node:async_hooks";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";

let pool;

export function openDatabase({ folder, schema }) {
  if (process.env.STUDIO_HOSTED === "1" && !folder) return openPostgres();

  const location = folder || process.env.STUDIO_DATA_DIR || join(process.cwd(), ".studio");
  mkdirSync(location, { recursive: true, mode: 0o700 });
  const db = new DatabaseSync(join(location, "studio.sqlite"));
  db.exec("PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
  db.exec(schema);
  return {
    get: (sql, ...args) => db.prepare(sql).get(...args),
    all: (sql, ...args) => db.prepare(sql).all(...args),
    run: (sql, ...args) => db.prepare(sql).run(...args),
    async transaction(action) {
      db.exec("BEGIN IMMEDIATE");
      try {
        const result = await action();
        db.exec("COMMIT");
        return result;
      } catch (error) {
        db.exec("ROLLBACK");
        throw error;
      }
    },
    close: () => db.close(),
  };
}

function openPostgres() {
  if (!pool) {
    const connectionString = process.env.MARKETING_OS_DB_URL?.replace(/^postgresql\+psycopg:/, "postgresql:");
    if (!connectionString?.startsWith("postgresql:")) throw new Error("Hosted Studio requires PostgreSQL.");
    const require = createRequire(join(process.cwd(), "package.json"));
    const { Pool, types } = require("pg");
    pool = new Pool({
      connectionString,
      options: "-c search_path=social_studio",
      max: 4,
      allowExitOnIdle: true,
      connectionTimeoutMillis: 3000,
      statement_timeout: 5000,
      types: { getTypeParser: (oid, format) => oid === 20 ? Number : types.getTypeParser(oid, format) },
    });
    pool.on("error", () => process.stderr.write("Studio PostgreSQL idle connection ended.\n"));
  }
  const active = new AsyncLocalStorage();
  function query(sql, args) {
    let index = 0;
    return (active.getStore() ?? pool).query(sql.replace(/\?/g, () => "$" + ++index), args);
  }
  return {
    get: async (sql, ...args) => (await query(sql, args)).rows[0],
    all: async (sql, ...args) => (await query(sql, args)).rows,
    run: async (sql, ...args) => ({ changes: (await query(sql, args)).rowCount }),
    async transaction(action) {
      const connection = await pool.connect();
      try {
        await connection.query("BEGIN");
        await connection.query("SELECT pg_advisory_xact_lock(2143189417)");
        const value = await active.run(connection, action);
        await connection.query("COMMIT");
        return value;
      } catch (error) {
        await connection.query("ROLLBACK");
        throw error;
      } finally {
        connection.release();
      }
    },
    close() {},
  };
}
