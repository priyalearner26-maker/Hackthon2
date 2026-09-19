import { test, expect } from "@playwright/test";

test("execution dashboard shell loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Playwright Test Command" })).toBeVisible();
});