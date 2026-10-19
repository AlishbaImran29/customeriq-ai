import { Globe, Tag } from "lucide-react";

/**
 * A small logo for each sales channel. Instagram, WhatsApp and Facebook are drawn here (the icon library
 * has no brand logos); Website and Other use plain icons in the text colour of whatever they sit on. The logo always sits NEXT TO the channel's name,
 * never instead of it, so nothing depends on recognising a picture or a colour.
 */
export function ChannelIcon({ channel, className = "h-4 w-4" }: { channel: string; className?: string }) {
  switch (channel) {
    case "instagram":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true" focusable="false">
          <defs>
            <linearGradient id="ciq-instagram" x1="0" y1="1" x2="1" y2="0">
              <stop offset="0" stopColor="#FEDA75" />
              <stop offset="0.3" stopColor="#FA7E1E" />
              <stop offset="0.55" stopColor="#D62976" />
              <stop offset="0.8" stopColor="#962FBF" />
              <stop offset="1" stopColor="#4F5BD5" />
            </linearGradient>
          </defs>
          <rect width="24" height="24" rx="6" fill="url(#ciq-instagram)" />
          <rect x="5.5" y="5.5" width="13" height="13" rx="4" fill="none" stroke="#fff" strokeWidth="1.7" />
          <circle cx="12" cy="12" r="3.1" fill="none" stroke="#fff" strokeWidth="1.7" />
          <circle cx="16.2" cy="7.8" r="1" fill="#fff" />
        </svg>
      );
    case "whatsapp":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true" focusable="false">
          <rect width="24" height="24" rx="6" fill="#25D366" />
          <path d="M12 4.6a7.4 7.4 0 0 0-6.4 11.1L4.6 19.4l3.8-1A7.4 7.4 0 1 0 12 4.6z" fill="#fff" />
          <g transform="translate(8.6 8.6) scale(0.3)">
            <path
              fill="#25D366"
              d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"
            />
          </g>
        </svg>
      );
    case "facebook":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true" focusable="false">
          <rect width="24" height="24" rx="6" fill="#1877F2" />
          <path fill="#fff" d="M13.4 20v-6.6h2.2l.4-2.7h-2.6V9c0-.8.3-1.3 1.4-1.3h1.3V5.3c-.2 0-1-.1-2-.1-2 0-3.3 1.2-3.3 3.4v2.1H8.6v2.7h2.2V20h2.6z" />
        </svg>
      );
    case "website":
      return <Globe className={className} aria-hidden="true" />;
    default:
      return <Tag className={className} aria-hidden="true" />;
  }
}

/** The logo and the name together, for pills and table rows. */
export function ChannelLabel({ channel, children }: { channel: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <ChannelIcon channel={channel} />
      {children}
    </span>
  );
}
