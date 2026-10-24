# P.U.L.S.E. — Predictive Upper-Atmosphere Launch & Simulation Engine

P.U.L.S.E. is a Python-first **educational** rocket ascent and weather-screening workbench. It integrates a simplified three-axis ascent, compares a reference atmosphere with explicitly requested Open-Meteo forecasts, and shows a transparent relative ranking of forecast hours.

> **Not flight-certified.** This software, its example vehicle profiles, and its forecasts are not suitable for real launch planning, flight guidance, range safety, structural certification, or go/no-go decisions. It does not calculate orbital insertion. See the in-app [model and library guide](/guide).

## Run in Replit

The `Start application` workflow runs:

```sh
uvicorn backend.main:app --host 0.0.0.0 --port 5000
```

Open the web preview at `/`. The workbench starts with a **modeled standard atmosphere**; no API key is needed for that simulation. Live forecast requests require internet access and call Open-Meteo directly. There is no silent switch to standard-atmosphere weather if a forecast request fails.

## Run locally

Requires Python 3.13 (3.10+ is recommended). With `uv`:

```sh
uv sync
uv run uvicorn backend.main:app --host 0.0.0.0 --port 5000
```

Open `http://127.0.0.1:5000`. Interactive API documentation is at `/docs`.

## Libraries and versions

Full explanations, links, purpose, and limitations are in [`/guide`](http://127.0.0.1:5000/guide), served from `frontend/guide.html`.

| Library | Version | Use |
|---|---:|---|
| Python | 3.13 | Main implementation and HTTP application |
| FastAPI | 0.161.1 | Typed HTTP API, validation integration, OpenAPI docs |
| Uvicorn | 0.54.0 | ASGI web server |
| NumPy | 2.5.4 | Atmospheric lookup arrays and interpolation |
| SciPy | 1.18.1 | Trapezoidal heat-load accumulation |
| HTTPX | 0.28.1 | Bounded-timeout Open-Meteo HTTPS requests |
| Jinja2 | 3.1.6 | Server-rendered guide |
| Pydantic | 2.14.1 | Simulation request validation (via FastAPI) |
| Chart.js | 4.4.8 | Local browser-side data visualization |
| pytest | 9.1.1 | Unit and API tests |

Python standard-library modules also handle CSV/JSON, dates, kinematics, file paths, and the in-memory result cache. The interface uses native HTML, CSS, and browser JavaScript; it does not use React, Leaflet, Three.js, or a map SDK. Versions are pinned in `pyproject.toml` and `uv.lock`.

## Model and data provenance

- Fixed 0.01 s midpoint (second-order Runge–Kutta) integration of east, north, and up position/velocity, with a spherical gravity correction.
- Two-stage or single-stage illustrative rocket presets with propellant depletion, dry-stage separation, altitude-adjusted thrust, simplified drag, and a prescribed pitch program. Preset numbers are approximate and not verified against manufacturer documentation.
- Reference weather is labeled **modeled**: layered dry standard-atmosphere approximation and zero wind.
- Live weather is labeled **forecast**: hourly Open-Meteo 2 m/surface and pressure-level temperature, wind, and geopotential height. Forecast pressure-layer altitudes and above-profile extrapolation are approximations. The service attributes Open-Meteo under CC BY 4.0. The free API is for non-commercial use; read its [terms](https://open-meteo.com/en/terms).
- Launch-window scan samples 12 forecast hours, spaced every three hours over a 36-hour horizon. Its documented weighted weather penalty is a **relative index**, not an AI model, probability of launch success, or recommendation.
- Max-Q is based on air-relative velocity. Heating is a Sutton–Graves-style proxy assuming a 1 m nose radius, not a heat-shield design calculation. Weather checks do not evaluate lightning, range safety, or certified vehicle limits.
- No orbital mechanics, targeting, Earth rotation, launch-site elevation, guidance, structural loads, aerodynamic database, powered descent, recovery, uncertainty model, or launch clearance is included.
- A maximum of 50 recent simulation responses is held in process memory. Exports are not durable history; they expire on restart or cache eviction.

## API

- `GET /api/health` — health
- `GET /api/config` — example vehicle/site presets and interface defaults
- `POST /api/simulate` — run the ascent using `weather_mode: "standard"` or `"live"`
- `GET /api/weather?site_id=cape` — explicitly fetch the current forecast
- `POST /api/windows` — rank forecast hours using the transparent weather index
- `GET /api/export/{run_id}.json` — full simulation result while it remains cached
- `GET /api/export/{run_id}.csv` — sampled telemetry while it remains cached
- `GET /docs` — interactive FastAPI documentation

## Verify

```sh
python -m pytest -q
```

## Project layout

```text
backend/
  atmosphere.py       Reference atmosphere and interpolation table
  main.py             FastAPI application, API and bounded result cache
  models.py           Validated simulation inputs
  physics.py          3-axis ascent integrator
  risk.py             Explicit screening rules
  weather.py          Open-Meteo forecast integration and relative windows
data/rockets.json     Illustrative example vehicle profiles
frontend/
  app.js              API interactions, charts, weather and export controls
  index.html          Simulation interface
  guide.html          Python-rendered method and dependency guide
  styles.css          Responsive interface styling
  vendor/             Locally served Chart.js
tests/                Unit and API contract tests
```

This repository is licensed under the MIT License in `LICENSE`.
