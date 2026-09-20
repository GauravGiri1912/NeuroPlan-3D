/**
 * NeuroPlan-3D — Color Scale Utilities
 *
 * Maps stress ratios to colors for viewport visualization.
 * Engineering convention: Blue (safe) → Green → Yellow → Red (critical)
 */
import * as THREE from 'three';

/**
 * Convert a stress ratio (0.0 – 1.0+) to an RGB color.
 *
 * 0.0       → Blue (#3b82f6)  — no stress
 * 0.0 – 0.5 → Blue to Green
 * 0.5 – 0.8 → Green to Yellow
 * 0.8 – 1.0 → Yellow to Red
 * > 1.0     → Bright Red (#ef4444) — failure
 */
export function stressRatioToColor(ratio: number): THREE.Color {
  const r = Math.max(0, Math.min(ratio, 1.5));

  if (r <= 0.01) {
    // Near zero — dim blue-grey
    return new THREE.Color(0.35, 0.45, 0.55);
  } else if (r <= 0.5) {
    // Blue → Green
    const t = r / 0.5;
    return new THREE.Color(
      0.23 * (1 - t) + 0.13 * t,
      0.51 * (1 - t) + 0.72 * t,
      0.96 * (1 - t) + 0.30 * t,
    );
  } else if (r <= 0.8) {
    // Green → Yellow
    const t = (r - 0.5) / 0.3;
    return new THREE.Color(
      0.13 * (1 - t) + 0.96 * t,
      0.72 * (1 - t) + 0.62 * t,
      0.30 * (1 - t) + 0.04 * t,
    );
  } else {
    // Yellow → Red
    const t = Math.min((r - 0.8) / 0.2, 1.0);
    return new THREE.Color(
      0.96 * (1 - t) + 0.94 * t,
      0.62 * (1 - t) + 0.27 * t,
      0.04 * (1 - t) + 0.27 * t,
    );
  }
}

/**
 * Convert a stress ratio to a CSS hex color string.
 */
export function stressRatioToHex(ratio: number): string {
  const color = stressRatioToColor(ratio);
  return '#' + color.getHexString();
}

/**
 * Get a status color for pass/fail/warning indicators.
 */
export function statusColor(status: 'ok' | 'overstressed' | 'buckling_risk' | string): string {
  switch (status) {
    case 'ok': return '#22c55e';
    case 'overstressed': return '#ef4444';
    case 'buckling_risk': return '#f59e0b';
    default: return '#8b919e';
  }
}

/**
 * Wireframe color — neutral grey
 */
export const WIREFRAME_COLOR = new THREE.Color(0.55, 0.58, 0.65);

/**
 * Node color — light accent
 */
export const NODE_COLOR = new THREE.Color(0.75, 0.78, 0.85);

/**
 * Support color — teal
 */
export const SUPPORT_COLOR = new THREE.Color(0.08, 0.72, 0.65);

/**
 * Load arrow color — warning amber
 */
export const LOAD_COLOR = new THREE.Color(0.96, 0.62, 0.04);

/**
 * Highlighted member color — bright accent
 */
export const HIGHLIGHT_COLOR = new THREE.Color(0.23, 0.51, 0.96);
