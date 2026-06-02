import { NextRequest } from "next/server";
import { authProxy } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  return authProxy(req, "auth/register");
}
