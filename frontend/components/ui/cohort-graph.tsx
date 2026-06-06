"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";

import type { CohortMemberState } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Radial cohort graph: the patient sits at center; donors arrange in a ring around
 * them. Click any donor node to toggle ejection — the existing simulator data flow
 * runs the scenario.
 *
 * Each donor node carries the same `data-testid="donor-tile"` + `data-ejected`
 * attributes the grid view uses, so E2E selectors keep working in this view.
 */
export function CohortGraph({
  patientName,
  patientBloodGroup,
  cohort,
  ejectedSet,
  onToggle,
}: {
  patientName: string;
  patientBloodGroup: string;
  cohort: CohortMemberState[];
  ejectedSet: Set<string>;
  onToggle: (donorId: string) => void;
}) {
  const { nodes, edges } = useMemo(() => {
    const radiusX = 320;
    const radiusY = 200;
    const n = cohort.length;

    const patientNode: Node = {
      id: "patient",
      type: "patient",
      position: { x: 0, y: 0 },
      data: { name: patientName, bloodGroup: patientBloodGroup },
      draggable: false,
      selectable: false,
    };

    const donorNodes: Node[] = cohort.map((m, i) => {
      const theta = (2 * Math.PI * i) / Math.max(n, 1) - Math.PI / 2;
      return {
        id: m.donor_id,
        type: "donor",
        position: {
          x: Math.cos(theta) * radiusX,
          y: Math.sin(theta) * radiusY,
        },
        data: {
          member: m,
          ejected: ejectedSet.has(m.donor_id),
          onToggle,
        },
        draggable: false,
        selectable: false,
      };
    });

    const donorEdges: Edge[] = cohort.map((m) => ({
      id: `e-${m.donor_id}`,
      source: "patient",
      target: m.donor_id,
      animated: !ejectedSet.has(m.donor_id),
      style: {
        stroke: ejectedSet.has(m.donor_id)
          ? "rgba(255,255,255,0.06)"
          : "rgba(78,205,196,0.4)",
        strokeWidth: ejectedSet.has(m.donor_id) ? 1 : 1.5,
        strokeDasharray: ejectedSet.has(m.donor_id) ? "4 4" : undefined,
      },
    }));

    return {
      nodes: [patientNode, ...donorNodes],
      edges: donorEdges,
    };
  }, [patientName, patientBloodGroup, cohort, ejectedSet, onToggle]);

  return (
    <div
      data-testid="cohort-graph"
      className="relative h-[520px] w-full overflow-hidden rounded-2xl border border-white/5 bg-black/30"
    >
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          panOnScroll={false}
          zoomOnScroll={false}
          zoomOnPinch={true}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => {
            if (node.type === "donor" && node.id !== "patient") {
              onToggle(node.id);
            }
          }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="rgba(255,255,255,0.06)"
          />
          <Controls
            showInteractive={false}
            className="!bg-surface/80 !border-white/10 [&_button]:!bg-transparent [&_button]:!text-white/60 [&_button:hover]:!text-white"
          />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}

// ---------- Custom node types ----------

function PatientNode({ data }: NodeProps<{ name: string; bloodGroup: string }>) {
  return (
    <div
      data-testid="graph-patient-node"
      className="rounded-full bg-gradient-to-br from-primary to-accent p-[2px] shadow-xl shadow-primary/30"
    >
      <Handle type="source" position={Position.Top} className="!opacity-0" />
      <div className="flex h-24 w-24 flex-col items-center justify-center rounded-full bg-background text-center">
        <p className="text-[10px] uppercase tracking-wider text-white/40">Patient</p>
        <p className="mt-0.5 max-w-[80px] truncate text-xs font-semibold text-white">
          {data.name}
        </p>
        <p className="mt-0.5 rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-primary">
          {data.bloodGroup}
        </p>
      </div>
    </div>
  );
}

function DonorNode({
  data,
}: NodeProps<{
  member: CohortMemberState;
  ejected: boolean;
  onToggle: (donorId: string) => void;
}>) {
  const { member, ejected } = data;
  const churn = Math.round(member.churn_90d * 100);
  const tone =
    churn >= 60
      ? "border-red-500/40 bg-red-500/10"
      : churn >= 35
      ? "border-amber-500/40 bg-amber-500/10"
      : "border-emerald-500/30 bg-emerald-500/10";

  return (
    // Click is dispatched by ReactFlow's onNodeClick (pane intercepts pointer events
    // on inner buttons), so we render a div but keep the same testids/attrs the
    // grid view uses so E2E selectors keep working.
    <div
      role="button"
      aria-pressed={ejected}
      data-testid="donor-tile"
      data-ejected={ejected ? "true" : "false"}
      data-donor-id={member.donor_id}
      className={cn(
        "group flex w-44 cursor-pointer flex-col items-start gap-1 rounded-xl border bg-surface/80 p-3 text-left shadow-lg backdrop-blur transition-all",
        ejected
          ? "border-white/5 bg-white/[0.02] opacity-50"
          : tone,
        "hover:scale-[1.03] hover:border-white/30",
      )}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="flex w-full items-center justify-between gap-2">
        <span
          className={cn(
            "truncate text-sm font-medium text-white",
            ejected && "line-through opacity-70",
          )}
        >
          {member.donor_name}
        </span>
        <span className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-primary">
          {member.blood_group}
        </span>
      </div>
      <div className="flex items-center gap-1 text-[10px] text-white/50">
        <span>30d {Math.round(member.churn_30d * 100)}%</span>
        <span>·</span>
        <span>60d {Math.round(member.churn_60d * 100)}%</span>
        <span>·</span>
        <span className="font-semibold text-white/80">90d {churn}%</span>
      </div>
      <p className="text-[10px] text-white/40 opacity-0 transition-opacity group-hover:opacity-100">
        {ejected ? "Click to restore" : "Click to eject"}
      </p>
    </div>
  );
}

const NODE_TYPES = {
  patient: PatientNode,
  donor: DonorNode,
};
