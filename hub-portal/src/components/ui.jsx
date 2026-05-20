import React from 'react';
import { tokens } from '../tokens.js';

export const StatusDot = ({ status }) => {
  const map = {
    healthy: tokens.ok,
    active: tokens.ok,
    degraded: tokens.warn,
    suspended: tokens.warn,
    down: tokens.err,
    archived: tokens.muted,
    maintenance: tokens.info,
    success: tokens.ok,
    failed: tokens.err,
  };
  const c = map[status] || tokens.muted;
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8, height: 8, borderRadius: '50%',
        background: c,
        boxShadow: `0 0 0 3px ${c}20`,
      }}
    />
  );
};

export const Pill = ({ children, tone = 'neutral' }) => {
  const toneMap = {
    neutral: { bg: '#F4F4F2', fg: '#52525B', bd: '#E7E5E2' },
    brand:   { bg: tokens.brandSoft, fg: tokens.brandDeep, bd: '#FACFD3' },
    accent:  { bg: tokens.accentSoft, fg: tokens.accentDeep, bd: '#BFC9F1' },
    ok:      { bg: '#D1FAE5', fg: '#065F46', bd: '#A7F3D0' },
    warn:    { bg: '#FEF3C7', fg: '#92400E', bd: '#FDE68A' },
    err:     { bg: '#FEE2E2', fg: '#991B1B', bd: '#FECACA' },
    info:    { bg: '#DBEAFE', fg: '#1E40AF', bd: '#BFDBFE' },
  };
  const t = toneMap[tone] || toneMap.neutral;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 999,
      background: t.bg, color: t.fg, border: `1px solid ${t.bd}`,
      fontSize: 11, fontWeight: 600, letterSpacing: 0.2, fontFamily: 'inherit',
      textTransform: 'uppercase',
    }}>{children}</span>
  );
};

export const Card = ({ children, style }) => (
  <div style={{
    background: '#fff', borderRadius: 12,
    border: `1px solid ${tokens.border}`,
    padding: 20, ...style,
  }}>{children}</div>
);

export const PageTitle = ({ title, subtitle, action }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 24 }}>
    <div>
      <h1 style={{
        fontFamily: 'Fraunces, serif', fontSize: 32, fontWeight: 600,
        margin: 0, letterSpacing: -0.5,
      }}>{title}</h1>
      {subtitle && <p style={{ color: tokens.muted, fontSize: 14, margin: '6px 0 0' }}>{subtitle}</p>}
    </div>
    {action}
  </div>
);

// Used to tag sections where the data is still seeded server-side (not yet
// wired to a real orchestrator/odoo endpoint).
export const DemoBadge = () => (
  <Pill tone="accent">Demo data</Pill>
);

// ---------------------------------------------------------------------------
// Generic primitives used by the TS admin pages (OnboardingPipeline / VPS / etc).
// ---------------------------------------------------------------------------
export const Badge = ({ children, color, tone }) => {
  // Tone is a Pill alias; color is a custom hex used by stage badges.
  if (color) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '3px 10px', borderRadius: 999,
        background: `${color}22`, color: color, border: `1px solid ${color}44`,
        fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
      }}>{children}</span>
    );
  }
  return <Pill tone={tone || 'neutral'}>{children}</Pill>;
};

export const Button = ({ children, onClick, variant = 'primary', size = 'md', type = 'button', disabled, style }) => {
  const variants = {
    primary:   { bg: tokens.brand, fg: '#fff', bd: tokens.brand },
    secondary: { bg: '#fff', fg: tokens.ink, bd: tokens.border },
    ghost:     { bg: 'transparent', fg: tokens.muted, bd: 'transparent' },
    danger:    { bg: tokens.err, fg: '#fff', bd: tokens.err },
  };
  const sizes = {
    sm: { p: '6px 10px', f: 11 },
    md: { p: '8px 14px', f: 12 },
    lg: { p: '10px 18px', f: 13 },
  };
  const v = variants[variant] || variants.primary;
  const s = sizes[size] || sizes.md;
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={{
      background: v.bg, color: v.fg, border: `1px solid ${v.bd}`,
      padding: s.p, borderRadius: 7, fontSize: s.f, fontWeight: 600,
      fontFamily: 'inherit', cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1, ...style,
    }}>{children}</button>
  );
};

// Transparent passthrough — onChange receives the native event so callers
// can write `(e) => setX(e.target.value)` (standard React DOM style).
export const Input = ({ style, ...rest }) => (
  <input
    {...rest}
    style={{
      background: '#fff', border: `1px solid ${tokens.border}`,
      borderRadius: 6, padding: '8px 12px', fontSize: 13,
      fontFamily: 'inherit', outline: 'none', width: '100%', ...style,
    }}
  />
);

export const Textarea = ({ style, rows = 4, ...rest }) => (
  <textarea
    rows={rows}
    {...rest}
    style={{
      background: '#fff', border: `1px solid ${tokens.border}`,
      borderRadius: 6, padding: '8px 12px', fontSize: 13,
      fontFamily: 'inherit', outline: 'none', width: '100%', resize: 'vertical', ...style,
    }}
  />
);

