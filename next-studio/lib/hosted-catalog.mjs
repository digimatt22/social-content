const cdn = "i.etsystatic.com";
export const imageLimit = 10 * 1024 * 1024;

export function imageType(bytes) {
  if (bytes.length <= 12 || bytes.length > imageLimit) return null;
  if (bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) return "image/png";
  if (bytes.subarray(0, 3).equals(Buffer.from([255, 216, 255]))) return "image/jpeg";
  if (bytes.toString("ascii", 0, 4) === "RIFF" && bytes.toString("ascii", 8, 12) === "WEBP") return "image/webp";
  return null;
}

export function etsyPhotoUrl(raw) {
  try {
    const url = new URL(raw);
    if (url.origin === `https://${cdn}` && !url.username && !url.password) return url.href;
  } catch {}
  return null;
}

export async function downloadEtsyPhoto(url) {
  const response = await fetch(url, { redirect: "error", signal: AbortSignal.timeout(8000) });
  if (!response.ok || !response.body) throw new Error("Etsy image is unavailable.");
  const mime = response.headers.get("content-type")?.split(";")[0];
  if (!["image/jpeg", "image/png", "image/webp"].includes(mime) ||
      Number(response.headers.get("content-length")) > imageLimit) {
    await response.body.cancel();
    throw new Error("Etsy image is too large or its format is unsupported.");
  }
  const chunks = [];
  let length = 0;
  for await (const chunk of response.body) {
    length += chunk.length;
    if (length > imageLimit) throw new Error("Etsy image is too large.");
    chunks.push(chunk);
  }
  const bytes = Buffer.concat(chunks, length);
  if (imageType(bytes) !== mime) throw new Error("Etsy did not return image bytes.");
  return { bytes, mime };
}
