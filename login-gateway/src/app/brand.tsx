import { asset } from "@/lib/url";

import OdooMark from "./odoo-mark";

/**
 * The two brand lockups the front door uses.
 *
 * The logo ships in two files because the official artwork's wordmark is black:
 * it disappears on anything dark. `eal-logo-dark.png` is the same artwork with
 * the neutral inks lifted to near-white and the red/blue swoosh untouched.
 *
 * Which one is used is decided differently in each place, on purpose:
 *  - BrandPanel always sits on the dark gradient, so it always takes the dark
 *    variant, whatever the browser's colour scheme is.
 *  - BrandCompact sits on the page background, so it swaps with the scheme —
 *    done in CSS rather than JS so there is no flash of the wrong logo.
 */

export function BrandPanel() {
  return (
    <aside className="brand-panel">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="eal-logo"
        src={asset("/brand/eal-logo-dark.png")}
        alt="Erajaya Active Lifestyle"
        width={900}
        height={611}
      />
      <div>
        <div className="brand-rule" />
        <h1>
          EAL<span className="hub">-Hub</span>
        </h1>
        <p>
          Satu pintu masuk ke seluruh sistem ERP Erajaya Active Lifestyle — retail,
          gudang, keuangan, dan perpajakan.
        </p>
      </div>
      <div className="brand-foot">
        <span>Dibangun di atas</span>
        <OdooMark className="odoo-mark" />
        <span>Community 19.0</span>
      </div>
    </aside>
  );
}

/** Shown in place of BrandPanel on narrow screens, and on the version page. */
export function BrandCompact({
  className = "brand-compact",
  caption,
}: {
  className?: string;
  caption?: string;
}) {
  return (
    <div className={className}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="eal-logo on-light"
        src={asset("/brand/eal-logo.png")}
        alt="Erajaya Active Lifestyle"
        width={900}
        height={611}
      />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="eal-logo on-dark"
        src={asset("/brand/eal-logo-dark.png")}
        alt=""
        aria-hidden="true"
        width={900}
        height={611}
      />
      {caption ? <span className="brand-caption">{caption}</span> : null}
    </div>
  );
}
