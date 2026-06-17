# Freepik/Magnific Creative Integration Plan

Date: 2026-06-17

## Recommendation

Use Magnific as the next production creative backend, with the app treating Freepik/Magnific outputs as external generated assets that must pass human review before they can be assigned to marketing tasks.

The current local image-generation proof of concept produced files, manifests, and asset records, but the images were not good enough. Phase 5 should replace that renderer with an adapter that can call a better creative system while preserving the Phase 4 review boundary.

## Current Vendor Notes

Freepik has moved its AI/API branding under Magnific. Official Magnific docs describe:

- API-key authenticated REST APIs for server-to-server integration.
- A text-to-image endpoint at `POST https://api.magnific.com/v1/ai/mystic`.
- Image editing APIs including upscalers, relighting, style transfer, background removal, reimagine, expand, inpainting, and camera changes.
- A Magnific Upscaler Creative API at `POST /v1/ai/image-upscaler` with prompt-guided enhancement and 2x, 4x, 8x, or 16x scaling.
- A remote Magnific MCP endpoint at `https://mcp.magnific.com` that uses OAuth and can generate images, upscale assets, browse creations, and use account credits from an AI assistant.
- A documented distinction between the REST API for direct product integrations and MCP for agent/chat workflows.

Primary references:

- `https://docs.magnific.com/introduction`
- `https://docs.magnific.com/authentication`
- `https://docs.magnific.com/api-reference/image-upscaler-creative/image-upscaler`
- `https://docs.magnific.com/modelcontextprotocol`
- `https://www.magnific.com/api/image-generation`

Before implementation, verify account access, current endpoint names, pricing, credit behavior, and whether the needed product-shot workflows are available through REST API, MCP, or both.

## Goal

Make high-quality product creative easier to produce than manually assembling graphics while preserving product accuracy, source traceability, local asset indexing, and human approval.

The integration should answer:

- Which approved source image was used?
- Which prompt, format, model, and parameters were used?
- What did Magnific return?
- Where is the output stored locally?
- Did the output preserve the product accurately enough to use?
- Which rejected outputs should never be reused?
- Which approved outputs are ready for Instagram, Facebook, Etsy, website, or blog work?

## Boundary

Allowed:

- Use approved local, Etsy, or MattMadeMe website images as sources.
- Create generation or upscale jobs only from an explicit operator action.
- Store prompts, model names, job IDs, response metadata, output URLs, local output paths, and review state.
- Download accepted candidates into the local asset library or configured generated-output folder.
- Use MCP manually for exploratory passes while the REST adapter is not implemented.

Not allowed:

- Auto-approve generated outputs.
- Use generated images in tasks before review.
- Generate from an unapproved source asset.
- Replace source product photos with generated files.
- Publish to Etsy, website, Instagram, or Facebook.
- Commit API keys, downloaded output batches, or large creative files to git.

## Configuration

Local `.env` variables:

```text
MAGNIFIC_API_KEY=
MAGNIFIC_WEBHOOK_SECRET=
MARKETING_OS_ASSET_ROOT=/Volumes/MarketingAssets
```

If the MCP path is used, the OAuth session belongs to the local agent/client rather than the app. The app should still record returned files and metadata after the MCP run.

## Adapter Shape

Create a source-agnostic creative generation boundary:

```text
marketing_os/integrations/magnific.py
marketing_os/services/creative_generation.py
```

Suggested adapter methods:

- `create_image_generation_job(request)`
- `create_upscale_job(request)`
- `get_job(job_id)`
- `list_jobs(limit=None)`
- `download_output(output_url, destination_path)`

Suggested service responsibilities:

- validate that the source asset exists and is approved
- select output format specs from local templates
- build prompt requests with product accuracy constraints
- persist the request before sending it
- submit to Magnific REST API when credentials are configured
- support manual/MCP generation by importing a returned file plus metadata
- download outputs into the local asset library or generated-output folder
- create generated asset candidates in `needs_review`
- expose failures in Data Health

## Review Requirements

Every generated candidate should be reviewed for:

- product shape and proportions
- printed details, color, and silhouette
- no fake accessories, text, packaging, or hands unless requested
- no misspelled visible text
- crop and safe zone for the target platform
- sufficient resolution after any upscaling
- brand fit with MattMadeMe tone
- clear source asset and prompt traceability

Default state is `needs_review`. Approval should require a short review note.

## Phased Implementation

### Phase A - Manual/MCP Import Path

- Keep using the current app UI for source selection and manifest creation.
- Use Magnific MCP or web UI manually to generate better candidates.
- Add an import form for generated files plus Magnific job URL or notes.
- Register each output as a generated asset candidate with source asset linkage.

### Phase B - REST API Adapter

- Add `MAGNIFIC_API_KEY` config.
- Implement API-key authenticated calls with `x-magnific-api-key`.
- Submit one controlled generation or upscale request from an approved source image.
- Poll job status or handle webhook callbacks.
- Download outputs and register candidates.

### Phase C - Production Workflow

- Add batch generation with explicit per-product limits and credit/cost visibility.
- Add format-specific prompt templates.
- Add rejection reasons and "do not reuse this look" notes.
- Add Data Health checks for failed jobs, unreviewed outputs, and missing files.

## Acceptance Criteria

- A generated asset cannot be requested unless the source asset exists and is approved.
- Every request stores source asset ID, product slug, target format, prompt, provider, model/tool, and requested dimensions.
- Every provider response stores job ID or MCP run note, status, error, and output metadata.
- Downloaded outputs are kept out of git and registered as local/generated assets.
- All generated outputs start in `needs_review`.
- Approved generated outputs can be assigned to tasks.
- Rejected generated outputs remain traceable and are not shown as ready.
- Missing credentials produce a visible Data Health warning without breaking daily tasks.

