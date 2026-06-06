# Bridge OS — Frontend

Next.js 14 App Router. Multi-page architecture matching the planned route table.

## Setup

```powershell
npm install
npx playwright install        # one-time, downloads E2E browsers
```

## Run

```powershell
copy ..\.env.example .env.local
npm run dev
# http://localhost:3000
```

## Test

```powershell
npm test               # Vitest unit/component tests
npm run e2e            # Playwright E2E (needs dev server or it auto-starts)
```
