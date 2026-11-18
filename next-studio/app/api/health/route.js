import { openStudio } from "../../../lib/studio.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  if (process.env.STUDIO_HOSTED !== "1") return Response.json({ status: "ok" });
  try {
    const studio = openStudio();
    await studio.get("SELECT id FROM public.products LIMIT 1");
    const { revision } = await studio.get("SELECT to_regclass('social_studio.revision') AS revision");
    if (!revision) return Response.json({ status: "awaiting_migration" });
    const applied = await studio.get("SELECT version FROM revision");
    if (applied?.version !== "studio_0001") throw new Error("Unexpected studio revision");
    return Response.json({ status: "ready" });
  } catch {
    return Response.json({ status: "not_ready" }, { status: 503 });
  }
}
