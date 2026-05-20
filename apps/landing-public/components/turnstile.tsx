'use client';

import { useEffect, useRef } from 'react';

interface TurnstileProps {
  onToken: (token: string) => void;
  siteKey?: string;
}

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        opts: { sitekey: string; callback: (token: string) => void },
      ) => string;
      reset: (id?: string) => void;
    };
  }
}

/**
 * Cloudflare Turnstile widget wrapper.
 *
 * If TURNSTILE_SITE_KEY is not configured, renders a dev placeholder that
 * still emits a synthetic token so the form can be exercised locally.
 */
export function Turnstile({ onToken, siteKey }: TurnstileProps) {
  const ref = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const key = siteKey || process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || '';

  useEffect(() => {
    if (!key) {
      // Dev fallback — emit synthetic token
      onToken('dev-bypass-token');
      return;
    }

    const id = 'cf-turnstile-script';
    if (!document.getElementById(id)) {
      const s = document.createElement('script');
      s.id = id;
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
      s.async = true;
      s.defer = true;
      document.head.appendChild(s);
    }

    const interval = setInterval(() => {
      if (window.turnstile && ref.current && !widgetId.current) {
        widgetId.current = window.turnstile.render(ref.current, {
          sitekey: key,
          callback: onToken,
        });
        clearInterval(interval);
      }
    }, 200);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!key) {
    return (
      <div className="rounded border border-dashed p-3 text-sm text-muted-foreground">
        Turnstile disabled (no NEXT_PUBLIC_TURNSTILE_SITE_KEY). Using dev token.
      </div>
    );
  }

  return <div ref={ref} className="cf-turnstile" />;
}
