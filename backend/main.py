"""FastAPI application for the P.U.L.S.E. launch simulation workbench."""

import csv
import io
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from backend.atmosphere import standard_weather
from backend.models import SimulationInput
from backend.physics import simulate
from backend.risk import assess
from backend.weather import SITES, WeatherUnavailable, get_forecast, get_site, rank_windows, weather_at

ROOT = Path(__file__).resolve().parent.parent
PROFILES = json.loads((ROOT / "data" / "rockets.json").read_text())
PROFILE_BY_ID = {profile["id"]: profile for profile in PROFILES}
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pulse")

app = FastAPI(
    title="P.U.L.S.E. — Launch Simulation Workbench",
    description="Educational rocket ascent and weather-risk simulator. Not for operational launch guidance.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
templates = Jinja2Templates(directory=ROOT / "frontend")
_results: OrderedDict[str, dict] = OrderedDict()
_result_lock = Lock()
_MAX_RESULTS = 50

DEFAULTS = {
    "profile_id": "falcon9", "site_id": "cape", "weather_mode": "standard",
    "duration_s": 420, "pitch_deg": 70, "heading_deg": 90, "throttle": 1,
    "max_q_limit_kpa": 50, "wind_limit_ms": 35,
}

LIBRARIES = [
    {
        "name": "Python", "version": "3.13", "purpose": "Application language and numerical model.",
        "why": "The simulator, API, forecast integration and guide are Python-first.",
        "limits": "Python 3.10+ recommended; use 3.13 in this Replit project.",
        "docs": "https://docs.python.org/3/",
    },
    {
        "name": "FastAPI", "version": "0.161.1", "purpose": "HTTP API, request validation, interactive OpenAPI documentation.",
        "why": "Typed Pydantic inputs and generated /docs suit the small JSON API.",
        "limits": "The result cache is in-memory and does not persist or share between processes.",
        "docs": "https://fastapi.tiangolo.com/",
    },
    {
        "name": "Uvicorn", "version": "0.54.0", "purpose": "ASGI application server.",
        "why": "Runs FastAPI for the Replit web preview on port 5000.",
        "limits": "A single development worker; not a production deployment configuration.",
        "docs": "https://www.uvicorn.org/",
    },
    {
        "name": "NumPy", "version": "2.5.4", "purpose": "Precomputed atmospheric lookup arrays and interpolation.",
        "why": "Efficient density, temperature and wind lookup during fixed time-step integration.",
        "limits": "The model's atmosphere and vehicle inputs are simplified; numerical speed does not imply flight accuracy.",
        "docs": "https://numpy.org/doc/",
    },
    {
        "name": "SciPy", "version": "1.18.1", "purpose": "Numerical integration helper for heating-load accumulation.",
        "why": "cumulative_trapezoid integrates the sampled heat-rate history.",
        "limits": "No finite-element structures, CFD, guidance optimizer or uncertainty propagation.",
        "docs": "https://docs.scipy.org/doc/scipy/",
    },
    {
        "name": "HTTPX", "version": "0.28.1", "purpose": "Bounded-timeout HTTPS access to Open-Meteo's forecast API.",
        "why": "The service uses hourly forecasts and pressure-level temperature, wind and geopotential height.",
        "limits": "Live weather requires network access. Free Open-Meteo API is for non-commercial use (<10,000 requests/day); attribution and CC BY 4.0 apply. Forecasts are not launch observations.",
        "docs": "https://www.python-httpx.org/",
    },
    {
        "name": "Jinja2", "version": "3.1.6", "purpose": "Server-rendered library/model guide.",
        "why": "Keeps guide content and HTML templating on the Python side.",
        "limits": "Not used to generate the simulator interface; the interface is plain HTML/CSS/JS.",
        "docs": "https://jinja.palletsprojects.com/",
    },
    {
        "name": "Pydantic", "version": "2.14.1", "purpose": "FastAPI's typed input validation.",
        "why": "Rejects invalid model selection, non-finite numbers and unbounded parameters.",
        "limits": "Validation constrains inputs; it does not verify rocket specifications or mission suitability.",
        "docs": "https://docs.pydantic.dev/",
    },
    {
        "name": "Chart.js", "version": "4.4.8", "purpose": "Locally vendored browser charts.",
        "why": "Draws trajectory and time-series charts directly from Python simulation telemetry.",
        "limits": "It is only the display layer. Numerical results are calculated server-side.",
        "docs": "https://www.chartjs.org/docs/latest/",
    },
    {
        "name": "pytest", "version": "9.1.1", "purpose": "Unit and API integration tests.",
        "why": "Checks the atmosphere, numerical model, risk screen and HTTP contract.",
        "limits": "Tests are examples, not validation against a flight-qualified simulator.",
        "docs": "https://docs.pytest.org/",
    },
]

MODEL_NOTES = [
    ("Coordinates", "Three-dimensional local east/north/up axes; a spherical-altitude gravity correction uses a 6,371 km Earth radius. No Earth rotation, ellipsoid, terrain, launch-site elevation or moving launch frame."),
    ("Atmosphere", "Layered dry standard-atmosphere reference through 84.852 km, with a continuous isothermal exponential extension. Live mode uses Open-Meteo hourly 2 m/surface and pressure-level forecast profiles; geometric height and dry-air density are approximate."),
    ("Vehicle", "Three visibly described example profiles, with stages, propellant consumption, altitude-adjusted thrust interpolation, configured drag coefficient and circular reference area. These illustrative values are not verified manufacturer specifications."),
    ("Integration", "Fixed 0.01 s midpoint (second-order Runge–Kutta) integration. The browser samples the calculated trajectory every 0.5 s. A simple 120 s pitch program starts after 10 s; throttle scales both thrust and propellant mass flow."),
    ("Loads", "q = ½ρvrelative². Drag follows q × Cd × reference area. Heating is a Sutton–Graves-style stagnation proxy assuming 1 m nose radius; the accumulated heat load is a trapezoidal integral."),
    ("Weather screening", "Forecast wind layers, surface rain/cloud and a simplified icing flag are shown separately. Checks compare requested thresholds; these do not establish structural or weather clearance."),
    ("Window ranking", "Twelve forecast hours sampled every 3 h for 36 h. A documented linear weather penalty ranks profile-wind, precipitation and cloud cover. It is not an AI model or probability of launch success."),
    ("Scope", "Educational local-frame ascent only. No orbital mechanics, target insertion, trajectory optimization, structural model, coupled CFD, weather-data assimilation, engine maps, reliability model, abort guidance, or flight certification."),
]


def store_result(result):
    with _result_lock:
        _results[result["id"]] = result
        _results.move_to_end(result["id"])
        while len(_results) > _MAX_RESULTS:
            _results.popitem(last=False)


def get_result(result_id):
    with _result_lock:
        result = _results.get(result_id)
        if result:
            _results.move_to_end(result_id)
        return result


def make_simulation(payload: SimulationInput):
    profile = PROFILE_BY_ID[payload.profile_id]
    site = get_site(payload.site_id)
    if payload.weather_mode == "live":
        forecast = get_forecast(site)
        weather = weather_at(site, payload.launch_time, forecast)
    else:
        weather = standard_weather()
    summary, telemetry, events = simulate(payload, profile, weather)
    result = {
        "id": __import__("uuid").uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": payload.model_dump(mode="json"),
        "profile": profile, "site": site, "weather": weather,
        "summary": summary, "risk": assess(payload, summary, weather),
        "telemetry": telemetry, "events": events,
    }
    store_result(result)
    return result


def weather_http_error(exc):
    logger.warning("Forecast unavailable: %s", exc)
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"title": "P.U.L.S.E."})


