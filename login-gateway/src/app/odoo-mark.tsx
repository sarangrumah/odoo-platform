/**
 * The Odoo wordmark, drawn geometrically: o-d-o-o is three rings and a ring
 * with an ascender, which is close enough to the real logotype to read as it
 * at the size we use it, and costs no font and no remote asset.
 *
 * Inline rather than a file in public/ so it can take its colour from CSS
 * (`currentColor`) — an <img src="…svg"> cannot, and the brand purple needs to
 * lighten in dark mode to stay legible.
 */
export default function OdooMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 202 70"
      role="img"
      aria-label="Odoo"
      fill="none"
      stroke="currentColor"
      strokeWidth="11"
    >
      <circle cx="24" cy="44" r="17" />
      <circle cx="75" cy="44" r="17" />
      <path d="M92 13.5V66.5" strokeLinecap="round" />
      <circle cx="126" cy="44" r="17" />
      <circle cx="177" cy="44" r="17" />
    </svg>
  );
}
