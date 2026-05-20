import { NextResponse } from 'next/server';
import { z } from 'zod';
import { callOrchestrator } from '@/lib/api';
import { intakeSchema, intakeResponseSchema } from '@/lib/schemas';

export const runtime = 'nodejs';

export async function POST(req: Request) {
  let parsed;
  try {
    const raw = await req.json();
    parsed = intakeSchema.safeParse(raw);
  } catch (e) {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  if (!parsed.success) {
    return NextResponse.json(
      { error: 'Validation failed', details: parsed.error.flatten() },
      { status: 400 },
    );
  }

  const fwd = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim();
  const sourceIp = fwd || req.headers.get('x-real-ip') || null;

  try {
    const result = await callOrchestrator({
      method: 'POST',
      path: '/v1/intake/submit',
      body: { ...parsed.data, source_ip: sourceIp },
      actor: 'landing-public',
    });
    const ok = intakeResponseSchema.safeParse(result);
    if (!ok.success) {
      return NextResponse.json(
        { error: 'Orchestrator returned unexpected payload' },
        { status: 502 },
      );
    }
    return NextResponse.json(ok.data, { status: 201 });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Orchestrator call failed' },
      { status: 502 },
    );
  }
}
