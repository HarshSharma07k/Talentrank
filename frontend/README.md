# TalentRank Frontend

React + TypeScript + Vite + Tailwind CSS client for the TalentRank matching API. Paste a resume, get back a ranked list of jobs from the bi-encoder + cross-encoder pipeline.

## Setup

```bash
npm install
cp .env.example .env   # points VITE_API_BASE_URL at the local API by default
npm run dev
```

The dev server runs at `http://localhost:5173` and expects the TalentRank API at `http://localhost:8000` (see the root `README.md` for running the backend). CORS for `http://localhost:5173` is already allowed by the API.

## Scripts

- `npm run dev` — start the Vite dev server
- `npm run build` — type-check (`tsc -b`) and build a production bundle to `dist/`
- `npm run preview` — serve the production build locally
- `npm run lint` — run oxlint

## Structure

```text
src/
├── components/   UI components (form, results, header, state panels)
├── hooks/        useHealthCheck, useTheme
├── lib/          api client, formatting helpers, sample resume
├── App.tsx       page layout and request orchestration
```
