# MattMadeMe Social Studio

This private Next.js app covers one manually started assignment from brief and ordered original photos to a versioned caption, image, review, and owner decision. The Results tab records the intended measurement and displays the decision history.

On Leonard, start the built app with `sh run-local.sh start` and open [the local studio](http://127.0.0.1:3037). Use `sh run-local.sh build` after changing the app, or use `sh run-local.sh dev` during development. The launcher uses Node.js 24 or the Codex bundled runtime on Leonard. The build was verified with the already installed Next.js and React versions in the manifest.

The server binds to loopback. Next.js and the worker share a local SQLite database under `.studio`. To use a disposable or separate database, set the same absolute `STUDIO_DATA_DIR` for both processes. `STUDIO_PHOTO_ROOT` overrides the read-only original photo location for the catalog. The catalog currently includes the Female Bingo and Vet Tech reference photos.

## Work through an assignment

1. In Work, save one primary outcome, the audience situation, a visible payoff, and the source details that support it. The first reference is the original image for a still. A carousel uses the selected photos in order.
2. Save a caption or queue it with Draft with OpenAI when the worker is configured. Each saved caption has its own version.
3. For a generated still, save the exact Magnific proposal. Simulate the cost in Magnific and record the quote and its receipt. The owner approves that proposal and credit amount before starting the handoff. Start it within 15 minutes of recording the quote. The app checks the source hashes before marking the handoff started.
4. Run the one approved image in Magnific with the original references. Return its task or creation ID and upload the result. The studio stores the output bytes and hash with the exact proposal. Generation takes place in Magnific. The app does not contact that provider.
5. In Review, choose the exact media and copy versions. Enter evidence for each of the four verdicts. Record the owner decision separately. Creative acceptance here carries no publication authority.

## Background copy

The copy worker submits a [background Responses request](https://developers.openai.com/api/docs/guides/background) with [structured output](https://developers.openai.com/api/docs/guides/structured-outputs). It records the response ID before polling and writes a draft once. A send with an uncertain result is held for reconciliation. Record the OpenAI job ID when investigating a hold. The provider request includes the studio job ID as metadata.

The web process and worker use the same approved server environment. The worker requires an OpenAI credential and a configured daily draft count. Caption drafts default to `gpt-6.1-terra`, and `STUDIO_OPENAI_MODEL` can override the default. Each request is capped at 1,500 output tokens and gets one submission attempt. The worker command is `sh run-local.sh worker`. The studio can run without a credential by saving manual drafts. Live activation remains subject to the project credential and spending decision.

The [versioned caption policy](lib/caption-policy.mjs) applies the drafting guidance from the social-media-skills pilot. It uses [Creative Direction](../../brand/CREATIVE_DIRECTION.md), the [brand playbook](../../PLAYBOOK.md), and owner-approved voice examples from [North Pole Mail](../../work/NORTH-POLE-MAIL-20261113/TASK.md) and [Room Steward](../../work/ROOM-STEWARD-20261113/TASK.md). Each job stores the exact policy and only the guidance for its channel and outcome. The app sends this curated prompt to OpenAI. The Codex planning, analytics, and review playbooks stay in the existing studio workflow.

The caption prompt checks whether a hook or punchline could fit an unrelated duck. For follower growth, it asks for one concrete payoff viewers can expect again, tied to the design or character they just saw.

Run `sh run-local.sh test` to verify the caption request, response-ID recovery, and uncertain-submission handling with fixtures. The application build and these tests do not make live API calls.

## Hosted Social Studio

On Sheldon, the existing operator login opens Social Studio. Start a post from Posts or from a selected product. Products shows Etsy references separately from uploaded originals. Each post keeps its caption, optional Magnific image, version-specific review, and measurement plan together. Social Studio stores selected references, uploaded originals, and generated results in PostgreSQL. Older dashboard opens the previous console. Edit product details opens its product editor directly.

Sheldon routes the public hostname to the authenticated Flask gateway. Next.js listens on container loopback. The web process uses the existing database runtime role. Hosted OpenAI calls need their own credential scope and budget.

The [Sheldon release instructions](../SHELDON_DEPLOY.md) describe staging and the independent Social Studio schema migration. The local launcher uses SQLite and the four Leonard sample photos.
