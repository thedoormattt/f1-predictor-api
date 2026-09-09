# F1 Predictions League — API

FastAPI backend for the F1 Predictions League webapp.

## Stack
- **FastAPI** — API framework
- **Supabase** — PostgreSQL database + auth (service role client)
- **OpenF1** — race result data
- **Render** — hosting

---

## Local setup

Python 3.13 (see `.python-version` — Render reads the same file, so local and
production stay on the same runtime).

```bash
# 1. Create and activate a virtualenv
#    Homebrew Python refuses a global pip install (PEP 668), so this isn't optional
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env with your Supabase credentials
cat > .env <<'EOF'
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_ANON_KEY=
SECRET_KEY=
EOF

# 4. Run locally
uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs?secret=$SECRET_KEY

Run the tests with `pytest tests/`.

---

## Project structure

```
app/
  main.py              # FastAPI app, CORS, router registration
  config.py            # Settings (reads from .env)
  database.py          # Supabase client singleton
  models.py            # Pydantic schemas for all entities
  routers/
    races.py            # GET /races, GET /races/{id}
    predictions.py      # GET + POST /predictions
    results.py          # GET /results, admin fetch + score endpoints
    leaderboard.py      # GET /leaderboard, GET /leaderboard/cumulative
    reference.py        # GET /reference/drivers, /reference/teams
  services/
    scoring.py          # Core scoring engine (mirrors spreadsheet logic)
    openf1.py           # OpenF1 API integration
tests/
  test_scoring.py       # Scoring unit tests
render.yaml             # Render deployment config
```

---

## Endpoints

### Public
| Method | Path | Description |
|--------|------|-------------|
| GET | `/races` | All races in calendar order |
| GET | `/races/{id}` | Single race |
| GET | `/predictions/race/{race_id}` | All predictions for a race (visible after race starts) |
| GET | `/predictions/player/{player_id}` | All predictions for a player |
| POST | `/predictions` | Submit/update a prediction (locked at race start) |
| GET | `/results/{race_id}` | Race result |
| GET | `/results/{race_id}/scores` | All player scores for a race |
| GET | `/leaderboard` | Current standings |
| GET | `/leaderboard/cumulative` | Cumulative scores per race (for chart) |
| GET | `/reference/drivers` | Driver list for prediction form |
| GET | `/reference/teams` | Team list for pitstop prediction |

### Admin (requires `X-Admin-Secret` header)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/results/admin/{race_id}/fetch-openf1` | Fetch result from OpenF1 and save |
| PATCH | `/results/admin/{race_id}/override` | Correct individual result fields |
| POST | `/results/admin/{race_id}/score` | Run scoring for all players |
| POST | `/results/admin/score-all` | Rescore every race that has a result |
| POST | `/results/admin/autoscore` | Run the automatic sweep immediately |

---

## After each race — nothing

Scoring is automatic. A background sweep runs on startup and every
`AUTOSCORE_INTERVAL_MINUTES`, and for each race that finished recently it
fetches the OpenF1 result and scores every player. Both steps are idempotent,
and a race that is already fully scored is skipped without calling OpenF1.

Free-tier Render instances sleep when idle, so the startup sweep is the one
that matters: whatever was missed while the service was asleep is caught up the
moment it wakes.

| Setting | Default | Meaning |
|---------|---------|---------|
| `AUTOSCORE_ENABLED` | `true` | Turn the sweep off entirely |
| `AUTOSCORE_INTERVAL_MINUTES` | `15` | How often the sweep runs |
| `AUTOSCORE_RACE_DELAY_MINUTES` | `210` | How long after lights out a GP is treated as finished |
| `AUTOSCORE_SPRINT_DELAY_MINUTES` | `120` | Same, for sprints |
| `AUTOSCORE_LOOKBACK_DAYS` | `10` | Races older than this are ignored by the sweep |

The manual admin steps remain for corrections:

```
POST  /results/admin/{race_id}/fetch-openf1   # re-pull from OpenF1
PATCH /results/admin/{race_id}/override        # fix a field by hand
POST  /results/admin/{race_id}/score           # recalculate scores
POST  /results/admin/autoscore                 # run the sweep right now
```

### Driver of the Day

DotD is not published by OpenF1 and was the only field ever entered by hand.
It has been retired: it can no longer be set (the fetch and override endpoints
both preserve whatever is stored) and it is no longer offered on the prediction
form. The column, the model field and the 4-point scoring rule all remain, so
historical scores are unchanged and stay reproducible on a rescore.

---

## Running tests

```bash
pytest tests/
```

---

## Deploying to Render

1. Push repo to GitHub
2. Create a new **Web Service** on Render, connect your repo
3. Render detects `render.yaml` automatically
4. Add environment variables in Render dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `SECRET_KEY` (used to protect admin endpoints)
5. Deploy — Render builds and starts automatically on every push
