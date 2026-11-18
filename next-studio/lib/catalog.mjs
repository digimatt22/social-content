import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = process.env.STUDIO_PHOTO_ROOT ?? "/Volumes/LaCie/MattMadeMe Assets/Product Photos";

export const sources = [
  { id: "bingo-3476", product: "Female Bingo Duck", folder: "Female Bingo", file: "IMG_3476.jpg" },
  { id: "bingo-3475", product: "Female Bingo Duck", folder: "Female Bingo", file: "IMG_3475.jpg" },
  { id: "vet-3482", product: "Vet Tech Duck", folder: "Vet Tech", file: "IMG_3482.jpg" },
  { id: "vet-3483", product: "Vet Tech Duck", folder: "Vet Tech", file: "IMG_3483.jpg" },
];

export function readSource(id) {
  const source = sources.find((entry) => entry.id === id);
  if (!source) throw new Error("Unknown source photo.");
  return readFileSync(join(root, source.folder, source.file));
}

export function digest(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

export function snapshotSources(ids) {
  if (!Array.isArray(ids) || ids.length < 1 || ids.length > 4 || new Set(ids).size !== ids.length) {
    throw new Error("Select one to four distinct source photos in reference order.");
  }
  return ids.map((id) => {
    const bytes = readSource(id);
    const { product, file } = sources.find((source) => source.id === id);
    return { id, product, file, sha256: digest(bytes) };
  });
}
