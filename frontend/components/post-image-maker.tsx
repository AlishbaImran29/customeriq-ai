"use client";

import { useEffect, useRef, useState } from "react";
import { Download, ImageUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { wrapLines } from "@/lib/launch-links";

type Template = "banner" | "split" | "frame";
type Format = "square" | "story";

const SIZES: Record<Format, { w: number; h: number }> = { square: { w: 1080, h: 1080 }, story: { w: 1080, h: 1920 } };
const INK = "#0b1220";
const WHITE = "#ffffff";
const ACCENT = "#22d3ee";
const BADGE = "#fbbf24";
const RTL = /[؀-ۿ]/;

/**
 * A simple post image maker that runs ENTIRELY in the browser (an HTML canvas): no paid image service and the
 * photo is never uploaded anywhere. Pick a photo, one of three templates and a size, add the price and labels,
 * and download a PNG. The picture is drawn from what the seller typed; nothing is invented.
 */
export function PostImageMaker({ productName }: { productName: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [photo, setPhoto] = useState<HTMLImageElement | null>(null);
  const [template, setTemplate] = useState<Template>("banner");
  const [format, setFormat] = useState<Format>("square");
  const [typedHeadline, setTypedHeadline] = useState<string | null>(null);        // null = follow the product name
  const headline = typedHeadline ?? productName;
  const [price, setPrice] = useState("");
  const [cod, setCod] = useState(true);
  const [freeDelivery, setFreeDelivery] = useState(false);
  const [custom, setCustom] = useState("");
  const [error, setError] = useState<string | null>(null);

  const labels = [cod ? "Cash on Delivery" : "", freeDelivery ? "Free Delivery" : "", custom.trim()].filter(Boolean);

  useEffect(() => {
    const el = canvas.current;
    if (el) draw(el, { photo, template, format, headline, price: price.trim(), labels });
  });

  function choose(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) return setError("Choose a PNG, JPEG or WebP picture.");
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      setPhoto(image);
      URL.revokeObjectURL(url);
    };
    image.onerror = () => {
      setError("That picture could not be opened.");
      URL.revokeObjectURL(url);
    };
    image.src = url;
  }

  function download() {
    canvas.current?.toBlob((blob) => {
      if (!blob) return;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${(productName || "post").replace(/[^\w-]+/g, "-").toLowerCase()}-${format}.png`;
      link.click();
      URL.revokeObjectURL(link.href);
    }, "image/png");
  }

  const { w, h } = SIZES[format];
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <div className="space-y-3">
        <div>
          <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" id="post-photo" onChange={(e) => choose(e.target.files?.[0])} />
          <Button variant="secondary" onClick={() => fileInput.current?.click()}>
            <ImageUp className="h-4 w-4" aria-hidden="true" />{photo ? "Change the photo" : "Choose a product photo"}
          </Button>
          <p className="mt-1 text-xs text-muted">The photo stays in your browser: it is not uploaded anywhere.</p>
        </div>
        <FilterPills label="Template" value={template} onChange={setTemplate}
          options={[{ value: "banner" as Template, label: "Photo with banner" }, { value: "split" as Template, label: "Photo and text panel" }, { value: "frame" as Template, label: "Framed photo" }]} />
        <FilterPills label="Size" value={format} onChange={setFormat}
          options={[{ value: "square" as Format, label: "Post 1080 x 1080" }, { value: "story" as Format, label: "Story 1080 x 1920" }]} />
        <label className="block space-y-1 text-xs font-medium text-muted">Headline<Input value={headline} onChange={(e) => setTypedHeadline(e.target.value)} maxLength={80} /></label>
        <label className="block space-y-1 text-xs font-medium text-muted">Price shown on the badge<Input value={price} onChange={(e) => setPrice(e.target.value)} maxLength={20} placeholder="Rs 1,999" /></label>
        <fieldset className="space-y-1.5 text-sm text-ink-2">
          <legend className="text-xs font-medium text-muted">Labels</legend>
          <label className="flex items-center gap-2"><input type="checkbox" checked={cod} onChange={(e) => setCod(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />Cash on Delivery</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={freeDelivery} onChange={(e) => setFreeDelivery(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />Free Delivery</label>
          <label className="block space-y-1 text-xs font-medium text-muted">Your own label (optional)<Input value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={30} /></label>
        </fieldset>
        <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
        <Button onClick={download} disabled={!photo}><Download className="h-4 w-4" aria-hidden="true" />Download PNG</Button>
        {!photo ? <p className="text-xs text-muted">Choose a photo to enable the download.</p> : null}
      </div>
      <div>
        <canvas ref={canvas} width={w} height={h} role="img" aria-label="Preview of the post image" className="mx-auto w-full max-w-sm rounded-xl border border-line bg-surface-2" style={{ aspectRatio: `${w} / ${h}` }} />
      </div>
    </div>
  );
}

type Options = { photo: HTMLImageElement | null; template: Template; format: Format; headline: string; price: string; labels: string[] };

function coverImage(ctx: CanvasRenderingContext2D, image: HTMLImageElement, x: number, y: number, w: number, h: number) {
  const scale = Math.max(w / image.width, h / image.height);
  const sw = w / scale, sh = h / scale;
  ctx.drawImage(image, (image.width - sw) / 2, (image.height - sh) / 2, sw, sh, x, y, w, h);
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function text(ctx: CanvasRenderingContext2D, value: string, x: number, y: number, size: number, color: string, maxWidth: number, maxLines: number, weight = 700) {
  ctx.font = `${weight} ${size}px system-ui, "Segoe UI", "Noto Naskh Arabic", sans-serif`;
  ctx.fillStyle = color;
  ctx.textBaseline = "top";
  const rtl = RTL.test(value);
  ctx.direction = rtl ? "rtl" : "ltr";
  ctx.textAlign = rtl ? "right" : "left";
  const lines = wrapLines(value, Math.max(6, Math.floor(maxWidth / (size * 0.52))), maxLines);
  lines.forEach((line, i) => ctx.fillText(line, rtl ? x + maxWidth : x, y + i * size * 1.2, maxWidth));
  ctx.direction = "ltr";
  return lines.length * size * 1.2;
}

function chips(ctx: CanvasRenderingContext2D, labels: string[], x: number, y: number, maxWidth: number, size: number) {
  let cx = x, cy = y;
  ctx.font = `700 ${size}px system-ui, "Segoe UI", sans-serif`;
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  ctx.direction = "ltr";
  for (const label of labels) {
    const w = ctx.measureText(label).width + size * 1.4, h = size * 1.9;
    if (cx + w > x + maxWidth && cx > x) { cx = x; cy += h + 14; }
    ctx.fillStyle = ACCENT;
    roundRect(ctx, cx, cy, w, h, h / 2);
    ctx.fill();
    ctx.fillStyle = INK;
    ctx.fillText(label, cx + size * 0.7, cy + h / 2);
    cx += w + 14;
  }
  return cy + size * 1.9 - y;
}

function badge(ctx: CanvasRenderingContext2D, price: string, cx: number, cy: number, r: number) {
  if (!price) return;
  ctx.fillStyle = BADGE;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = INK;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const size = price.length > 9 ? r * 0.36 : r * 0.46;
  ctx.font = `800 ${size}px system-ui, "Segoe UI", sans-serif`;
  ctx.fillText(price, cx, cy, r * 1.7);
}

function draw(el: HTMLCanvasElement, o: Options) {
  const ctx = el.getContext("2d");
  if (!ctx) return;
  const { w, h } = SIZES[o.format];
  ctx.clearRect(0, 0, w, h);
  const pad = 64;

  if (o.template === "banner") {
    ctx.fillStyle = INK;
    ctx.fillRect(0, 0, w, h);
    if (o.photo) coverImage(ctx, o.photo, 0, 0, w, h);
    const g = ctx.createLinearGradient(0, h * 0.45, 0, h);
    g.addColorStop(0, "rgba(11,18,32,0)");
    g.addColorStop(1, "rgba(11,18,32,0.92)");
    ctx.fillStyle = g;
    ctx.fillRect(0, h * 0.45, w, h * 0.55);
    badge(ctx, o.price, w - pad - 110, pad + 110, 110);
    const chipHeight = o.labels.length ? 90 : 0;
    const titleY = h - pad - chipHeight - 200;
    text(ctx, o.headline, pad, titleY, 76, WHITE, w - pad * 2, 3);
    if (o.labels.length) chips(ctx, o.labels, pad, h - pad - 54, w - pad * 2, 34);
  } else if (o.template === "split") {
    const photoH = Math.round(h * 0.62);
    ctx.fillStyle = INK;
    ctx.fillRect(0, 0, w, h);
    if (o.photo) coverImage(ctx, o.photo, 0, 0, w, photoH);
    badge(ctx, o.price, w - pad - 100, photoH - 20, 100);
    const used = text(ctx, o.headline, pad, photoH + 70, 70, WHITE, w - pad * 2 - 40, 2);
    if (o.labels.length) chips(ctx, o.labels, pad, photoH + 70 + used + 36, w - pad * 2, 32);
  } else {
    ctx.fillStyle = ACCENT;
    ctx.fillRect(0, 0, w, h);
    const inset = 56;
    ctx.save();
    roundRect(ctx, inset, inset, w - inset * 2, h - inset * 2, 48);
    ctx.clip();
    ctx.fillStyle = INK;
    ctx.fillRect(0, 0, w, h);
    if (o.photo) coverImage(ctx, o.photo, inset, inset, w - inset * 2, h - inset * 2);
    const g = ctx.createLinearGradient(0, inset, 0, inset + 360);
    g.addColorStop(0, "rgba(11,18,32,0.85)");
    g.addColorStop(1, "rgba(11,18,32,0)");
    ctx.fillStyle = g;
    ctx.fillRect(inset, inset, w - inset * 2, 360);
    ctx.restore();
    text(ctx, o.headline, inset + 48, inset + 44, 68, WHITE, w - inset * 2 - 300, 2);
    badge(ctx, o.price, w - inset - 110, inset + 110, 100);
    if (o.labels.length) {
      ctx.fillStyle = "rgba(11,18,32,0.0)";
      chips(ctx, o.labels, inset + 48, h - inset - 120, w - inset * 2 - 96, 32);
    }
  }
}