@app.get("/guide", response_class=HTMLResponse, include_in_schema=False)
def guide(request: Request):
    return templates.TemplateResponse(request, "guide.html", {
        "title": "Model & library guide · P.U.L.S.E.",
        "libraries": LIBRARIES, "notes": MODEL_NOTES,
    })


@app.get("/api/health")
def health():
    return {"status": "ok", "name": "P.U.L.S.E.", "result_cache_capacity": _MAX_RESULTS}


@app.get("/api/config")
def config():
    return {"profiles": PROFILES, "sites": SITES, "defaults": DEFAULTS}


@app.post("/api/simulate")
def run_simulation(payload: SimulationInput):
    try:
        return make_simulation(payload)
    except WeatherUnavailable as exc:
        weather_http_error(exc)


@app.get("/api/weather")
def live_weather(site_id: str = Query("cape", pattern="^(cape|vandenberg|sriharikota|mahia)$")):
    try:
        site = get_site(site_id)
        return weather_at(site, data=get_forecast(site))
    except WeatherUnavailable as exc:
        weather_http_error(exc)


@app.post("/api/windows")
def windows(payload: SimulationInput):
    try:
        return rank_windows(get_site(payload.site_id), payload.wind_limit_ms)
    except WeatherUnavailable as exc:
        weather_http_error(exc)


@app.get("/api/export/{result_id}.json")
def export_json(result_id: str):
    result = get_result(result_id)
    if not result:
        raise HTTPException(404, "Simulation has expired or does not exist. Run a new simulation.")
    content = json.dumps(result, indent=2, allow_nan=False)
    return StreamingResponse(io.BytesIO(content.encode()), media_type="application/json",
                             headers={"Content-Disposition": f'attachment; filename="pulse-{result_id[:10]}.json"'})


@app.get("/api/export/{result_id}.csv")
def export_csv(result_id: str):
    result = get_result(result_id)
    if not result:
        raise HTTPException(404, "Simulation has expired or does not exist. Run a new simulation.")
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(result["telemetry"][0]))
    writer.writeheader()
    writer.writerows(result["telemetry"])
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="pulse-{result_id[:10]}-telemetry.csv"'})

