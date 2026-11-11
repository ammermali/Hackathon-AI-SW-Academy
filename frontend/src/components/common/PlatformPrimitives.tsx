import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "accent" | "success" | "warning" | "danger";
  icon?: ReactNode;
}) {
  return (
    <div className={`stat-card stat-card-${tone}`}>
      <div className="stat-card-top">
        <span className="stat-card-label">{label}</span>
        {icon && <span className="stat-card-icon">{icon}</span>}
      </div>
      <div className="stat-card-value">{value}</div>
      {hint && <div className="stat-card-hint">{hint}</div>}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="progress-wrap">
      {label && (
        <div className="progress-label-row">
          <span>{label}</span>
          <span>{clamped.toFixed(0)}%</span>
        </div>
      )}
      <div className="progress-track" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress-fill" style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  return <span className={`ui-badge ui-badge-${tone}`}>{children}</span>;
}

export function LoadingState({ label = "Caricamento in corso..." }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <Loader2 size={20} className="spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="page-error-banner" role="alert">
      <div className="page-error-content">
        <AlertCircle size={17} aria-hidden="true" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <button type="button" className="retry-button" onClick={onRetry}>
          <RotateCcw size={14} aria-hidden="true" />
          <span>Riprova</span>
        </button>
      )}
    </div>
  );
}

export interface ChartPoint {
  label: string;
  value: number;
  sublabel?: string;
}

export function ScoreBarChart({
  title,
  points,
  emptyText = "Nessun dato sufficiente per mostrare l'andamento.",
}: {
  title: string;
  points: ChartPoint[];
  emptyText?: string;
}) {
  if (points.length === 0) {
    return (
      <div className="chart-card">
        <h3 className="chart-title">{title}</h3>
        <p className="chart-empty">{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <h3 className="chart-title">{title}</h3>
      <div className="bar-chart-grid" aria-label={title}>
        {points.map((pt, idx) => {
          const pct = Math.max(0, Math.min(100, pt.value));
          return (
            <div key={`${pt.label}-${idx}`} className="bar-chart-col" title={`${pt.label}: ${pct.toFixed(1)}%`}>
              <span className="bar-chart-val">{pct.toFixed(0)}%</span>
              <div className="bar-chart-track">
                <div className="bar-chart-bar" style={{ height: `${Math.max(4, pct)}%` }} />
              </div>
              <span className="bar-chart-label">{pt.label}</span>
              {pt.sublabel && <span className="bar-chart-sub">{pt.sublabel}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
