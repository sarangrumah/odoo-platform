import { notFound } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { callOrchestrator } from '@/lib/api';
import { statusResponseSchema, type StatusResponse } from '@/lib/schemas';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const STAGE_TIMELINE = [
  'intake',
  'brd_uploaded',
  'brd_analyzed',
  'go_no_go',
  'vps_assigned',
  'provisioning',
  'modules_deploying',
  'uat',
  'go_live',
  'closed',
];

async function fetchStatus(token: string): Promise<StatusResponse | null> {
  try {
    const raw = await callOrchestrator({
      method: 'GET',
      path: `/v1/intake/${encodeURIComponent(token)}/status`,
    });
    const parsed = statusResponseSchema.safeParse(raw);
    if (!parsed.success) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

export default async function StatusPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const status = await fetchStatus(token);
  if (!status) notFound();

  const stageIndex = STAGE_TIMELINE.indexOf(status.stage);
  const progress =
    typeof status.progress_pct === 'number'
      ? status.progress_pct
      : Math.max(0, Math.round(((stageIndex + 1) / STAGE_TIMELINE.length) * 100));

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Onboarding Status</CardTitle>
          <CardDescription>
            Token: <code className="text-xs">{token}</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center gap-3">
            <Badge variant="default">{status.stage}</Badge>
            <Badge variant="outline">{status.status}</Badge>
            {status.target_go_live && (
              <span className="text-sm text-muted-foreground">
                Target Go-Live: {status.target_go_live}
              </span>
            )}
          </div>

          <div>
            <div className="flex justify-between text-sm mb-2">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <Progress value={progress} />
          </div>

          <ol className="space-y-2">
            {STAGE_TIMELINE.map((stage, i) => {
              const done = stageIndex >= 0 && i <= stageIndex;
              const current = i === stageIndex;
              return (
                <li
                  key={stage}
                  className={`flex items-center gap-3 text-sm ${
                    done ? 'text-foreground' : 'text-muted-foreground'
                  }`}
                >
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                      done ? 'bg-primary text-primary-foreground' : 'bg-secondary'
                    } ${current ? 'ring-2 ring-primary' : ''}`}
                  >
                    {i + 1}
                  </span>
                  <span className="font-mono">{stage}</span>
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
