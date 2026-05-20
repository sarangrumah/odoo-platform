// Shared UI primitives. Keeps the bundle small (no full UI lib).
// TODO: tighten types where any used.
import React, { CSSProperties, ReactNode } from 'react';
import { colors, radii, shadows, spacing } from '../tokens';

type DivProps = React.HTMLAttributes<HTMLDivElement>;
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

export function Card({
  children,
  style,
  padded = true,
  ...rest
}: DivProps & { padded?: boolean }) {
  return (
    <div
      style={{
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radii.lg,
        padding: padded ? spacing.lg : 0,
        boxShadow: shadows.sm,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  style,
  ...rest
}: BtnProps & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}) {
  const bg = {
    primary: colors.accent,
    secondary: colors.surfaceMuted,
    ghost: 'transparent',
    danger: colors.danger,
  }[variant];
  const fg = variant === 'ghost' ? colors.text : '#fff';
  const padX = size === 'sm' ? 10 : size === 'lg' ? 22 : 14;
  const padY = size === 'sm' ? 6 : size === 'lg' ? 12 : 8;
  return (
    <button
      style={{
        background: bg,
        color: fg,
        border:
          variant === 'secondary' || variant === 'ghost'
            ? `1px solid ${colors.border}`
            : 'none',
        borderRadius: radii.md,
        padding: `${padY}px ${padX}px`,
        cursor: 'pointer',
        fontSize: size === 'sm' ? 12 : 14,
        fontWeight: 600,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        transition: 'opacity 0.15s',
        ...style,
      }}
      onMouseDown={(e) => (e.currentTarget.style.opacity = '0.8')}
      onMouseUp={(e) => (e.currentTarget.style.opacity = '1')}
      onMouseLeave={(e) => (e.currentTarget.style.opacity = '1')}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        color: colors.text,
        borderRadius: radii.md,
        padding: '8px 12px',
        fontSize: 14,
        outline: 'none',
        width: '100%',
        ...props.style,
      }}
    />
  );
}

export function Textarea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
) {
  return (
    <textarea
      {...props}
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        color: colors.text,
        borderRadius: radii.md,
        padding: '8px 12px',
        fontSize: 14,
        outline: 'none',
        width: '100%',
        minHeight: 100,
        fontFamily: 'inherit',
        resize: 'vertical',
        ...props.style,
      }}
    />
  );
}

export function Select({
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        color: colors.text,
        borderRadius: radii.md,
        padding: '8px 12px',
        fontSize: 14,
        outline: 'none',
        ...rest.style,
      }}
    >
      {children}
    </select>
  );
}

export function Badge({
  children,
  tone = 'default',
  style,
}: {
  children: ReactNode;
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  style?: CSSProperties;
}) {
  const bg = {
    default: colors.surfaceMuted,
    success: 'rgba(34,197,94,0.15)',
    warning: 'rgba(245,158,11,0.15)',
    danger: 'rgba(239,68,68,0.15)',
    info: 'rgba(59,130,246,0.15)',
  }[tone];
  const fg = {
    default: colors.textMuted,
    success: colors.success,
    warning: colors.warning,
    danger: colors.danger,
    info: colors.info,
  }[tone];
  return (
    <span
      style={{
        background: bg,
        color: fg,
        padding: '2px 8px',
        borderRadius: radii.pill,
        fontSize: 11,
        fontWeight: 600,
        display: 'inline-block',
        ...style,
      }}
    >
      {children}
    </span>
  );
}

export function Modal({
  open,
  onClose,
  children,
  title,
  width = 720,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: string;
  width?: number;
}) {
  if (!open) return null;
  return (
    <div
      role="dialog"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: spacing.lg,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: colors.surface,
          border: `1px solid ${colors.border}`,
          borderRadius: radii.lg,
          width: '100%',
          maxWidth: width,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: shadows.lg,
        }}
      >
        {title && (
          <div
            style={{
              padding: spacing.lg,
              borderBottom: `1px solid ${colors.border}`,
              fontWeight: 700,
              fontSize: 16,
            }}
          >
            {title}
          </div>
        )}
        <div style={{ padding: spacing.lg }}>{children}</div>
      </div>
    </div>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div style={{ marginBottom: spacing.xl }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          marginBottom: spacing.md,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 20 }}>{title}</h2>
          {description && (
            <p style={{ margin: '4px 0 0', color: colors.textMuted, fontSize: 13 }}>
              {description}
            </p>
          )}
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

export function Table({
  columns,
  rows,
  empty = 'No rows',
}: {
  columns: { key: string; label: string; render?: (row: any) => ReactNode; width?: number | string }[];
  rows: any[];
  empty?: string;
}) {
  return (
    <div
      style={{
        border: `1px solid ${colors.border}`,
        borderRadius: radii.md,
        overflow: 'hidden',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead style={{ background: colors.surfaceMuted }}>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={{
                  textAlign: 'left',
                  padding: '10px 12px',
                  color: colors.textMuted,
                  fontWeight: 600,
                  fontSize: 11,
                  textTransform: 'uppercase',
                  width: c.width,
                }}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  padding: spacing.xl,
                  textAlign: 'center',
                  color: colors.textDim,
                }}
              >
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((r, i) => (
              <tr
                key={r.id ?? i}
                style={{
                  borderTop: `1px solid ${colors.border}`,
                  background: i % 2 ? colors.surface : 'transparent',
                }}
              >
                {columns.map((c) => (
                  <td key={c.key} style={{ padding: '10px 12px' }}>
                    {c.render ? c.render(r) : r[c.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string; icon?: ReactNode }[];
  active: string;
  onChange: (k: string) => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        gap: spacing.xs,
        borderBottom: `1px solid ${colors.border}`,
        marginBottom: spacing.lg,
      }}
    >
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            background: 'transparent',
            color: active === t.key ? colors.text : colors.textMuted,
            border: 'none',
            borderBottom:
              active === t.key
                ? `2px solid ${colors.accent}`
                : '2px solid transparent',
            padding: '10px 14px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Toast({ msg, tone = 'success' }: { msg: string; tone?: 'success' | 'danger' | 'info' }) {
  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderLeft: `4px solid ${tone === 'success' ? colors.success : tone === 'danger' ? colors.danger : colors.info}`,
        borderRadius: radii.md,
        padding: '12px 16px',
        boxShadow: shadows.lg,
        zIndex: 1100,
        minWidth: 280,
      }}
    >
      {msg}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div
      style={{
        padding: spacing.xxl,
        textAlign: 'center',
        color: colors.textMuted,
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      {hint && <div style={{ fontSize: 13, color: colors.textDim }}>{hint}</div>}
    </div>
  );
}
