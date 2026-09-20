/**
 * NeuroPlan-3D — 3D Structural Viewport
 *
 * React Three Fiber canvas rendering the truss structure with:
 * - Nodes as spheres
 * - Members as cylinders (colored by stress ratio)
 * - Support symbols
 * - Load arrows
 * - Orbit controls
 * - Grid and coordinate axes
 */
import { useRef, useMemo, useEffect } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls, Grid, Line, Text } from '@react-three/drei';
import * as THREE from 'three';
import { useAppStore } from '../stores/appStore';
import {
  stressRatioToColor, WIREFRAME_COLOR, NODE_COLOR,
  SUPPORT_COLOR, LOAD_COLOR, HIGHLIGHT_COLOR,
} from '../utils/colorScales';
import type { NodeData, MemberData, MemberResultData } from '../types/engineering';

// ─── Main Viewport Component ───

export default function StructuralViewport() {
  const structure = useAppStore((s) => s.currentStructure());
  const results = useAppStore((s) => s.currentResults());
  const displayMode = useAppStore((s) => s.displayMode);
  const showLoads = useAppStore((s) => s.showLoads);
  const showSupports = useAppStore((s) => s.showSupports);
  const showLabels = useAppStore((s) => s.showLabels);
  const showDeformed = useAppStore((s) => s.showDeformed);
  const deformationScale = useAppStore((s) => s.deformationScale);
  const visibility = useAppStore((s) => s.visibility);

  return (
    <Canvas
      camera={{ position: [15, 8, 12], fov: 45, near: 0.1, far: 500 }}
      gl={{ antialias: true, alpha: false }}
      style={{ background: '#12141a' }}
    >
      <color attach="background" args={['#12141a']} />

      {/* Lighting */}
      <ambientLight intensity={0.6} />
      <directionalLight position={[20, 20, 10]} intensity={0.8} />
      <directionalLight position={[-10, 10, -10]} intensity={0.3} />

      {/* Controls */}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.1}
        minDistance={2}
        maxDistance={600}
      />

      {/* Frame the camera to the structure's actual extents. Without this a
          24 m space truss overflows the viewport at the default camera
          distance, and the Z depth of a spatial structure is not visible. */}
      <CameraRig structure={structure} />

      {/* Grid */}
      {visibility.grid && <Grid
        args={[100, 100]}
        position={[0, -0.01, 0]}
        cellSize={1}
        cellThickness={0.5}
        cellColor="#1e2028"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#282c35"
        fadeDistance={60}
        fadeStrength={1.5}
        infiniteGrid
      />}

      {/* Coordinate Axes */}
      {visibility.axes && <CoordinateAxes />}

      {/* Structure */}
      {structure && (
        <StructureGroup
          structure={structure}
          results={results}
          displayMode={displayMode}
          showLoads={showLoads}
          showSupports={showSupports}
          showLabels={showLabels}
          showDeformed={showDeformed}
          deformationScale={deformationScale}
          visibility={visibility}
        />
      )}
    </Canvas>
  );
}

// ─── Camera Rig ───

/**
 * Fits the camera to the structure whenever its extents change.
 *
 * The structure group is centred on the origin, so only the bounding-box
 * size matters. For a SPATIAL structure the camera is placed off-axis so
 * the Z depth is immediately visible rather than hidden edge-on; a planar
 * structure is viewed from a shallower angle since it has no depth to show.
 */
