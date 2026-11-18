import { setTimeout as wait } from "node:timers/promises";
import { openStudio } from "../lib/studio.mjs";
import { copyLimits, processOne, responsesClient } from "../lib/responses.mjs";

if (!copyLimits(process.env, { requireCredential: true }).enabled) {
  process.stderr.write("OpenAI copy worker is disabled. A credential and daily job limit are required.\n");
  process.exitCode = 1;
} else {
  const studio = openStudio();
  const client = responsesClient();
  let stopping = false;
  process.once("SIGINT", () => { stopping = true; });
  process.once("SIGTERM", () => { stopping = true; });
  try {
    if (process.env.STUDIO_HOSTED === "1") {
      while (!stopping) {
        const { revision } = await studio.get("SELECT to_regclass('social_studio.revision') AS revision");
        if (revision) break;
        await wait(3000);
      }
    }
    while (!stopping) {
      if (!await processOne(studio, client)) await wait(1000);
    }
  } finally {
    studio.close();
  }
}
