"""Dry-air layered reference atmosphere and explicit weather provenance."""

import math
from datetime import datetime, timezone

import numpy as np

G0 = 9.80665
R_AIR = 287.05287
# US Standard Atmosphere-style geopotential layers through 84.852 km.
BASES = [0, 11000, 20000, 32000, 47000, 51000, 71000, 84852]
LAPSES = [-0.0065, 0, 0.001, 0.0028, 0, -0.0028, -0.002]


def reference_air(altitude_m: float) -> tuple[float, float, float]:
    """Return temperature K, pressure Pa, density kg/m³.

    Above 84.852 km, a continuous isothermal exponential tail is an
    educational approximation, not a thermosphere or re-entry model.
    """
    h = max(0.0, altitude_m)
    temperature, pressure = 288.15, 101325.0
    for i, lapse in enumerate(LAPSES):
        thickness = min(h, BASES[i + 1]) - BASES[i]
        if thickness < 0:
            break
        next_t = temperature + lapse * thickness
        if lapse:
            pressure *= (next_t / temperature) ** (-G0 / (R_AIR * lapse))
        else:
            pressure *= math.exp(-G0 * thickness / (R_AIR * temperature))
        temperature = next_t
        if h <= BASES[i + 1]:
            break
    if h > BASES[-1]:
        pressure *= math.exp(-G0 * (h - BASES[-1]) / (R_AIR * temperature))
    return temperature, pressure, pressure / (R_AIR * temperature)


def standard_weather() -> dict:
    layers = []
    for height in [0, 1000, 2000, 3000, 5000, 7000, 9000, 11000, 15000, 20000, 30000, 50000, 71000, 84852]:
        temp, pressure, density = reference_air(height)
        layers.append({
            "altitude_m": height, "temperature_c": temp - 273.15,
            "pressure_pa": pressure, "density_kg_m3": density,
            "wind_east_ms": 0.0, "wind_north_ms": 0.0, "wind_ms": 0.0,
        })
    return {
        "source": "standard",
        "label": "Standard atmosphere · calm-wind reference",
        "valid_at": datetime.now(timezone.utc).isoformat(),
        "surface": {"temperature_c": 15.0, "wind_ms": 0.0, "precipitation_mm": None,
                    "cloud_cover_pct": None, "humidity_pct": None},
        "layers": layers,
        "note": "Modeled dry air and zero wind, not observed weather. Rain, cloud and icing checks are unavailable. Reference model above 84.852 km is an exponential approximation.",
    }


class AirTable:
    """Precomputed 100 m interpolation table, avoiding network/large arrays per step."""

    def __init__(self, weather):
        heights = np.arange(0, 1000001, 100)
        values = np.array([reference_air(float(h)) for h in heights])
        self.temperature = values[:, 0]
        self.density = values[:, 2]
        self.pressure = values[:, 1]
        self.east = np.zeros(len(heights))
        self.north = np.zeros(len(heights))
        if weather["source"] == "open-meteo":
            layers = weather["layers"]
            z = np.array([x["altitude_m"] for x in layers])
            top = z[-1]
            mask = heights <= top
            self.temperature[mask] = np.interp(heights[mask], z, [x["temperature_c"] + 273.15 for x in layers])
            # Log density/pressure interpolation respects positive values.
            self.density[mask] = np.exp(np.interp(heights[mask], z, np.log([x["density_kg_m3"] for x in layers])))
            self.pressure[mask] = np.exp(np.interp(heights[mask], z, np.log([x["pressure_pa"] for x in layers])))
            # Blend to reference aloft over 10 km; explicitly disclosed.
            blend = np.clip((top + 10000 - heights) / 10000, 0, 1)
            upper = heights > top
            for array, key in [(self.density, "density_kg_m3"), (self.pressure, "pressure_pa")]:
                ratio = layers[-1][key] / (reference_air(top)[2 if key == "density_kg_m3" else 1])
                array[upper] *= np.exp(math.log(ratio) * blend[upper])
            self.east = np.interp(heights, z, [x["wind_east_ms"] for x in layers]) * blend
            self.north = np.interp(heights, z, [x["wind_north_ms"] for x in layers]) * blend

    def at(self, height):
        index = max(0, min(float(height) / 100, len(self.density) - 1.00001))
        low = int(index)
        fraction = index - low
        return tuple(float(a[low] + fraction * (a[low + 1] - a[low]))
                     for a in (self.temperature, self.pressure, self.density, self.east, self.north))
