import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function HomePage() {
  return (
    <div className="space-y-16">
      <section className="text-center space-y-6 py-16">
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight">
          Spin up your vertical on our Odoo platform
        </h1>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Submit your business profile, target vertical, and BRD. Our BA team
          reviews and the platform provisions automatically.
        </p>
        <div className="flex justify-center gap-4">
          <Link href="/intake">
            <Button size="lg">Onboard New Vertical</Button>
          </Link>
        </div>
      </section>

      <section className="grid md:grid-cols-3 gap-6">
        {[
          { t: '1. Intake', d: 'Tell us about your company and modules you need.' },
          { t: '2. BA Review', d: 'BRD analysis + cross-vertical impact assessment.' },
          { t: '3. Go Live', d: 'VPS provisioned, modules deployed, UAT, then live.' },
        ].map((s) => (
          <div key={s.t} className="rounded-lg border p-6">
            <h3 className="font-semibold mb-2">{s.t}</h3>
            <p className="text-sm text-muted-foreground">{s.d}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
