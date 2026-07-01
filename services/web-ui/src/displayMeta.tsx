import {
  Boxes,
  Bot,
  Bug,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  FileText,
  GitBranch,
  Network,
  ShieldCheck,
  SquareStack,
  Wrench,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import type { StatusTone } from "./ui";

export type StageDisplayMeta = {
  description: string;
  icon: ReactNode;
  key: string;
  label: string;
};

export const STANDARD_PIPELINE_STAGES: StageDisplayMeta[] = [
  { key: "snapshot-ready", label: "Snapshot Ready", description: "Ready workspace snapshot is bound to the run.", icon: <SquareStack className="h-4 w-4" /> },
  { key: "structure-discovery", label: "Structure Discovery", description: "Workspace structure, manifests, and entrypoints are mapped.", icon: <FileSearch className="h-4 w-4" /> },
  { key: "agent-audit", label: "Agent Audit", description: "Orchestrator starts the first audit pass.", icon: <Bot className="h-4 w-4" /> },
  { key: "code-analysis", label: "Code Analysis", description: "Batch code analysis and local tools produce candidate evidence.", icon: <ClipboardCheck className="h-4 w-4" /> },
  { key: "value-triage", label: "Value Triage", description: "Candidates are ranked by exploitability and business value.", icon: <ShieldCheck className="h-4 w-4" /> },
  { key: "whiteboard-swarm", label: "Whiteboard Swarm", description: "Shared whiteboard schedules swarm tasks and Trace Worker evidence.", icon: <GitBranch className="h-4 w-4" /> },
  { key: "validation-judgement", label: "Validation Judgement", description: "Validators decide whether findings are real and actionable.", icon: <CheckCircle2 className="h-4 w-4" /> },
  { key: "feedback-loop", label: "Feedback Loop", description: "Weak findings request more context or deeper analysis.", icon: <Workflow className="h-4 w-4" /> },
  { key: "poc-writing", label: "PoC Writing", description: "PoC writers draft safe proof artifacts for confirmed findings.", icon: <FileText className="h-4 w-4" /> },
  { key: "poc-verification", label: "PoC Verification", description: "PoC verifier checks reproducibility in runtime.", icon: <Wrench className="h-4 w-4" /> },
  { key: "report", label: "Report", description: "Reports summarize findings, evidence, validation, and artifacts.", icon: <FileText className="h-4 w-4" /> },
  { key: "runtime-cleanup", label: "Runtime Cleanup", description: "Containers and temporary runtime resources are cleaned up.", icon: <Boxes className="h-4 w-4" /> },
];

export type ExecutionNodeDisplayMeta = {
  icon: ReactNode;
  label: string;
  ring: string;
};

export function executionNodeMeta(kind: string): ExecutionNodeDisplayMeta {
  if (kind.includes("audit-run")) return { label: "Audit Run", icon: <ShieldCheck className="h-4 w-4" />, ring: "border-slate-400 bg-slate-100 text-slate-800" };
  if (kind.includes("pipeline")) return { label: "Pipeline Step", icon: <Workflow className="h-4 w-4" />, ring: "border-cyan-300 bg-cyan-50 text-cyan-900" };
  if (kind.includes("agent")) return { label: "Agent Run", icon: <Bot className="h-4 w-4" />, ring: "border-indigo-300 bg-indigo-50 text-indigo-800" };
  if (kind.includes("container")) return { label: "Container", icon: <Boxes className="h-4 w-4" />, ring: "border-slate-400 bg-slate-100 text-slate-800" };
  if (kind.includes("whiteboard")) return { label: "Whiteboard", icon: <GitBranch className="h-4 w-4" />, ring: "border-emerald-300 bg-emerald-50 text-emerald-800" };
  if (kind.includes("task") || kind.includes("swarm")) return { label: "Swarm Task", icon: <Workflow className="h-4 w-4" />, ring: "border-amber-300 bg-amber-50 text-amber-900" };
  if (kind.includes("finding")) return { label: "Finding", icon: <Bug className="h-4 w-4" />, ring: "border-red-300 bg-red-50 text-red-800" };
  if (kind.includes("evidence") || kind.includes("artifact")) return { label: "Evidence", icon: <FileText className="h-4 w-4" />, ring: "border-violet-300 bg-violet-50 text-violet-800" };
  if (kind.includes("report")) return { label: "Report", icon: <FileText className="h-4 w-4" />, ring: "border-teal-300 bg-teal-50 text-teal-800" };
  return { label: "Node", icon: <Network className="h-4 w-4" />, ring: "border-slate-300 bg-white text-slate-700" };
}

export function severityTone(value?: string): StatusTone {
  const normalized = (value || "").toLowerCase();
  if (["critical", "high"].includes(normalized)) return "danger";
  if (["medium"].includes(normalized)) return "warning";
  if (["low", "info", "informational"].includes(normalized)) return "processing";
  return "neutral";
}
