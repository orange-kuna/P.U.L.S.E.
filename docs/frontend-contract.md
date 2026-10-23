# P.U.L.S.E. frontend contract

The app is Python-first. FastAPI serves `frontend/index.html` and mounts `/static` from `frontend/`. Build plain HTML/CSS/JavaScript in that folder, no React or npm. Use relative fetch URLs. No auth is needed. Do not use emojis anywhere in the UI.

## Product

P.U.L.S.E. is an educational flight-dynamics workbench for people exploring how atmosphere and rocket parameters affect a launch. It should feel precise and responsive, not like a generic admin app. It is NOT flight-certified guidance. All rocket presets are illustrative, not manufacturer mission predictions.

## Screens (client-side views)

- `/` Simulation: configure, run, inspect computed trajectory/telemetry, risk checks and timeline; export JSON and CSV.
- Atmosphere view: inspect the selected simulation's atmosphere and optionally fetch a real forecast.
- Launch windows view: fetch and rank actual forecast hours for the chosen site with a transparent heuristic (NOT AI).
- Model & libraries view: show methodology and library documentation at `/guide`, rendered by Python separately. Link to that page.

## API

GET `/api/config` returns:
```
{profiles:[{id,name,description,wet_mass_kg,diameter_m,stages:[{name,propellant_kg,dry_mass_kg,thrust_sea_n,thrust_vac_n,burn_time_s}],cd}],
sites:[{id,name,region,latitude,longitude}],defaults:{profile_id:"falcon9",site_id:"cape",weather_mode:"standard",duration_s:420,pitch_deg:70,heading_deg:90,throttle:1,max_q_limit_kpa:50,wind_limit_ms:35}}
```

POST `/api/simulate`, body:
```
{profile_id,site_id,weather_mode:"standard"|"live",duration_s:60..900,pitch_deg:0..85,heading_deg:0..360,throttle:0.5..1,max_q_limit_kpa:5..100,wind_limit_ms:5..100}
```
Optional launch_time ISO UTC within next 6 days. All defaults on backend.
Returns:
```
{id,created_at,inputs,profile,site,
weather:{source:"standard"|"open-meteo",label,valid_at, surface:{temperature_c,wind_ms,precipitation_mm,cloud_cover_pct,humidity_pct},layers:[{altitude_m,temperature_c,pressure_pa,density_kg_m3,wind_east_ms,wind_north_ms,wind_ms}],note},
summary:{max_altitude_km,max_velocity_ms,max_q_kpa,max_q_time_s,burnout_time_s,flight_time_s,max_heating_kw_m2,max_shear_ms_km},
risk:{overall:"nominal"|"caution"|"exceeded",checks:[{name,value,unit,limit,status:"nominal"|"caution"|"exceeded",detail}]},
telemetry:[{time_s,altitude_km,velocity_ms,q_kpa,mass_kg,acceleration_g,downrange_km,crossrange_km,density_kg_m3,wind_ms,temperature_c,heating_kw_m2}],
events:[{time_s,name,detail}]}
```
Default simulation should run on initial load and update UI with real computed data. Label the default weather as STANDARD ATMOSPHERE, never LIVE. Show actual simulation statuses not hardcoded "go". Retain previous results if a request fails, with clear error.

GET `/api/weather?site_id=cape` returns the weather object above, using live Open-Meteo. Failures return 502 `{detail:"..."}` — never silently fall back.

POST `/api/windows`, same body as simulate, returns:
```
{source:"Open-Meteo hourly forecast",method:"...",site,windows:[{launch_time,wind_ms,precipitation_mm,cloud_cover_pct,score,status:"nominal"|"caution"|"exceeded",reasons:[string]}],recommended:{...same window},note}
```
12 forecast hours sampled every 3 hours over 36 hours. Loading and error states necessary. No mock windows.

GET `/api/export/{id}.json` full result download, `/api/export/{id}.csv` telemetry CSV. In-memory bounded results, downloads valid for this process until evicted. No saved-history claim.
GET `/guide` detailed Python-rendered library and model guide. `/api/health` health check. `/docs` FastAPI interactive API docs.

## Visualization

Use locally vendored Chart.js 4.4.8 at `/static/vendor/chart.umd.js` (main agent downloads). Quantitative charts must reflect real returned telemetry: time in seconds numeric x-axis, one metric per axis or clearly labeled dual axes, units explicit. Can draw a local trajectory visualization with SVG/canvas (downrange vs altitude); must be driven by the telemetry, not a fake map. Do not need map or globe libraries. No made-up uncertainty bands. Distinguish calculated maximum from end-of-simulation altitude.

## Ownership

You own ONLY frontend/index.html, frontend/styles.css, frontend/app.js and optional small frontend SVG assets. Main agent owns Python, vendor library download, docs and tests. Do not edit backend or workflows. All UI controls/nav/buttons must work. Use accessible labels and responsive layout. Support loading, error, result, and mobile states. Derive memorable palette from the aerospace product domain. Prioritize information density and polish. Invest in subtle transitions and useful interactions; avoid generic template UI.
