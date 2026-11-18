import { randomUUID } from "node:crypto";
import { captionInstructions, captionPolicyVersion } from "./caption-policy.mjs";

const endpoint = "https://api.openai.com/v1/responses";
const defaultModel = "gpt-6.1-terra";
const outputLimit = 1_500;
const pollEvery = 4000;
const assetFilename = /\b[\w-]+(?:\.[\w-]+)*\.(?:avif|dng|gif|heic|jpe?g|mov|mp4|png|psd|webp)\b/i;
const internalNote = /^\s*(?:internal|production|review|source) notes?\s*:/im;

export function copyLimits(env = process.env, { requireCredential = env.STUDIO_HOSTED !== "1" } = {}) {
  const daily = Number(env.STUDIO_OPENAI_DAILY_JOBS);
  const model = env.STUDIO_OPENAI_MODEL?.trim() || defaultModel;
  return {
    enabled: Boolean((!requireCredential || env.OPENAI_API_KEY?.trim()) && Number.isSafeInteger(daily) && daily > 0 && daily <= 20),
    model, daily,
  };
}

export function copyInput(brief) {
  const publicContext = (value) => value.split(/\r?\n/)
    .filter(line => !internalNote.test(line))
    .map(line => line.replace(new RegExp(assetFilename.source, "gi"), "").trim())
    .join("\n").trim();

  return {
    policyVersion: captionPolicyVersion,
    instructions: captionInstructions(brief),
    brief: {
      audience: publicContext(brief.audience), payoff: publicContext(brief.payoff),
      outcome: brief.outcome, action: publicContext(brief.action), channel: brief.channel,
      format: brief.format, products: [...new Set(brief.sources.map(source => source.product))],
    },
  };
}

export function responsesClient(key = process.env.OPENAI_API_KEY) {
  async function request(url, options = {}) {
    const response = await fetch(url, {
      ...options, redirect: "error", signal: AbortSignal.timeout(25_000),
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    });
    if (!response.ok) {
      const failure = new Error(`OpenAI returned HTTP ${response.status}.`);
      failure.status = response.status;
      throw failure;
    }
    return response.json();
  }
  return {
    submit(job) {
      const input = JSON.parse(job.input);
      return request(endpoint, {
        method: "POST",
        body: JSON.stringify({
          model: job.model, background: true, max_output_tokens: outputLimit,
          instructions: input.instructions, input: JSON.stringify(input.brief),
          metadata: { studio_job_id: job.id, policy_version: input.policyVersion },
          text: { format: {
            type: "json_schema", name: "caption", strict: true,
            schema: { type: "object", properties: { caption: { type: "string" } },
              required: ["caption"], additionalProperties: false },
          } },
        }),
      });
    },
    retrieve(id) { return request(`${endpoint}/${encodeURIComponent(id)}`); },
  };
}

async function acceptResponse(studio, job, response) {
  if (response.id !== job.provider_id) throw new Error("Provider response ID did not match.");
  if (["queued", "in_progress"].includes(response.status)) return;
  const usage = response.usage ? JSON.stringify(response.usage) : null;
  let caption;
  let detail = "OpenAI returned no usable caption.";
  if (response.status === "completed") {
    try {
      const output = response.output.flatMap(item => item.type === "message" ? item.content : []);
      const text = output.filter(item => item.type === "output_text").map(item => item.text).join("");
      const parsed = JSON.parse(text);
      if (typeof parsed.caption === "string" && parsed.caption.trim() && parsed.caption.length <= 2200) {
        if (assetFilename.test(parsed.caption) || internalNote.test(parsed.caption)) {
          detail = "OpenAI returned a filename or an internal note. No caption was saved.";
        } else {
          caption = parsed.caption.trim();
        }
      }
    } catch {
      // An incomplete or refused response cannot become a saved draft.
    }
  }
  await studio.transaction(async () => {
    if (caption) {
      await studio.run("INSERT INTO copy VALUES (?,?,?,?,?,?) ON CONFLICT(job_id) DO NOTHING",
        randomUUID(), job.assignment_id, caption, "openai", job.id, Date.now());
    }
    await studio.run("UPDATE job SET state=?,usage=?,detail=? WHERE id=? AND state='running'",
      caption ? "complete" : "failed", usage, caption ? null : detail, job.id);
  });
}

export async function processOne(studio, client) {
  const time = Date.now();
  const job = await studio.transaction(async () => {
    await studio.run("UPDATE job SET state='uncertain',detail=? WHERE state='submitting' AND next_poll < ?",
      "The send was interrupted before the response ID was saved. Check OpenAI before sending again.", time);
    const next = await studio.get("SELECT * FROM job WHERE state IN ('queued','running') AND next_poll <= ? ORDER BY next_poll,created LIMIT 1", time);
    if (!next) return null;
    await studio.run("UPDATE job SET state=?,next_poll=? WHERE id=?",
      next.state === "queued" ? "submitting" : "running", time + 40_000, next.id);
    return next;
  });
  if (!job) return false;
  if (job.state === "queued") {
    let response;
    try {
      response = await client.submit(job);
      if (typeof response.id !== "string" || !response.id) throw new Error("Missing response ID.");
    } catch (error) {
      const rejected = [400, 401, 403, 404, 422, 429].includes(error.status);
      await studio.run("UPDATE job SET state=?,detail=? WHERE id=? AND state='submitting'",
        rejected ? "failed" : "uncertain",
        rejected ? error.message : "Submission could not be confirmed. Check OpenAI before sending again.", job.id);
      return true;
    }
    // Persist the response ID before interpreting any provider output.
    await studio.run("UPDATE job SET state='running',provider_id=?,next_poll=?,detail=NULL WHERE id=? AND state IN ('submitting','uncertain')",
      response.id, Date.now() + pollEvery, job.id);
    await acceptResponse(studio, { ...job, provider_id: response.id }, response);
    return true;
  }

  if (time - job.created > 30 * 60_000) {
    await studio.run("UPDATE job SET state='uncertain',detail=? WHERE id=? AND state='running'",
      "Polling stopped after 30 minutes. Check the saved OpenAI response before sending again.", job.id);
    return true;
  }
  try {
    const response = await client.retrieve(job.provider_id);
    await studio.run("UPDATE job SET next_poll=?,detail=NULL WHERE id=? AND state='running'", Date.now() + pollEvery, job.id);
    await acceptResponse(studio, job, response);
  } catch {
    await studio.run("UPDATE job SET next_poll=?,detail=? WHERE id=? AND state='running'",
      Date.now() + 15_000, "Waiting to retrieve the existing OpenAI response.", job.id);
  }
  return true;
}
