import React from 'react';
import { AlertCircle } from 'lucide-react';
import { tokens } from '../tokens.js';

interface Props {
  feature: string;
  hint?: string;
}

export default function ConfigRequiredBanner({ feature, hint }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        padding: 16,
        background: '#FEF3C7',
        border: `1px solid #FDE68A`,
        borderRadius: 8,
        marginBottom: 16,
        color: '#92400E',
      }}
    >
      <AlertCircle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
      <div>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{feature} requires configuration</div>
        {hint && <div style={{ fontSize: 12, marginTop: 4 }}>{hint}</div>}
      </div>
    </div>
  );
}
