import { randomUUID } from "node:crypto";
import { openDatabase } from "./database.mjs";
import { digest, readSource, snapshotSources } from "./catalog.mjs";
import { downloadEtsyPhoto, etsyPhotoUrl, imageLimit, imageType } from "./hosted-catalog.mjs";

export const outcomes = ["Follower growth", "Engagement", "Drive sales"];
export const channels = ["Instagram", "Facebook", "Pinterest", "X", "r/3dprintedducks"];
export const gates = ["Idea and relevance", "Visual execution", "Product and factual truth", "Copy and outcome"];
export const model = "nano-banana-pro-flash";
export const maxImageBytes = imageLimit;

export class StudioInputError extends Error {}

export function requireThat(condition, message) {
  if (!condition) throw new StudioInputError(message);
}

function field(value, label, max = 1200) {
  requireThat(typeof value === "string" && value.trim().length > 0 && value.length <= max,
    `${label} is required and must be at most ${max} characters.`);
  return value.trim();
}

function option(value, options, label) {
  requireThat(options.includes(value), `Select a valid ${label}.`);
  return value;
}

const json = JSON.stringify;
const parse = JSON.parse;
const now = () => Date.now();

const schema = `
    CREATE TABLE IF NOT EXISTS assignment (
      id TEXT PRIMARY KEY, brief TEXT NOT NULL, created INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS copy (
      id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES assignment(id),
      caption TEXT NOT NULL, origin TEXT NOT NULL, job_id TEXT UNIQUE, created INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS job (
      id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES assignment(id), state TEXT NOT NULL,
      model TEXT NOT NULL, input TEXT NOT NULL, provider_id TEXT UNIQUE, usage TEXT,
      detail TEXT, next_poll INTEGER NOT NULL, created INTEGER NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS active_copy_job ON job(assignment_id)
      WHERE state IN ('queued','submitting','running','uncertain');
    CREATE TABLE IF NOT EXISTS proposal (
      id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES assignment(id),
      settings TEXT NOT NULL, quote TEXT, approved INTEGER, started INTEGER, created INTEGER NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_started_proposal ON proposal(assignment_id) WHERE started IS NOT NULL;
    CREATE TABLE IF NOT EXISTS artifact (
      id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES assignment(id),
      proposal_id TEXT UNIQUE REFERENCES proposal(id), provider_id TEXT UNIQUE,
      flags TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT, bytes BLOB, created INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS review (
      id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES assignment(id),
      copy_id TEXT NOT NULL REFERENCES copy(id), artifact_id TEXT NOT NULL REFERENCES artifact(id),
      judgment TEXT NOT NULL, owner_decision TEXT, owner_note TEXT, owner_at INTEGER, created INTEGER NOT NULL
    );
`;

