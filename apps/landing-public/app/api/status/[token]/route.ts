import { NextResponse } from 'next/server';
import { callOrchestrator } from '@/lib/api';
import { statusResponseSchema } from '@/lib/schemas';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  if (!token || token.length < 8) {
    return NextResponse.json({ error: 'Invalid token' }, { status: 400 });
  }
  try {
    const raw = await callOrchestrator({
      method: 'GET',
      path: `/v1/intake/${encodeURIComponent(token)}/status`,
    });
    const parsed = statusResponseSchema.safeParse(raw);
    if (!parsed.success) {
      return NextResponse.json(
        { error: 'Unexpected payload from orchestrator' },
        { status: 502 },
      );
    }
    return NextResponse.json(parsed.data);
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Status lookup failed' },
      { status: 502 },
    );
  }
}
