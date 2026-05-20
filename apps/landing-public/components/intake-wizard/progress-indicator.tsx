'use client';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  steps: string[];
  current: number;
}

export function ProgressIndicator({ steps, current }: Props) {
  return (
    <ol className="flex items-center w-full mb-8">
      {steps.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li
            key={label}
            className={cn(
              'flex w-full items-center',
              i < steps.length - 1 &&
                "after:content-[''] after:w-full after:h-1 after:border-b after:border-4 after:inline-block",
              done ? 'after:border-primary' : 'after:border-border',
            )}
          >
            <span
              className={cn(
                'flex items-center justify-center w-10 h-10 rounded-full shrink-0 text-sm font-semibold',
                done && 'bg-primary text-primary-foreground',
                active && 'bg-primary/20 text-primary border-2 border-primary',
                !done && !active && 'bg-secondary text-muted-foreground',
              )}
              title={label}
            >
              {done ? <Check className="w-5 h-5" /> : i + 1}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
