import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { copyInput, copyLimits, processOne, responsesClient } from "../lib/responses.mjs";
import { openStudio } from "../lib/studio.mjs";

const brief = {
  title: "A sculpted Bingo detail", outcome: "Follower growth", channel: "Instagram",
  format: "Still image", audience: "Bingo regulars noticing their favorite accessory.",
  payoff: "The photo reveals the dauber beside the duck.", fit: "See the original Bingo photo.",
  action: "Follow for the next sculpted detail.",
  measure: "Check seven-day attributed follows and record any missing data.",
  sourceIds: ["bingo-3476"],
};
const limits = { enabled: true, model: "test-model", daily: 4 };

test("hosted web queues copy without a credential while the worker requires one", () => {
  const env = { STUDIO_HOSTED: "1", STUDIO_OPENAI_DAILY_JOBS: "1" };
  assert.equal(copyLimits(env).enabled, true);
  assert.equal(copyLimits(env, { requireCredential: true }).enabled, false);
  assert.equal(copyLimits({ ...env, STUDIO_OPENAI_DAILY_JOBS: "0" }).enabled, false);
});

test("caption drafts use Terra and send a 1,500-output-token cap unless the model is overridden", async (t) => {
  const env = { OPENAI_API_KEY: "test-credential", STUDIO_OPENAI_DAILY_JOBS: "1" };
  const config = copyLimits(env);
  assert.equal(config.enabled, true);
  assert.equal(copyLimits({ ...env, STUDIO_OPENAI_MODEL: " gpt-5-mini " }).model, "gpt-5-mini");

  const folder = mkdtempSync(join(tmpdir(), "studio-caption-defaults-"));
  const studio = openStudio(folder);
  try {
    const id = await studio.create(brief);
    await studio.command(id, { command: "queue-copy" }, config, copyInput);
    const request = t.mock.method(globalThis, "fetch", async () => Response.json({ id: "resp_defaults", status: "queued" }));
    await processOne(studio, responsesClient(env.OPENAI_API_KEY));
    assert.equal(request.mock.callCount(), 1);
    const [url, requestOptions] = request.mock.calls[0].arguments;
    assert.equal(url, "https://api.openai.com/v1/responses");
    const body = JSON.parse(requestOptions.body);
    assert.equal(body.model, "gpt-6.1-terra");
    assert.equal(body.max_output_tokens, 1500);
    assert.equal(body.background, true);
    assert.equal(body.metadata.policy_version, "studio-v19-copy-v4");
    assert.match(body.instructions, /No street number\. No ZIP code\./);
    assert.match(body.instructions, /leave the reveal to the right frame/);
    assert.match(body.instructions, /concrete reason to follow/);
    assert.match(body.instructions, /If the opening or punchline could fit an unrelated duck, rewrite it/);
    assert.match(body.instructions, /one recurring payoff connected to this post/);
  } finally {
    studio.close();
    rmSync(folder, { recursive: true });
  }
});

test("caption guidance chooses the voice example and action for the brief’s channel and outcome", () => {
  const draft = { ...brief, sources: [{ product: "Female Bingo Duck" }] };
  const facebook = copyInput({ ...draft, channel: "Facebook", outcome: "Engagement" }).instructions;
  assert.match(facebook, /Which towel animal did your cabin steward leave you/);
  assert.match(facebook, /one meaningful response/);
  assert.doesNotMatch(facebook, /No ZIP code|concrete reason to follow|one recurring payoff/);

  const reddit = copyInput({ ...draft, channel: "r/3dprintedducks", outcome: "Engagement" }).instructions;
  assert.match(reddit, /Omit prices, availability, shop links, purchase prompts, and indirect sales funnels/);
  assert.doesNotMatch(reddit, /towel animal|No ZIP code/);
});

test("reopening the database retrieves the same Responses job and saves one draft", async () => {
  const folder = mkdtempSync(join(tmpdir(), "studio-worker-"));
  let studio = openStudio(folder);
  try {
    const id = await studio.create(brief);
    const jobId = await studio.command(id, { command: "queue-copy" }, limits, copyInput);
    assert.equal(await studio.command(id, { command: "queue-copy" }, limits, copyInput), jobId);
    await processOne(studio, { submit: async () => ({ id: "resp_fixture", status: "queued" }) });
    studio.close();
    studio = openStudio(folder);
    await studio.run("UPDATE job SET next_poll=0 WHERE id=?", jobId);
    await processOne(studio, {
      submit: async () => { assert.fail("Restart submitted a second provider request."); },
      retrieve: async (responseId) => {
        assert.equal(responseId, "resp_fixture");
        return {
          id: responseId, status: "completed", usage: { output_tokens: 12 },
          output: [{ type: "message", content: [{ type: "output_text", text: '{"caption":"That tiny Bingo detail."}' }] }],
        };
      },
    });
    const state = await studio.state();
    assert.equal(state.jobs[0].state, "complete");
    assert.equal(state.copy.length, 1);
    assert.equal(state.copy[0].caption, "That tiny Bingo detail.");
  } finally {
    studio.close();
    rmSync(folder, { recursive: true });
  }
});

test("a lost submit response stays uncertain and does not call the provider twice", async () => {
  const folder = mkdtempSync(join(tmpdir(), "studio-ambiguous-"));
  const studio = openStudio(folder);
  try {
    const id = await studio.create(brief);
    const jobId = await studio.command(id, { command: "queue-copy" }, limits, copyInput);
    await processOne(studio, { submit: async () => { throw new Error("Fixture transport loss"); } });
    assert.equal((await studio.state()).jobs[0].state, "uncertain");
    assert.equal(await studio.command(id, { command: "queue-copy" }, limits, copyInput), jobId);
    assert.equal(await processOne(studio, { submit: async () => assert.fail("Uncertain send was retried") }), false);
  } finally {
    studio.close();
    rmSync(folder, { recursive: true });
  }
});

test("copy jobs omit internal fields and refuse to save a caption with a source filename", async () => {
  const folder = mkdtempSync(join(tmpdir(), "studio-caption-context-"));
  const studio = openStudio(folder);
  try {
    const id = await studio.create({
      ...brief,
      title: "Private working title",
      payoff: "Spot the tiny dauber. IMG_3476.jpg\nInternal note: layout needs sign-off.",
      fit: "Internal source note for the reviewer",
    });
    await studio.command(id, { command: "queue-copy" }, limits, copyInput);
    await processOne(studio, {
      submit: async (job) => {
        const { brief: context } = JSON.parse(job.input);
        assert.equal(context.payoff, "Spot the tiny dauber.");
        assert.deepEqual(context.products, ["Female Bingo Duck"]);
        assert.doesNotMatch(JSON.stringify(context), /IMG_3476|sign-off|Private working title|Internal source note/i);
        return {
          id: "resp_filename_fixture", status: "completed", usage: { output_tokens: 12 },
          output: [{ type: "message", content: [{ type: "output_text", text: '{"caption":"Meet the duck in IMG_3476.jpg."}' }] }],
        };
      },
    });
    assert.equal((await studio.state()).jobs[0].state, "failed");
    assert.match((await studio.state()).jobs[0].detail, /filename or an internal note/);
    assert.equal((await studio.state()).copy.length, 0);
  } finally {
    studio.close();
    rmSync(folder, { recursive: true });
  }
});
