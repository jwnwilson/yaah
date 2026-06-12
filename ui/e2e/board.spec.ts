import { test, expect } from "@playwright/test";

// Requires the API running on :8000 (dev auth bypass -> dev-user) and the Vite
// dev server proxying /api. See e2e/README.md. The Vite proxy strips the /api
// prefix, so this also guards against the proxy-rewrite regression.
test("create project, add epic, see it on the board hierarchy", async ({ page }) => {
  const suffix = `${Date.now()}`;
  const projectName = `E2E Project ${suffix}`;

  await page.goto("/");

  // Create a project (needs a repo_url or local_path).
  await page.getByRole("button", { name: /new project/i }).click();
  await page.getByLabel(/name/i).fill(projectName);
  await page.getByLabel(/local path/i).fill(`/tmp/e2e-repo-${suffix}`);
  await page.getByRole("button", { name: /^create$/i }).click();

  // It appears in the list; open its board.
  await page.getByText(projectName).click();
  await expect(page.getByRole("heading", { name: /board/i })).toBeVisible();

  // Create an epic via the hierarchy tree.
  await page.getByRole("button", { name: /add epic/i }).click();
  await page.getByPlaceholder(/new epic title/i).fill("E2E Epic");
  await page.getByRole("button", { name: /^create$/i }).click();

  await expect(page.getByText("E2E Epic")).toBeVisible();
});
