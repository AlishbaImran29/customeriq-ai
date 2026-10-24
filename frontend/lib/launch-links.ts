// Small pure helpers for Launch Studio (no imports, so they can be tested on their own: launch-links.test.ts).

/** Digits of an international number from the backend format "+923001234567", or null if it is not usable. */
export function phoneDigits(phone: string | null | undefined): string | null {
  const digits = (phone ?? "").replace(/\D/g, "");
  return /^[1-9]\d{7,14}$/.test(digits) ? digits : null;
}

/**
 * A wa.me link with the message already typed. Nothing is sent until the seller presses send inside WhatsApp.
 * Null when the vendor has no usable number (the caller shows a disabled button and says why).
 */
export function waMeLink(phone: string | null | undefined, message: string): string | null {
  const digits = phoneDigits(phone);
  const text = message.trim();
  if (!digits || !text) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}

/** A whole Meta ad as plain text, for the copy button. */
export function adAsText(ad: { hook: string; primary_text: string; headline: string; cta: string }): string {
  return `${ad.hook}\n\n${ad.primary_text}\n\n${ad.headline}\n${ad.cta}`;
}

/** An Instagram post as plain text: the caption, then the hashtags. */
export function instagramAsText(post: { caption: string; hashtags: string[] }): string {
  return post.hashtags.length ? `${post.caption}\n\n${post.hashtags.join(" ")}` : post.caption;
}

/** Hashtags typed as one line ("summer, #fan  cool") into a clean list that each start with #. */
export function parseHashtags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(/[\s,]+/)) {
    const word = raw.replace(/^#+/, "").replace(/[^\p{L}\p{N}_]/gu, "");
    const tag = word ? `#${word}` : "";
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out.slice(0, 30);
}

/** Split text into lines no wider than `maxChars`, breaking only between words (used by the image maker). */
export function wrapLines(text: string, maxChars: number, maxLines: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word;
    if (next.length <= maxChars || !line) line = next;
    else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    kept[maxLines - 1] = `${kept[maxLines - 1].replace(/[.,;:!?]+$/, "")}…`;
    return kept;
  }
  return lines;
}
