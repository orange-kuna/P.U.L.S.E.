"""Transparent educational screening; no launch approval or probability claims."""


def assess(inputs, summary, weather):
    checks = []

    def check(name, value, unit, limit, detail):
        status = "exceeded" if value > limit else "caution" if value >= limit * 0.8 else "nominal"
        checks.append({"name": name, "value": round(value, 3), "unit": unit,
                       "limit": limit, "status": status, "detail": detail})

    check("Dynamic pressure", summary["max_q_kpa"], "kPa", inputs.max_q_limit_kpa,
          "Peak air-relative dynamic pressure against your selected limit; no structural stress solver.")
    check("Profile wind", max(l["wind_ms"] for l in weather["layers"]), "m/s", inputs.wind_limit_ms,
          "Maximum forecast-layer wind, not a vehicle-certified wind envelope.")
    check("Vertical wind shear", summary["max_shear_ms_km"], "m/s/km", 15,
          "Vector wind difference per km between forecast levels; illustrative threshold.")
    check("Heating proxy", summary["max_heating_kw_m2"], "kW/m²", 500,
          "Sutton-Graves-style stagnation estimate, 1 m nose radius; illustrative threshold only.")
    surface = weather["surface"]
    if weather["source"] == "open-meteo":
        check("Precipitation", surface["precipitation_mm"], "mm/h", 1,
              "Forecast precipitation. Lightning, electric fields and cloud geometry are not assessed.")
        icing = surface["temperature_c"] <= 2 and surface["humidity_pct"] >= 80
        checks.append({"name": "Surface icing conditions", "value": int(icing), "unit": "flag",
                       "limit": 0, "status": "caution" if icing else "nominal",
                       "detail": "Simplified screen: temperature ≤2°C and humidity ≥80%. Not an icing model."})
    else:
        checks.append({"name": "Weather completeness", "value": None, "unit": "", "limit": None,
                       "status": "caution", "detail": "Calm reference only. Precipitation, cloud, lightning and icing are not assessed."})
    overall = "exceeded" if any(c["status"] == "exceeded" for c in checks) else "caution" if any(c["status"] == "caution" for c in checks) else "nominal"
    return {"overall": overall, "checks": checks}
