export const dynamic = "force-dynamic";

/** Container healthcheck target. Deliberately says nothing about tenants. */
export function GET() {
  return Response.json({ status: "ok" });
}
