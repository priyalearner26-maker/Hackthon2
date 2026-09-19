# Nexa Playwright Dashboard

This is an independent Playwright test execution application. It does not import or modify the existing `frontend/` or `backend/` modules.

## Run

```powershell
npm install
npm run playwright:install
npm run dev
```

Open `http://127.0.0.1:4174`.

The Vite UI runs on port `4174`; the isolated Express and Socket.IO execution API runs on port `4175`. Story and mapped-test fixtures are local to this module and can be replaced by Jira adapter calls inside `server/index.ts`.

## Execution artifacts

Each run captures screenshots, videos, traces, and browser console messages under `artifacts/`. The module also includes `playwright.config.ts`, `allure-playwright`, and an Allure report script.