export function openStudio(folder) {
  const database = openDatabase({ folder, schema });
  const { get, all, run, transaction } = database;
  const hosted = process.env.STUDIO_HOSTED === "1" && !folder;

  async function products() {
    requireThat(hosted, "The hosted catalog is available on Sheldon.");
    return all("SELECT id,name,sync_status FROM public.products ORDER BY lower(name),id");
  }

  async function productPhotos(id) {
    requireThat(hosted, "The hosted catalog is available on Sheldon.");
    const product = await get("SELECT id,name FROM public.products WHERE id=?", id);
    requireThat(product, "Product was not found.");
    const origins = await all("SELECT id,file,kind,sha256 FROM source_image WHERE product_id=? AND kind='original' ORDER BY created DESC", id);
    const references = await all("SELECT id,name,canonical_url FROM public.assets WHERE product_id=? AND external_source='etsy' AND hidden_from_generation=0 ORDER BY default_reference DESC,id", id);
    return {
      product: product.name,
      photos: [
        ...origins.map(photo => ({ ...photo, product: product.name })),
        ...references.flatMap(asset => {
          const preview = etsyPhotoUrl(asset.canonical_url);
          return preview ? [{ id: `etsy-${asset.id}`, file: asset.name, kind: "etsy", product: product.name, preview }] : [];
        }),
      ],
    };
  }

  async function uploadSource({ productId, filename, mime, bytes }) {
    requireThat(hosted, "The hosted catalog is available on Sheldon.");
    requireThat(imageType(bytes) === mime, "Choose a PNG, JPEG, or WebP image up to 10 MB.");
    requireThat(await get("SELECT id FROM public.products WHERE id=?", productId), "Product was not found.");
    const id = `source-${randomUUID()}`;
    const file = field(filename.split(/[\\/]/).pop(), "Filename", 200);
    await run("INSERT INTO source_image (id,product_id,file,kind,sha256,mime,bytes,created) VALUES (?,?,?,?,?,?,?,?)",
      id, productId, file, "original", digest(bytes), mime, bytes, now());
    return id;
  }

  async function sourceImage(id) {
    if (hosted) return get("SELECT bytes,mime,sha256,file FROM source_image WHERE id=?", id);
    const bytes = readSource(id);
    return { bytes, mime: "image/jpeg", sha256: digest(bytes) };
  }

  async function hostedSources(ids) {
    requireThat(Array.isArray(ids) && ids.length >= 1 && ids.length <= 4 && new Set(ids).size === ids.length,
      "Select one to four distinct source photos in reference order.");
    const entries = [];
    for (const id of ids) {
      requireThat(typeof id === "string", "Invalid photo selection.");
      if (/^source-[\da-f-]{36}$/i.test(id)) {
        const original = await get("SELECT s.id,p.name,s.kind,s.file,s.sha256 FROM source_image s JOIN public.products p ON p.id=s.product_id WHERE s.id=? AND s.kind='original'", id);
        requireThat(original, "An original photo is unavailable.");
        entries.push({ id: original.id, product: original.name, kind: original.kind, file: original.file, sha256: original.sha256 });
        continue;
      }
      const key = /^etsy-(\d+)$/.exec(id);
      requireThat(key, "Invalid catalog photo selection.");
      const asset = await get("SELECT a.canonical_url,a.product_id,p.name FROM public.assets a JOIN public.products p ON p.id=a.product_id WHERE a.id=? AND a.external_source='etsy' AND a.hidden_from_generation=0", Number(key[1]));
      const url = asset && etsyPhotoUrl(asset.canonical_url);
      requireThat(url, "A selected Etsy photo is unavailable.");
      let image;
      try { image = await downloadEtsyPhoto(url); }
      catch { throw new StudioInputError("A selected Etsy photo could not be loaded. Choose another reference or attach an original."); }
      const checksum = digest(image.bytes);
      const snapshotId = `etsy-${key[1]}-${checksum}`;
      const file = `${id}.${image.mime.split("/")[1]}`;
      entries.push({ id: snapshotId, product: asset.name, kind: "etsy", file, sha256: checksum,
        snapshot: { productId: asset.product_id, mime: image.mime, bytes: image.bytes } });
    }
    return entries;
  }

  async function state() {
    return {
      assignments: (await all("SELECT * FROM assignment ORDER BY created DESC")).map(row => ({ ...row, brief: parse(row.brief) })),
      copy: await all("SELECT * FROM copy ORDER BY created DESC"),
      jobs: await all("SELECT id,assignment_id,state,model,provider_id,usage,detail,created FROM job ORDER BY created DESC"),
      proposals: (await all("SELECT * FROM proposal ORDER BY created DESC")).map(row => ({
        ...row, settings: parse(row.settings), quote: row.quote ? parse(row.quote) : null,
      })),
      artifacts: (await all("SELECT id,assignment_id,proposal_id,provider_id,flags,sha256,mime,created FROM artifact ORDER BY created DESC"))
        .map(row => ({ ...row, flags: parse(row.flags) })),
      reviews: (await all("SELECT * FROM review ORDER BY created DESC")).map(row => ({ ...row, judgment: parse(row.judgment) })),
    };
  }

  async function create(brief) {
    const channel = option(brief.channel, channels, "channel");
    const outcome = option(brief.outcome, outcomes, "outcome");
    requireThat(channel !== "r/3dprintedducks" || outcome !== "Drive sales", "The Reddit channel is strictly non-sales.");
    let sources;
    try { sources = hosted ? await hostedSources(brief.sourceIds) : snapshotSources(brief.sourceIds); }
    catch (error) {
      throw new StudioInputError(error.code === "ENOENT" ? "A source photo is unavailable." : error.message);
    }
    const id = randomUUID();
    const record = {
      title: field(brief.title, "Title", 100), channel, outcome,
      audience: field(brief.audience, "Audience situation"),
      payoff: field(brief.payoff, "Visible payoff"),
      fit: field(brief.fit, "Source detail that carries the idea"),
      action: field(brief.action, "Intended viewer action"),
      measure: field(brief.measure, "Measurement and decision rule"),
      format: option(brief.format, ["Still image", "Photo carousel"], "format"),
      sources: sources.map(({ snapshot, ...source }) => source),
    };
    requireThat(record.format !== "Photo carousel" || sources.length > 1, "Select at least two sources for a photo carousel.");
    await transaction(async () => {
      for (const source of sources.filter(source => source.snapshot)) {
        await run("INSERT INTO source_image (id,product_id,file,kind,sha256,mime,bytes,created) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
          source.id, source.snapshot.productId, source.file, source.kind, source.sha256, source.snapshot.mime, source.snapshot.bytes, now());
      }
      await run("INSERT INTO assignment VALUES (?,?,?)", id, json(record), now());
      const originals = record.format === "Still image" ? record.sources.slice(0, 1) : record.sources;
      await run("INSERT INTO artifact VALUES (?,?,?,?,?,?,?,?,?)", randomUUID(), id, null, null,
        json({ kind: "originals", sources: originals }), digest(json(originals)), null, null, now());
    });
    return id;
  }

  async function copyJob(id, limits, input) {
    requireThat(limits.enabled, "OpenAI worker is unavailable. You can write a draft in the studio.");
    return transaction(async () => {
      const active = await get("SELECT id FROM job WHERE assignment_id=? AND state IN ('queued','submitting','running','uncertain')", id);
      if (active) return active.id;
      const date = new Date();
      const since = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
      requireThat((await get("SELECT count(*) AS count FROM job WHERE created >= ?", since)).count < limits.daily,
        "The daily background copy limit has been reached.");
      const jobId = randomUUID();
      await run("INSERT INTO job (id,assignment_id,state,model,input,next_poll,created) VALUES (?,?,?,?,?,?,?)",
        jobId, id, "queued", limits.model, json(input), now(), now());
      return jobId;
    });
  }

  async function command(id, body, limits, buildCopyInput) {
    const assignment = await get("SELECT brief FROM assignment WHERE id=?", id);
    requireThat(assignment, "Assignment was not found.");
    const brief = parse(assignment.brief);
    const type = body.command;
    if (type === "queue-copy") return copyJob(id, limits, buildCopyInput(brief));
    if (type === "save-copy") {
      return await run("INSERT INTO copy VALUES (?,?,?,?,?,?)", randomUUID(), id,
        field(body.caption, "Caption", 2200), "manual", null, now());
    }
    if (type === "propose-image") {
      requireThat(brief.format === "Still image", "This build supports Magnific for still image assignments.");
      const proposalId = randomUUID();
      const scene = field(body.scene, "Scene and composition", 1700);
      const settings = {
        model, resolution: "2K", aspectRatio: option(body.ratio, ["1:1", "4:5", "9:16", "2:3"], "aspect ratio"),
        quantity: 1, retryCap: 0, sources: brief.sources,
        prompt: `${scene}\n\nUse ${brief.sources.map((source, index) => `@img${index + 1}: ${source.product} (${source.file})`).join("; ")} as ordered product photo references. Generate the complete scene. The printed duck is 2.5 inches tall and should read at that scale relative to the setting. Preserve its actual silhouette, colors, accessories, proportions, and print layer texture. Keep the required subjects readable at feed size. Keep the source files unchanged. Do not add text, logos, or measurement callouts.`,
      };
      return transaction(async () => {
        requireThat(!await get("SELECT id FROM proposal WHERE assignment_id=? AND started IS NOT NULL", id),
          "This assignment already has a started Magnific attempt.");
        await run("INSERT INTO proposal VALUES (?,?,?,NULL,NULL,NULL,?)", proposalId, id, json(settings), now());
        return proposalId;
      });
    }
    if (["record-quote", "approve-image", "start-image"].includes(type)) {
      return transaction(async () => {
        const p = await get("SELECT * FROM proposal WHERE id=? AND assignment_id=?", body.proposalId, id);
        requireThat(p, "Image proposal was not found.");
        requireThat(!await get("SELECT id FROM proposal WHERE assignment_id=? AND started IS NOT NULL", id),
          "This assignment already has a started Magnific attempt.");
        if (type === "record-quote") {
          requireThat(!p.approved, "Approved quotes are bound to their proposal. Create a new proposal to change the quote.");
          requireThat(Number.isSafeInteger(body.credits) && body.credits > 0, "Enter the estimated credits from Magnific.");
          return await run("UPDATE proposal SET quote=? WHERE id=?", json({
            credits: body.credits, receipt: field(body.receipt, "Simulation receipt"), recorded: now(),
          }), p.id);
        }
        requireThat(p.quote && parse(p.quote).credits === body.credits, "Review the current simulated quote before proceeding.");
        if (type === "approve-image") {
          requireThat(!p.approved, "This proposal already has approval.");
          return await run("UPDATE proposal SET approved=? WHERE id=?", now(), p.id);
        }
        requireThat(p.approved, "Approve the exact Magnific proposal before starting an attempt.");
        requireThat(now() - parse(p.quote).recorded <= 15 * 60 * 1000,
          "The recorded quote has expired. Record a fresh quote on a new proposal.");
        for (const source of parse(p.settings).sources) {
          const current = await sourceImage(source.id);
          requireThat(current?.sha256 === source.sha256, "A reference photo changed. Start with a fresh assignment.");
        }
        return await run("UPDATE proposal SET started=? WHERE id=?", now(), p.id);
      });
    }
    if (type === "review") {
      const copy = await get("SELECT id FROM copy WHERE id=? AND assignment_id=?", body.copyId, id);
      const asset = await get("SELECT id FROM artifact WHERE id=? AND assignment_id=?", body.artifactId, id);
      requireThat(copy && asset, "Select saved media and copy from this assignment.");
      const judgment = gates.map((name, i) => ({
        name, verdict: option(body.verdicts?.[i], ["Pass", "Revise", "Reject", "Blocked"], name),
        evidence: field(body.evidence?.[i], `${name} evidence`, 500),
      }));
      return await run("INSERT INTO review VALUES (?,?,?,?,?,NULL,NULL,NULL,?)",
        randomUUID(), id, copy.id, asset.id, json(judgment), now());
    }
    if (type === "owner-decision") {
      const review = await get("SELECT * FROM review WHERE id=? AND assignment_id=?", body.reviewId, id);
      requireThat(review && !review.owner_decision, "Select an undecided review.");
      const decision = option(body.decision, ["Accept creative", "Request revision", "Defer"], "decision");
      requireThat(decision !== "Accept creative" || parse(review.judgment).every(gate => gate.verdict === "Pass"),
        "Resolve the non-passing review gates before accepting creative.");
      const changed = await run("UPDATE review SET owner_decision=?, owner_note=?, owner_at=? WHERE id=? AND owner_decision IS NULL",
        decision, field(body.note, "Decision note", 500), now(), review.id);
      requireThat(changed.changes === 1, "This review already has an owner decision.");
      return changed;
    }
    throw new StudioInputError("Unknown action.");
  }

  async function attach(id, { proposalId, providerId, mime, bytes }) {
    const provider = field(providerId, "Magnific task or creation ID", 160);
    requireThat(bytes.length > 12 && bytes.length <= maxImageBytes, "Choose an image up to 10 MB.");
    requireThat(imageType(bytes) === mime, "Choose a PNG, JPEG, or WebP image.");
    return transaction(async () => {
      const proposal = await get("SELECT * FROM proposal WHERE id=? AND assignment_id=? AND started IS NOT NULL", proposalId, id);
      requireThat(proposal, "Start the approved Magnific handoff before recording a result.");
      requireThat(!await get("SELECT id FROM artifact WHERE proposal_id=? OR provider_id=?", proposalId, provider),
        "A result for that proposal or Magnific task was already attached.");
      const artifactId = randomUUID();
      await run("INSERT INTO artifact VALUES (?,?,?,?,?,?,?,?,?)", artifactId, id, proposalId, provider,
        json({ kind: "magnific", sources: parse(proposal.settings).sources, cost: "Unverified" }),
        digest(bytes), mime, bytes, now());
      return artifactId;
    });
  }

  return { state, create, command, attach, products, productPhotos, uploadSource, sourceImage, get, run, transaction, close: database.close };
}