// Renders children (<option> elements) as standard <select>. Also supports
// an optional `options` array prop for callers that prefer the data form.
export const Select = ({ options, placeholder, style, children, ...rest }) => (
  <select
    {...rest}
    style={{
      background: '#fff', border: `1px solid ${tokens.border}`,
      borderRadius: 6, padding: '8px 12px', fontSize: 13,
      fontFamily: 'inherit', outline: 'none', width: '100%', ...style,
    }}
  >
    {placeholder && <option value="">{placeholder}</option>}
    {children}
    {options && options.map((opt) => {
      const v = typeof opt === 'object' ? opt.value : opt;
      const l = typeof opt === 'object' ? opt.label : opt;
      return <option key={v} value={v}>{l}</option>;
    })}
  </select>
);

export const Modal = ({ open, onClose, title, children, width = 600 }) => {
  if (!open) return null;
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 50,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: '#fff', borderRadius: 12, width: '90%', maxWidth: width,
        maxHeight: '90vh', overflow: 'auto', padding: 0,
      }}>
        {title && (
          <div style={{
            padding: '16px 24px', borderBottom: `1px solid ${tokens.border}`,
            fontSize: 16, fontWeight: 600,
          }}>{title}</div>
        )}
        <div style={{ padding: 24 }}>{children}</div>
      </div>
    </div>
  );
};

// Simple inline toast; pages call setToast({message, tone}) and render this.
export const Toast = ({ message, tone = 'info', onClose }) => {
  if (!message) return null;
  const toneMap = {
    success: { bg: '#D1FAE5', fg: '#065F46', bd: '#A7F3D0' },
    error:   { bg: '#FEE2E2', fg: '#991B1B', bd: '#FECACA' },
    info:    { bg: '#DBEAFE', fg: '#1E40AF', bd: '#BFDBFE' },
    warn:    { bg: '#FEF3C7', fg: '#92400E', bd: '#FDE68A' },
  };
  const t = toneMap[tone] || toneMap.info;
  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 100,
      background: t.bg, color: t.fg, border: `1px solid ${t.bd}`,
      padding: '10px 16px', borderRadius: 8, fontSize: 13,
      maxWidth: 360, boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
      cursor: onClose ? 'pointer' : 'default',
    }} onClick={onClose}>
      {message}
    </div>
  );
};

export const Spinner = ({ size = 16 }) => (
  <span style={{
    display: 'inline-block', width: size, height: size,
    border: `2px solid ${tokens.border}`,
    borderTopColor: tokens.brand,
    borderRadius: '50%',
    animation: 'spin 0.7s linear infinite',
  }}>
    <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
  </span>
);

export const Section = ({ title, action, children, style }) => (
  <section style={{ marginBottom: 24, ...style }}>
    {(title || action) && (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 12,
      }}>
        {title && <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0, color: tokens.ink }}>{title}</h3>}
        {action}
      </div>
    )}
    {children}
  </section>
);

export const Tabs = ({ tabs = [], active, onChange, children }) => (
  <div>
    <div style={{
      display: 'flex', gap: 2, borderBottom: `1px solid ${tokens.border}`,
      marginBottom: 16,
    }}>
      {tabs.map((t) => {
        const id = typeof t === 'object' ? t.id : t;
        const label = typeof t === 'object' ? t.label : t;
        const isActive = active === id;
        return (
          <button key={id} onClick={() => onChange && onChange(id)} style={{
            background: 'transparent', border: 'none', borderBottom: `2px solid ${isActive ? tokens.brand : 'transparent'}`,
            padding: '10px 14px', fontSize: 12, fontWeight: isActive ? 600 : 500,
            color: isActive ? tokens.ink : tokens.muted,
            fontFamily: 'inherit', cursor: 'pointer', marginBottom: -1,
          }}>{label}</button>
        );
      })}
    </div>
    {children}
  </div>
);

export const Table = ({ columns = [], data = [], onRowClick, emptyMessage = 'No records.' }) => (
  <div style={{ background: '#fff', borderRadius: 8, border: `1px solid ${tokens.border}`, overflow: 'hidden' }}>
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr style={{ background: tokens.surfaceAlt }}>
          {columns.map((c) => (
            <th key={c.key} style={{
              textAlign: 'left', padding: '10px 14px',
              fontSize: 11, color: tokens.muted, fontWeight: 600,
              textTransform: 'uppercase', letterSpacing: 0.4,
              borderBottom: `1px solid ${tokens.border}`,
            }}>{c.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.length === 0 ? (
          <tr><td colSpan={columns.length} style={{ padding: 24, textAlign: 'center', color: tokens.muted }}>
            {emptyMessage}
          </td></tr>
        ) : data.map((row, i) => (
          <tr
            key={row.id || i}
            onClick={() => onRowClick && onRowClick(row)}
            style={{
              cursor: onRowClick ? 'pointer' : 'default',
              borderBottom: `1px solid ${tokens.border}`,
            }}
          >
            {columns.map((c) => (
              <td key={c.key} style={{ padding: '10px 14px' }}>
                {c.render ? c.render(row) : row[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const ErajayaMark = ({ size = 36 }) => (
  // Stylised Erajaya logomark: red square with a navy swoosh + red dot,
  // approximating the corporate logo so the brand is recognisable even
  // before the official asset is dropped into /public.
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    <rect width="64" height="64" rx="12" fill={tokens.brand} />
    <path d="M14 38 Q32 18 50 28" stroke={tokens.accent} strokeWidth="5" fill="none" strokeLinecap="round" />
    <circle cx="50" cy="28" r="4" fill={tokens.brand} stroke="#fff" strokeWidth="1.5" />
    <text x="32" y="52" textAnchor="middle" fontFamily="Fraunces, serif" fontWeight="800" fontSize="22" fill="#fff">E</text>
  </svg>
);
