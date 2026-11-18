import { sources } from "../../../../lib/catalog.mjs";
import { copyInput, copyLimits } from "../../../../lib/responses.mjs";
import { maxImageBytes, openStudio, requireThat, StudioInputError } from "../../../../lib/studio.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const result = (body, status = 200) => Response.json(body, {
  status, headers: { "Cache-Control": "no-store" },
});

function localRequest(request) {
  const host = request.headers.get("host") ?? "";
  return /^(localhost|127\.0\.0\.1)(:[0-9]+)?$/i.test(host);
}

async function jsonForm(request) {
  const body = await request.json();
  requireThat(body && typeof body === "object" && !Array.isArray(body), "Expected a form object.");
  return body;
}

export async function GET(request, { params }) {
  if (!localRequest(request)) return result({ error: "Open the local studio." }, 403);
  const [kind, id] = (await params).path;
  const studio = openStudio();
  try {
    if (kind === "state") return result({ ...await studio.state(), copyAvailable: copyLimits().enabled });
    if (kind === "products") return result({ products: await studio.products() });
    if (kind === "product-photos" && /^\d+$/.test(id ?? "")) return result(await studio.productPhotos(Number(id)));
    if (kind === "source") {
      const source = sources.find(entry => entry.id === id);
      if (process.env.STUDIO_HOSTED !== "1" && !source) return result({ error: "Source was not found." }, 404);
      const image = await studio.sourceImage(id);
      if (!image) return result({ error: "Source was not found." }, 404);
      const expected = new URL(request.url).searchParams.get("hash");
      if (expected && image.sha256 !== expected) return result({ error: "The source file changed." }, 409);
      return new Response(image.bytes, { headers: {
        "Content-Type": image.mime, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
      } });
    }
    if (kind === "artifact") {
      const asset = await studio.get("SELECT bytes,mime FROM artifact WHERE id=?", id);
      if (!asset?.bytes) return result({ error: "Artifact was not found." }, 404);
      return new Response(asset.bytes, { headers: {
        "Content-Type": asset.mime, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
      } });
    }
    return result({ error: "Page was not found." }, 404);
  } catch (error) {
    if (error instanceof StudioInputError) return result({ error: error.message }, 400);
    if (error.code === "ENOENT") return result({ error: "The original photo is unavailable." }, 404);
    throw error;
  } finally {
    studio.close();
  }
}

export async function POST(request, { params }) {
  const origin = request.headers.get("origin");
  if (!localRequest(request) || (origin && origin !== `http://${request.headers.get("host")}`) ||
      request.headers.get("sec-fetch-site") === "cross-site") {
    return result({ error: "Open the local studio to make changes." }, 403);
  }
  const [kind, id] = (await params).path;
  const limit = ["attach", "upload-source"].includes(kind) ? maxImageBytes + 16_384 : 32_768;
  const length = Number(request.headers.get("content-length"));
  if (!Number.isSafeInteger(length) || length < 1 || length > limit) {
    return result({ error: "The form is missing or exceeds the upload limit." }, 413);
  }

  const studio = openStudio();
  try {
    if (kind === "upload-source" && /^\d+$/.test(id ?? "")) {
      const file = (await request.formData()).get("image");
      requireThat(file instanceof File && file.size <= maxImageBytes, "Choose an image up to 10 MB.");
      const source = await studio.uploadSource({ productId: Number(id), filename: file.name,
        mime: file.type, bytes: Buffer.from(await file.arrayBuffer()) });
      return result({ id: source }, 201);
    }
    if (kind === "attach") {
      const form = await request.formData();
      const file = form.get("image");
      requireThat(file instanceof File && file.size <= maxImageBytes, "Choose an image up to 10 MB.");
      const artifact = await studio.attach(id, {
        proposalId: form.get("proposalId"), providerId: form.get("providerId"),
        mime: file.type, bytes: Buffer.from(await file.arrayBuffer()),
      });
      return result({ id: artifact }, 201);
    }
    if (kind === "assignment") return result({ id: await studio.create(await jsonForm(request)) }, 201);
    if (kind === "command") {
      await studio.command(id, await jsonForm(request), copyLimits(), copyInput);
      return result({ received: true });
    }
    return result({ error: "Action was not found." }, 404);
  } catch (error) {
    if (error instanceof StudioInputError || error instanceof SyntaxError) {
      return result({ error: error.message }, 400);
    }
    console.error("Studio action failed", { kind, id, code: error.code });
    return result({ error: "The studio could not save this change." }, 500);
  } finally {
    studio.close();
  }
}
