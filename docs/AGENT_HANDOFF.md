# DhanyaDrishti — Agent Handoff

> Read this first if you are a new human or AI-agent session. It encodes the PRD §24
> continuity protocol so no prior chat history is required.

---

## 1. Mandatory beginning-of-session procedure

1. Read `PRD.txt` (or `docs/PRD.md`).
2. Read `docs/DECISIONS.md`.
3. Read `PROJECT_STATUS.md`.
4. Read `PHASE_PLAN.txt` — only the section for the current phase is usually needed.
5. Inspect the repository state:
   ```powershell
   git status
   git log --oneline -10
   ```
6. Run the relevant existing tests **before** changing code:
   ```powershell
   cd backend; python -m pytest -q
   cd ..\frontend; npm run build
   ```
7. Continue only from the **"Next exact task"** in `PROJECT_STATUS.md`.
8. Do not replace completed work or change a locked decision (see `docs/DECISIONS.md` §1).

If `PROJECT_STATUS.md` and reality disagree, trust reality, then fix the status file.

## 2. Mandatory end-of-session procedure

1. Run the relevant tests.
2. Update `PROJECT_STATUS.md` (all fields, including the next exact task).
3. Update documentation if architecture or behaviour changed.
4. Record known limitations or blockers.
5. Commit only after tests pass, with a focused message
   (e.g. `feat(api): health endpoint and typed config`).
6. Leave exactly one clearly stated next task.

## 3. Repository map (where things belong)

| Need | Location |
|---|---|
| Product requirements | `PRD.txt`, `docs/PRD.md` |
| Execution plan | `PHASE_PLAN.txt` |
| Current state | `PROJECT_STATUS.md` |
| Locked decisions | `docs/DECISIONS.md` |
| System design | `docs/ARCHITECTURE.md` |
| Backend app | `backend/app/` |
| Calibration thresholds (Phase 2+) | `backend/configs/*.yaml` |
| Production model artifacts | `backend/app/artifacts/production/` |
| Runtime temp storage (wiped) | `backend/.runtime/` |
| Backend tests | `backend/tests/` |
| Frontend app | `frontend/src/` |
| Dataset (not committed) | `data/raw/rice_leaf_diseases/` |
| Split manifests (committed) | `data/splits/` |
| Experiment notebooks | `notebooks/` |
| One-off scripts | `scripts/` |
| Cross-stack tests | `tests/end_to_end/` |

## 4. Local commands

```powershell
# Backend (from repository root)
cd backend
python -m pytest -q
uvicorn app.main:app --reload --port 8000

# Frontend (from repository root)
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # type-check + production build
```

Environment:

- Root `.env` (copy of `.env.example`) → backend settings.
- `frontend/.env` (copy of `frontend/.env.example`) → `VITE_API_BASE_URL`.

## 5. Current state (Phase 0 done)

- Backend: app factory, typed settings, logging, error mapping, CORS, health endpoint, 3 tests.
- Frontend: dashboard shell (header/nav/footer), three routed pages, health badge, API client stub.
- Data: raw dataset in `data/raw/rice_leaf_diseases/` (40/40/40), git-ignored.
- No prediction pipeline or model exists yet — that is expected.

## 6. Rules that prevent damage

- Do not edit or delete files under `data/raw/`.
- Do not commit raw images, `.env`, SQLite files or `backend/.runtime/`.
- Do not add TensorFlow, CUDA or MobileNetV2 to Version 1.
- Do not train a model inside a request handler.
- Do not duplicate feature-extraction logic; training and inference must share one module.
- Keep every numeric threshold in `backend/configs/*.yaml`.
- Never claim healthy-leaf detection; return `uncertain` instead.
- Keep the exact disclaimer wording from the PRD in API responses and UI.

## 7. Handoff checklist for the next session

- [ ] Read the five documents listed in §1.
- [ ] Confirm tests pass before edits.
- [ ] Pick up the "Next exact task" from `PROJECT_STATUS.md`.
- [ ] Stay inside the current phase; do not start the next phase early.
- [ ] Update `PROJECT_STATUS.md` before finishing.
