import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { CheckCircle, Info, Warning, XCircle } from '@phosphor-icons/react';
import type { Tone } from '../api/types';

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const lowered = status.toLowerCase();
  const tone: Tone = lowered.includes('ready') || lowered.includes('complete') || lowered.includes('valid') || lowered.includes('observed') || lowered.includes('tested')
    ? 'success'
    : lowered.includes('high') || lowered.includes('error') || lowered.includes('attention')
      ? 'danger'
      : lowered.includes('partial') || lowered.includes('deferred') || lowered.includes('review') || lowered.includes('assumption')
        ? 'warning'
        : lowered.includes('active') || lowered.includes('running') || lowered.includes('fact')
          ? 'accent'
          : 'neutral';
  return <Badge tone={tone}>{status}</Badge>;
}

export function Button({ variant = 'secondary', icon, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; icon?: ReactNode }) {
  return <button className={`button button--${variant}`} {...props}>{icon}{children}</button>;
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function PanelHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="panel-header"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>;
}

export function Notice({ tone = 'info', title, children }: { tone?: 'info' | 'warning' | 'success' | 'danger'; title: string; children: ReactNode }) {
  const Icon = tone === 'warning' ? Warning : tone === 'success' ? CheckCircle : tone === 'danger' ? XCircle : Info;
  return <div className={`notice notice--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}><Icon size={18} weight="fill" aria-hidden="true" /><div><strong>{title}</strong><p>{children}</p></div></div>;
}

export function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return <fieldset className="segmented"><legend className="sr-only">{label}</legend>{options.map(option => <button type="button" key={option.value} className={value === option.value ? 'is-active' : ''} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</fieldset>;
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-state__mark" aria-hidden="true" /><h3>{title}</h3><p>{children}</p>{action}</div>;
}

export function Progress({ value, label }: { value: number; label: string }) {
  return <div className="progress" aria-label={label}><div className="progress__meta"><span>{label}</span><strong>{value}%</strong></div><div className="progress__track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}><span style={{ width: `${value}%` }} /></div></div>;
}

export function SkeletonPage() {
  return <div className="skeleton-page" aria-label="Loading workspace" aria-busy="true"><div className="skeleton skeleton--title"/><div className="metric-grid">{[1,2,3,4].map(item => <div className="skeleton skeleton--card" key={item}/>)}</div><div className="skeleton skeleton--panel"/></div>;
}
