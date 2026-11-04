import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Pager } from "@/components/pager";
import { cleanProfile, emptyProfile } from "@/components/profile-editor";
import { salaryText } from "@/components/job-card";
import { ScoreBadge, StatusBadge } from "@/components/ui/badge";
import { formatMoney, titleCase } from "@/lib/utils";

describe("badges", () => {
  it("shows the match score with an accessible label", () => {
    render(<ScoreBadge score={82} />);
    expect(screen.getByLabelText("Match score 82 out of 100")).toHaveTextContent("82% match");
  });
  it("handles an unscored job", () => { render(<ScoreBadge score={null} />); expect(screen.getByText("Not scored")).toBeInTheDocument(); });
  it("humanises statuses", () => { render(<StatusBadge status="MANUAL_REQUIRED" />); expect(screen.getByText("manual required")).toBeInTheDocument(); });
});

describe("pager", () => {
  it("hides when everything fits on one page", () => { const { container } = render(<Pager page={1} pageSize={10} total={5} onPage={() => {}} />); expect(container).toBeEmptyDOMElement(); });
  it("navigates", () => {
    const onPage = vi.fn();
    render(<Pager page={2} pageSize={10} total={35} onPage={onPage} />);
    fireEvent.click(screen.getByText("Next")); fireEvent.click(screen.getByText("Previous"));
    expect(onPage).toHaveBeenNthCalledWith(1, 3); expect(onPage).toHaveBeenNthCalledWith(2, 1);
  });
});

describe("helpers", () => {
  it("formats money from minor units", () => { expect(formatMoney(49900)).toContain("499"); });
  it("title-cases", () => { expect(titleCase("auto_apply")).toBe("Auto Apply"); });
  it("formats salary ranges", () => {
    expect(salaryText({ salary_min: 800000, salary_max: 1200000, salary_currency: "INR", salary_period: "year" })).toBe("INR 8,00,000-12,00,000 / year");
    expect(salaryText({ salary_min: null, salary_max: null, salary_currency: null, salary_period: null })).toBeNull();
  });
  it("cleanProfile drops empty rows and trims", () => {
    const p = { ...emptyProfile(), full_name: "  Ann ", experience: [{ company: "", title: "", is_current: false, bullets: [] }, { company: "X", title: "Dev", is_current: true, end_date: "Dec 2020", bullets: [" a ", ""] }], education: [{ institution: " " }] };
    const c = cleanProfile(p);
    expect(c.full_name).toBe("Ann"); expect(c.experience).toHaveLength(1); expect(c.experience[0].bullets).toEqual(["a"]); expect(c.experience[0].end_date).toBeNull(); expect(c.education).toHaveLength(0);
  });
});
