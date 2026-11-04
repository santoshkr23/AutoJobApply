import { cn } from "@/lib/utils";

const tones: Record<string, string> = {
  default: "bg-secondary text-secondary-foreground",
  primary: "bg-accent text-accent-foreground",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-destructive/15 text-destructive",
};

export function Badge({ tone = "default", className, ...p }: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", tones[tone], className)} {...p} />;
}

const STATUS_TONE: Record<string, keyof typeof tones> = {
  APPLIED: "success", INTERVIEW: "success", OFFER: "success", PENDING_APPROVAL: "warning", MANUAL_REQUIRED: "warning",
  FAILED: "danger", REJECTED: "danger", APPLYING: "primary", RESUME_GENERATED: "primary", MATCHED: "default", WITHDRAWN: "default", DISCOVERED: "default",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "default"}>{status.replace(/_/g, " ").toLowerCase()}</Badge>;
}

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-xs text-muted-foreground">Not scored</span>;
  const tone = score >= 85 ? "success" : score >= 70 ? "primary" : score >= 55 ? "warning" : "default";
  return <Badge tone={tone} aria-label={`Match score ${score} out of 100`}>{score}% match</Badge>;
}
