import { Building2, ExternalLink, MapPin } from "lucide-react";
import { Badge, ScoreBadge } from "@/components/ui/badge";
import type { Job } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export function salaryText(j: Pick<Job, "salary_min" | "salary_max" | "salary_currency" | "salary_period">) {
  if (j.salary_min == null && j.salary_max == null) return null;
  const f = (n: number) => n.toLocaleString("en-IN");
  const range = j.salary_min && j.salary_max && j.salary_min !== j.salary_max ? `${f(j.salary_min)}-${f(j.salary_max)}` : f((j.salary_min ?? j.salary_max)!);
  return `${j.salary_currency ?? ""} ${range}${j.salary_period ? ` / ${j.salary_period}` : ""}`.trim();
}

export function JobSummary({ job, children }: { job: Job; children?: React.ReactNode }) {
  const salary = salaryText(job);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold leading-tight">{job.title}</h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1"><Building2 className="h-3.5 w-3.5" aria-hidden />{job.company}</span>
            {job.location_text && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden />{job.location_text}</span>}
            {salary && <span>{salary}</span>}
          </p>
        </div>
        <ScoreBadge score={job.match_score} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {job.work_mode && <Badge tone="primary">{job.work_mode}</Badge>}
        {job.is_sample && <Badge tone="warning" title="Built-in sample data for development - not a real job">sample data</Badge>}
        {job.skills.slice(0, 6).map((s) => <Badge key={s}>{s}</Badge>)}
      </div>
      <p className="text-xs text-muted-foreground">via {job.source}{job.posted_at ? ` · posted ${formatDate(job.posted_at)}` : ""}{" "}
        <a href={job.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-primary hover:underline">View posting<ExternalLink className="h-3 w-3" aria-hidden /></a></p>
      {children}
    </div>
  );
}
