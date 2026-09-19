import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  reporter: [["list"], ["allure-playwright"]],
  use: { trace: "retain-on-failure", video: "retain-on-failure", screenshot: "only-on-failure", baseURL: "http://127.0.0.1:4174" },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});