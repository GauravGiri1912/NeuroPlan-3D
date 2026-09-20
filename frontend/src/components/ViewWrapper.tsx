/**
 * NeuroPlan-3D — Generic View Wrapper
 *
 * Adds the standard view header (group label / title / subtitle) around
 * an existing panel component, without touching that panel's internals.
 * Used for panels that were previously mounted permanently in the old
 * always-on sidebars and now live behind a single nav destination.
 */
import type { ReactNode } from 'react';

export default function ViewWrapper({ group, title, subtitle, children }: {
  group: string;
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="view-content">
      <div className="view-header">
        <div className="text-label">{group}</div>
        <h1 className="view-title">{title}</h1>
        {subtitle && <div className="view-subtitle">{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}
