/**
 * NeuroPlan-3D — Primary Navigation Sidebar
 *
 * Groups the application's existing workspaces so only one is visible at
 * a time. Every destination below renders an EXISTING panel component
 * (several reused across more than one destination, e.g. Buckling and
 * IS 800 both open the same Engineering Analysis panel at a different
 * section) — nothing here changes what data is fetched or computed.
 */
import { useAppStore, type NavView } from '../stores/appStore';

interface NavItem {
  id: NavView;
  label: string;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Core',
    items: [
      { id: 'overview', label: 'Overview' },
      { id: 'setup', label: 'New Analysis' },
      { id: 'model', label: 'Model' },
      { id: 'results', label: 'Results' },
      { id: 'checks', label: 'Checks' },
    ],
  },
  {
    title: 'Structural Investigation',
    items: [
      { id: 'failure-lab', label: 'Failure Lab' },
      { id: 'compare', label: 'Compare' },
      { id: 'robustness', label: 'Robustness' },
    ],
  },
  {
    title: 'Engineering Analysis',
    items: [
      { id: 'load-cases', label: 'Load Cases' },
      { id: 'diagnostics', label: 'Diagnostics' },
      { id: 'sensitivity', label: 'Sensitivity' },
      { id: 'buckling', label: 'Buckling' },
      { id: 'is800', label: 'IS 800' },
      { id: 'advanced', label: 'Advanced Analysis' },
    ],
  },
  {
    title: 'Evidence',
    items: [
      { id: 'validation', label: 'Validation' },
      { id: 'engineering-evidence', label: 'Engineering Evidence' },
      { id: 'report', label: 'Report' },
    ],
  },
];

export default function NavSidebar() {
  const activeNavView = useAppStore((s) => s.activeNavView);
  const setActiveNavView = useAppStore((s) => s.setActiveNavView);

  return (
    <nav className="nav-sidebar">
      {NAV_GROUPS.map((group) => (
        <div className="nav-group" key={group.title}>
          <div className="nav-group-title">{group.title}</div>
          {group.items.map((item) => (
            <button
              key={item.id}
              className={`nav-item${activeNavView === item.id ? ' active' : ''}`}
              onClick={() => setActiveNavView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ))}
    </nav>
  );
}
