import Link from "next/link";

/**
 * List / Board / Timeline over the same data — the Plane pattern.
 *
 * Plain links carrying a `view` query param rather than client state: a chosen view then
 * survives a refresh and can be shared as a URL, which is the whole point of it.
 */
export default function ViewSwitcher({
  current,
  base,
  extra = "",
}: {
  current: "list" | "board" | "timeline";
  base: string;
  extra?: string;
}) {
  const views: Array<{ key: "list" | "board" | "timeline"; label: string; href: string }> = [
    { key: "list", label: "List", href: `${base}?view=list${extra}` },
    { key: "board", label: "Board", href: `${base}?view=board${extra}` },
    { key: "timeline", label: "Timeline", href: `/timeline${extra ? `?${extra.replace(/^&/, "")}` : ""}` },
  ];

  return (
    <div className="seg" style={{ marginLeft: "auto" }}>
      {views.map((view) => (
        <Link key={view.key} href={view.href} aria-current={view.key === current ? "true" : undefined}>
          {view.label}
        </Link>
      ))}
    </div>
  );
}