function CameraRig({ structure }: { structure: { nodes: NodeData[] } | null }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as { target: THREE.Vector3; update: () => void } | null;

  // Extents, rounded so tiny numeric drift between repair iterations
  // doesn't retrigger the framing and yank the user's view around.
  const extents = useMemo(() => {
    if (!structure || structure.nodes.length === 0) return null;
    const xs = structure.nodes.map((n) => n.x);
    const ys = structure.nodes.map((n) => n.y);
    const zs = structure.nodes.map((n) => n.z);
    return {
      sx: Math.round(Math.max(...xs) - Math.min(...xs)),
      sy: Math.round(Math.max(...ys) - Math.min(...ys)),
      sz: Math.round(Math.max(...zs) - Math.min(...zs)),
    };
  }, [structure]);

  const key = extents ? `${extents.sx}-${extents.sy}-${extents.sz}` : 'none';

  useEffect(() => {
    if (!extents) return;
    const { sx, sy, sz } = extents;
    const radius = Math.max(Math.sqrt(sx * sx + sy * sy + sz * sz) / 2, 1);

    // Distance that fits the bounding sphere in the vertical FOV, with margin.
    const fov = ((camera as THREE.PerspectiveCamera).fov ?? 45) * (Math.PI / 180);
    const distance = (radius / Math.sin(fov / 2)) * 1.35;

    const isSpatial = sz > 0.5;
    // Direction chosen to reveal depth for spatial structures.
    const dir = isSpatial
      ? new THREE.Vector3(0.75, 0.45, 0.85).normalize()
      : new THREE.Vector3(0.55, 0.35, 1.0).normalize();

    camera.position.copy(dir.multiplyScalar(distance));
    camera.near = Math.max(distance / 1000, 0.1);
    camera.far = distance * 10;
    camera.updateProjectionMatrix();
    camera.lookAt(0, 0, 0);

    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
    // `key` collapses the extents into a primitive so this runs only when the
    // structure's actual size changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, camera, controls]);

  return null;
}

// ─── Coordinate Axes ───

function CoordinateAxes() {
  return (
    <group>
      <Line points={[[0, 0, 0], [2, 0, 0]]} color="#ef4444" lineWidth={2} />
      <Line points={[[0, 0, 0], [0, 2, 0]]} color="#22c55e" lineWidth={2} />
      <Line points={[[0, 0, 0], [0, 0, 2]]} color="#3b82f6" lineWidth={2} />
      <Text position={[2.3, 0, 0]} fontSize={0.3} color="#ef4444" anchorX="center">X</Text>
      <Text position={[0, 2.3, 0]} fontSize={0.3} color="#22c55e" anchorX="center">Y</Text>
      <Text position={[0, 0, 2.3]} fontSize={0.3} color="#3b82f6" anchorX="center">Z</Text>
    </group>
  );
}

// ─── Structure Group ───

interface StructureGroupProps {
  structure: ReturnType<typeof useAppStore.getState>['iterations'][0]['structure'];
  results: ReturnType<typeof useAppStore.getState>['iterations'][0]['results'] | null;
  displayMode: string;
  showLoads: boolean;
  showSupports: boolean;
  showLabels: boolean;
  showDeformed: boolean;
  deformationScale: number;
  visibility: ReturnType<typeof useAppStore.getState>['visibility'];
}

function StructureGroup({
  structure, results, displayMode,
  showLoads, showSupports, showLabels,
  showDeformed, deformationScale, visibility,
}: StructureGroupProps) {
  const hoveredId = useAppStore((s) => s.hoveredMemberId);
  const setHovered = useAppStore((s) => s.setHoveredMember);
  const setSelected = useAppStore((s) => s.setSelectedMember);
  const inspect = useAppStore((s) => s.inspect);
  const tracedNodeId = useAppStore((s) => s.tracedLoadNodeId);
  const evidence = useAppStore((s) => s.evidence);
  const failureLabMemberId = useAppStore((s) => s.failureLabMemberId);

  // Members carrying the currently traced load, from the backend's load-path
  // evidence — not re-derived here.
  const tracedMemberIds = useMemo(() => {
    if (tracedNodeId === null || !evidence) return new Set<number>();
    const path = evidence.load_paths.find((p) => p.node_id === tracedNodeId);
    return new Set<number>(path ? path.members.map((m) => m.member_id) : []);
  }, [tracedNodeId, evidence]);

  const nodeMap = useMemo(() => {
    const map: Record<number, NodeData> = {};
    structure.nodes.forEach((n) => { map[n.id] = n; });
    return map;
  }, [structure.nodes]);

  const memberResultMap = useMemo(() => {
    if (!results) return {};
    const map: Record<number, MemberResultData> = {};
    results.member_results.forEach((r) => { map[r.member_id] = r; });
    return map;
  }, [results]);

  const nodeResultMap = useMemo(() => {
    if (!results) return {};
    const map: Record<number, { dx: number; dy: number; dz: number; total_displacement_mm: number }> = {};
    results.node_results.forEach((r) => { map[r.node_id] = r; });
    return map;
  }, [results]);

  const maxNodeDisplacement = useMemo(() => {
    if (!results || results.node_results.length === 0) return 0;
    return Math.max(...results.node_results.map((r) => r.total_displacement_mm));
  }, [results]);

  // Center the structure in the viewport
  const center = useMemo(() => {
    if (structure.nodes.length === 0) return [0, 0, 0] as [number, number, number];
    const xs = structure.nodes.map((n) => n.x);
    const ys = structure.nodes.map((n) => n.y);
    const zs = structure.nodes.map((n) => n.z);
    return [
      (Math.min(...xs) + Math.max(...xs)) / 2,
      (Math.min(...ys) + Math.max(...ys)) / 2,
      (Math.min(...zs) + Math.max(...zs)) / 2,
    ] as [number, number, number];
  }, [structure.nodes]);

  return (
    <group position={[-center[0], -center[1], -center[2]]}>
      {/* Members */}
      {visibility.members && structure.members.map((member) => {
        const ni = nodeMap[member.node_i];
        const nj = nodeMap[member.node_j];
        if (!ni || !nj) return null;

        const mr = memberResultMap[member.id];
        let color: THREE.Color;

        if (displayMode === 'stress' && mr) {
          color = stressRatioToColor(mr.stress_ratio);
        } else if (displayMode === 'displacement' && results && maxNodeDisplacement > 1e-9) {
          const di = nodeResultMap[member.node_i];
          const dj = nodeResultMap[member.node_j];
          const avgDisp = di && dj ? (di.total_displacement_mm + dj.total_displacement_mm) / 2 : 0;
          color = stressRatioToColor(avgDisp / maxNodeDisplacement);
        } else if (displayMode === 'failure' && mr) {
          color = mr.status === 'ok'
            ? new THREE.Color(0.13, 0.77, 0.37)
            : new THREE.Color(0.94, 0.27, 0.27);
        } else {
          color = WIREFRAME_COLOR.clone();
        }

        const isTraced = tracedMemberIds.has(member.id);
        if (isTraced) color = new THREE.Color(0.96, 0.62, 0.04); // amber load path

        const isFailureLabTarget = failureLabMemberId === member.id;
        if (isFailureLabTarget) color = new THREE.Color(0.86, 0.15, 0.86); // magenta — Failure Lab focus

        const isHovered = hoveredId === member.id;
        if (isHovered) color = HIGHLIGHT_COLOR.clone();

        return (
          <MemberCylinder
            key={member.id}
            nodeI={ni}
            nodeJ={nj}
            color={color}
            radius={isHovered ? 0.08 : isFailureLabTarget ? 0.08 : isTraced ? 0.075 : 0.05}
            onHover={(h) => setHovered(h ? member.id : null)}
            onClick={() => { setSelected(member.id); inspect('member', member.id); }}
          />
        );
      })}

      {/* Nodes */}
      {visibility.nodes && structure.nodes.map((node) => (
        <mesh
          key={node.id}
          position={[node.x, node.y, node.z]}
          onClick={(e) => { e.stopPropagation(); inspect('node', node.id); }}
          onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = 'pointer'; }}
          onPointerOut={() => { document.body.style.cursor = 'auto'; }}
        >
          <sphereGeometry args={[node.id === tracedNodeId ? 0.22 : 0.12, 12, 12]} />
          <meshStandardMaterial
            color={node.id === tracedNodeId ? new THREE.Color(0.96, 0.62, 0.04) : NODE_COLOR}
          />
        </mesh>
      ))}

      {/* Node labels */}
      {showLabels && structure.nodes.map((node) => (
        <Text
          key={`label-${node.id}`}
          position={[node.x, node.y + 0.35, node.z]}
          fontSize={0.22}
          color="#8b919e"
          anchorX="center"
          anchorY="bottom"
        >
          {node.id}
        </Text>
      ))}

      {/* Supports */}
      {visibility.supports && showSupports && structure.supports.map((sup) => {
        const node = nodeMap[sup.node_id];
        if (!node) return null;
        return (
          <SupportSymbol
            key={`sup-${sup.node_id}`}
            position={[node.x, node.y, node.z]}
            type={sup.support_type}
          />
        );
      })}

      {/* Loads */}
      {visibility.loads && showLoads && structure.loads.map((load, i) => {
        const node = nodeMap[load.node_id];
        if (!node) return null;
        return (
          <LoadArrow
            key={`load-${i}`}
            position={[node.x, node.y, node.z]}
            fx={load.fx}
            fy={load.fy}
            fz={load.fz}
          />
        );
      })}

      {/* Reaction vectors — drawn from solver-recovered reactions */}
      {visibility.reactions && results && results.reactions.map((r) => {
        const n = nodeMap[r.node_id];
        const mag = Math.sqrt(r.rx * r.rx + r.ry * r.ry + r.rz * r.rz);
        if (!n || mag < 1e-6) return null;
        const dir = new THREE.Vector3(r.rx, r.ry, r.rz).normalize();
        const len = 1.2;
        const tip = new THREE.Vector3(n.x, n.y, n.z).add(dir.clone().multiplyScalar(len));
        return (
          <group key={`rx-${r.node_id}`}>
            <Line
              points={[[n.x, n.y, n.z], [tip.x, tip.y, tip.z]]}
              color="#22c55e"
              lineWidth={2.5}
            />
            <Text
              position={[tip.x, tip.y + 0.25, tip.z]}
              fontSize={0.22}
              color="#22c55e"
              anchorX="center"
            >
              {`${(mag / 1000).toFixed(1)} kN`}
            </Text>
          </group>
        );
      })}

      {/* Failure locations — from the solver's diagnosis, not inferred */}
      {visibility.failures && results && results.diagnosis.failures.map((f, i) => {
        let pos: [number, number, number] | null = null;
        if (f.member_id != null) {
          const m = structure.members.find((mm) => mm.id === f.member_id);
          if (m) {
            const a = nodeMap[m.node_i], b = nodeMap[m.node_j];
            if (a && b) pos = [(a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2];
          }
        } else if (f.node_id != null) {
          const n = nodeMap[f.node_id];
          if (n) pos = [n.x, n.y, n.z];
        }
        if (!pos) return null;
        return (
          <mesh key={`fail-${i}`} position={pos}>
            <sphereGeometry args={[0.28, 12, 12]} />
            <meshStandardMaterial color="#ef4444" transparent opacity={0.55} />
          </mesh>
        );
      })}

      {/* Deformed shape overlay */}
      {showDeformed && results && (
        <DeformedOverlay
          structure={structure}
          nodeResultMap={nodeResultMap}
          scale={deformationScale}
        />
      )}
    </group>
  );
}

// ─── Member Cylinder ───

interface MemberCylinderProps {
  nodeI: NodeData;
  nodeJ: NodeData;
  color: THREE.Color;
  radius: number;
  onHover: (hovered: boolean) => void;
  onClick: () => void;
}

function MemberCylinder({ nodeI, nodeJ, color, radius, onHover, onClick }: MemberCylinderProps) {
  const meshRef = useRef<THREE.Mesh>(null);

  const { position, quaternion, length } = useMemo(() => {
    const start = new THREE.Vector3(nodeI.x, nodeI.y, nodeI.z);
    const end = new THREE.Vector3(nodeJ.x, nodeJ.y, nodeJ.z);
    const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
    const direction = new THREE.Vector3().subVectors(end, start);
    const len = direction.length();

    // Cylinder default direction is along Y axis
    const q = new THREE.Quaternion();
    if (len > 1e-6) {
      const up = new THREE.Vector3(0, 1, 0);
      q.setFromUnitVectors(up, direction.normalize());
    }

    return { position: mid, quaternion: q, length: len };
  }, [nodeI, nodeJ]);

  return (
    <mesh
      ref={meshRef}
      position={position}
      quaternion={quaternion}
      onPointerOver={(e) => { e.stopPropagation(); onHover(true); }}
      onPointerOut={(e) => { e.stopPropagation(); onHover(false); }}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
    >
      <cylinderGeometry args={[radius, radius, length, 8]} />
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

// ─── Support Symbol ───

function SupportSymbol({ position, type }: { position: [number, number, number]; type: string }) {
  const isPin = type === 'pin' || type === 'fixed';

  if (isPin) {
    // Triangle pointing down
    return (
      <group position={position}>
        <mesh position={[0, -0.35, 0]} rotation={[0, 0, Math.PI]}>
          <coneGeometry args={[0.3, 0.4, 3]} />
          <meshStandardMaterial color={SUPPORT_COLOR} wireframe />
        </mesh>
        {/* Ground line */}
        <Line
          points={[[-0.4, -0.55, 0], [0.4, -0.55, 0]]}
          color={SUPPORT_COLOR}
          lineWidth={2}
        />
      </group>
    );
  }

  // Roller — triangle + circle
  return (
    <group position={position}>
      <mesh position={[0, -0.35, 0]} rotation={[0, 0, Math.PI]}>
        <coneGeometry args={[0.3, 0.4, 3]} />
        <meshStandardMaterial color={SUPPORT_COLOR} wireframe />
      </mesh>
      <mesh position={[0, -0.7, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.12, 0.03, 8, 16]} />
        <meshStandardMaterial color={SUPPORT_COLOR} />
      </mesh>
      <Line
        points={[[-0.4, -0.85, 0], [0.4, -0.85, 0]]}
        color={SUPPORT_COLOR}
        lineWidth={2}
      />
    </group>
  );
}

// ─── Load Arrow ───

function LoadArrow({ position, fx, fy, fz }: {
  position: [number, number, number];
  fx: number; fy: number; fz: number;
}) {
  const magnitude = Math.sqrt(fx * fx + fy * fy + fz * fz);
  if (magnitude < 1e-6) return null;

  const arrowLength = 1.5;
  const dir = new THREE.Vector3(fx, fy, fz).normalize();
  const arrowStart = new THREE.Vector3(...position).add(
    dir.clone().multiplyScalar(-arrowLength)
  );
  const arrowEnd = new THREE.Vector3(...position);

  // Arrow head direction
  const q = new THREE.Quaternion();
  q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);

  return (
    <group>
      <Line
        points={[
          [arrowStart.x, arrowStart.y, arrowStart.z],
          [arrowEnd.x, arrowEnd.y, arrowEnd.z],
        ]}
        color={LOAD_COLOR}
        lineWidth={2.5}
      />
      <mesh position={[arrowEnd.x, arrowEnd.y, arrowEnd.z]} quaternion={q}>
        <coneGeometry args={[0.12, 0.3, 8]} />
        <meshStandardMaterial color={LOAD_COLOR} />
      </mesh>
      {/* Force label */}
      <Text
        position={[arrowStart.x - 0.3, arrowStart.y, arrowStart.z]}
        fontSize={0.25}
        color="#f59e0b"
        anchorX="right"
      >
        {`${(magnitude / 1000).toFixed(0)} kN`}
      </Text>
    </group>
  );
}

// ─── Deformed Shape Overlay ───

function DeformedOverlay({ structure, nodeResultMap, scale }: {
  structure: { nodes: NodeData[]; members: MemberData[] };
  nodeResultMap: Record<number, { dx: number; dy: number; dz: number }>;
  scale: number;
}) {
  const nodeMap = useMemo(() => {
    const map: Record<number, NodeData> = {};
    structure.nodes.forEach((n) => { map[n.id] = n; });
    return map;
  }, [structure.nodes]);

  return (
    <group>
      {structure.members.map((member) => {
        const ni = nodeMap[member.node_i];
        const nj = nodeMap[member.node_j];
        if (!ni || !nj) return null;

        const di = nodeResultMap[member.node_i] || { dx: 0, dy: 0, dz: 0 };
        const dj = nodeResultMap[member.node_j] || { dx: 0, dy: 0, dz: 0 };

        const startDeformed: [number, number, number] = [
          ni.x + di.dx * scale,
          ni.y + di.dy * scale,
          ni.z + di.dz * scale,
        ];
        const endDeformed: [number, number, number] = [
          nj.x + dj.dx * scale,
          nj.y + dj.dy * scale,
          nj.z + dj.dz * scale,
        ];

        return (
          <Line
            key={`def-${member.id}`}
            points={[startDeformed, endDeformed]}
            color="#f59e0b"
            lineWidth={1.5}
            dashed
            dashSize={0.2}
            gapSize={0.1}
          />
        );
      })}
    </group>
  );
}
