import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const LOG = process.env.E2E_BACKEND_LOG ?? "/tmp/e2e-backend.log";
const email = `e2e-${Date.now()}@example.com`;
const password = "E2e-Passw0rd!x";

function verifyToken(): string {
  const log = readFileSync(LOG, "utf8");
  const matches = [...log.matchAll(/verify-email\?token=([A-Za-z0-9_-]+)/g)];
  if (!matches.length) throw new Error("verification link not found in backend log");
  return matches[matches.length - 1][1];
}

test("public pages render", async ({ page }) => {
  for (const [url, heading] of [["/", /Find the right jobs/], ["/pricing", /Simple pricing/], ["/faq", /Frequently asked/], ["/features", /Features/], ["/how-it-works", /How it works/]] as const) {
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(heading);
  }
  await page.goto("/pricing");
  await expect(page.getByText("₹499")).toBeVisible();
  await expect(page.getByText("₹999")).toBeVisible();
});

test("dashboard redirects anonymous visitors to sign in", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});

test("full user journey: register -> onboard -> match -> tailor -> approve -> track", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Priya Sharma");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByLabel(/Terms of Service/).check();
  await page.getByLabel(/Privacy Policy/).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();

  await expect.poll(() => { try { return verifyToken().length; } catch { return 0; } }, { timeout: 15_000 }).toBeGreaterThan(10);
  await page.goto(`/verify-email?token=${verifyToken()}`);
  await expect(page.getByText("Email verified")).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/onboarding/);

  await page.locator("input[type=file]").setInputFiles(path.join(__dirname, "fixtures/resume.docx"));
  await expect(page.getByText("Check what we extracted")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("Full name")).toHaveValue("Priya Sharma");
  await page.getByLabel("Country code").fill("IN");
  await page.getByRole("button", { name: "Confirm and continue" }).click();

  await page.getByLabel("Countries").fill("IN");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Minimum match score").fill("50");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel(/AI processing/).check();
  await page.getByLabel(/Automated applications/).check();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  // Sandbox billing (clearly labelled, no real money) unlocks tailoring.
  await page.goto("/dashboard/subscription");
  await expect(page.getByText("Sandbox billing")).toBeVisible();
  await page.getByRole("button", { name: "Choose Pro" }).click();
  await expect(page.getByText("Current plan: Pro")).toBeVisible({ timeout: 15_000 });

  await page.goto("/dashboard/matches");
  await page.getByRole("button", { name: "Find new matches" }).first().click();
  await expect(page.getByRole("heading", { name: "Azure Data Engineer" }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Start application" }).first().click();

  await expect(page).toHaveURL(/\/dashboard\/applications\//);
  await page.getByRole("button", { name: /Generate tailored resume/ }).click();
  await expect(page.getByText("draft - not approved")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Approve documents" }).click();
  await expect(page.getByText("documents approved")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve and submit/ })).toBeVisible();
  await page.getByLabel("Update status").selectOption("APPLIED");
  await expect(page.getByText(/not verified by the platform/).first()).toBeVisible();

  const csv = await page.request.get("/api/applications/export.csv");
  expect(csv.ok()).toBeTruthy();
  expect(await csv.text()).toContain("Azure Data Engineer");
});
