import React from 'react';
import { tokens } from '../tokens.js';

interface Props {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '64px 32px',
        background: '#fff',
        borderRadius: 12,
        border: `1px dashed ${tokens.border}`,
        textAlign: 'center',
      }}
    >
      {icon && <div style={{ marginBottom: 16, color: tokens.muted }}>{icon}</div>}
      <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0, color: tokens.ink }}>{title}</h3>
      {description && (
        <p style={{ fontSize: 13, color: tokens.muted, margin: '8px 0 16px', maxWidth: 400 }}>
          {description}
        </p>
      )}
      {action}
    </div>
  );
}
