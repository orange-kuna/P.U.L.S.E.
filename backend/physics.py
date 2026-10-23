"""Three-axis local-frame educational ascent integration."""

import math

import numpy as np
from scipy.integrate import cumulative_trapezoid

from backend.atmosphere import AirTable, G0

DT = 0.01
EARTH_RADIUS = 6371000


def simulate(inputs, profile, weather):
    """Fixed 0.01s midpoint (RK2) translational integration.

    x=east, y=north, z=up; pitch is measured away from vertical.
    Throttle scales thrust and mass flow, lengthening burn time.
    """
    air = AirTable(weather)
    heading = math.radians(inputs.heading_deg)
    east_heading, north_heading = math.sin(heading), math.cos(heading)
    area = math.pi * (profile["diameter_m"] / 2) ** 2
    stages = profile["stages"]
    stage_index = 0
    mass = float(profile["wet_mass_kg"])
    propellant = float(stages[0]["propellant_kg"])
    x = y = z = vx = vy = vz = 0.0
    events = [{"time_s": 0.0, "name": "Ignition", "detail": f'{profile["name"]} · {inputs.throttle * 100:.0f}% throttle'}]
    telemetry = []
    max_q = max_q_t = max_alt = max_velocity = max_heat = 0.0
    burnout_time = None
    liftoff = False
    impact = False

    def dynamics(t, height, ux, uy, uz, current_mass, stage):
        temp, pressure, density, we, wn = air.at(height)
        rx, ry, rz = ux - we, uy - wn, uz
        relative_speed = math.sqrt(rx * rx + ry * ry + rz * rz)
        q = 0.5 * density * relative_speed ** 2
        drag_factor = q * profile["cd"] * area / max(relative_speed, 0.001)
        thrust = 0.0
        if stage is not None:
            vacuum_fraction = 1 - min(pressure / 101325, 1)
            thrust = (stage["thrust_sea_n"] + vacuum_fraction * (stage["thrust_vac_n"] - stage["thrust_sea_n"])) * inputs.throttle
        # Hold vertical for first 10 s, then a prescribed 120 s pitch program.
        pitch = math.radians(inputs.pitch_deg) * min(max((t - 10) / 120, 0), 1)
        horizontal = thrust * math.sin(pitch)
        gravity = G0 * (EARTH_RADIUS / (EARTH_RADIUS + max(height, 0))) ** 2
        ax = (horizontal * east_heading - drag_factor * rx) / current_mass
        ay = (horizontal * north_heading - drag_factor * ry) / current_mass
        az = (thrust * math.cos(pitch) - drag_factor * rz) / current_mass - gravity
        # Sutton-Graves-style proxy with assumed 1 m nose radius, not heat-shield design.
        heating = 1.83e-4 * math.sqrt(max(density, 0)) * relative_speed ** 3 / 1000
        return ax, ay, az, q / 1000, temp - 273.15, density, math.hypot(we, wn), heating

    steps = int(inputs.duration_s / DT)
    for step in range(steps + 1):
        t = step * DT
        stage = stages[stage_index] if stage_index < len(stages) else None
        if stage is not None and propellant <= 1e-6:
            events.append({"time_s": round(t, 2), "name": f'{stage["name"]} cutoff', "detail": "Usable propellant depleted"})
            if stage_index + 1 < len(stages):
                mass -= stage["dry_mass_kg"]
                stage_index += 1
                stage = stages[stage_index]
                propellant = float(stage["propellant_kg"])
                events.append({"time_s": round(t, 2), "name": "Stage separation", "detail": f'{stage["name"]} ignition; previous dry stage discarded'})
            else:
                stage_index += 1
                stage = None
                burnout_time = round(t, 2)
        dyn = dynamics(t, z, vx, vy, vz, mass, stage)
        ax, ay, az, q, temp, density, wind, heat = dyn
        velocity = math.sqrt(vx * vx + vy * vy + vz * vz)
        if q > max_q:
            max_q, max_q_t = q, t
        max_alt = max(max_alt, z / 1000)
        max_velocity = max(max_velocity, velocity)
        max_heat = max(max_heat, heat)
        if step % 50 == 0 or impact or step == steps:
            telemetry.append({
                "time_s": round(t, 2), "altitude_km": round(max(0, z) / 1000, 5),
                "velocity_ms": round(velocity, 3), "q_kpa": round(q, 5),
                "mass_kg": round(mass, 2), "acceleration_g": round(math.sqrt(ax*ax + ay*ay + az*az) / G0, 4),
                "downrange_km": round((x * east_heading + y * north_heading) / 1000, 5),
                "crossrange_km": round((x * north_heading - y * east_heading) / 1000, 5),
                "density_kg_m3": density, "wind_ms": round(wind, 3),
                "temperature_c": round(temp, 3), "heating_kw_m2": round(heat, 4),
            })
        if impact or step == steps:
            break
        # Pad constraint: a low thrust-to-weight ratio cannot launch underground.
        if z <= 0 and vz <= 0 and az <= 0 and not liftoff:
            if not any(e["name"] == "Insufficient liftoff thrust" for e in events):
                events.append({"time_s": round(t, 2), "name": "Insufficient liftoff thrust", "detail": "Vehicle remains on pad until thrust exceeds weight."})
            flow = stage["propellant_kg"] / stage["burn_time_s"] * inputs.throttle if stage else 0
            used = min(propellant, flow * DT)
            propellant -= used
            mass -= used
            continue
        if not liftoff:
            liftoff = True
            events.append({"time_s": round(t, 2), "name": "Liftoff", "detail": "Vertical thrust exceeds vehicle weight"})
        flow = stage["propellant_kg"] / stage["burn_time_s"] * inputs.throttle if stage else 0
        used = min(propellant, flow * DT)
        mid = dynamics(t + DT / 2, max(0, z + vz * DT / 2),
                       vx + ax * DT / 2, vy + ay * DT / 2, vz + az * DT / 2,
                       mass - used / 2, stage)
        x += (vx + ax * DT / 2) * DT
        y += (vy + ay * DT / 2) * DT
        z += (vz + az * DT / 2) * DT
        vx += mid[0] * DT
        vy += mid[1] * DT
        vz += mid[2] * DT
        mass -= used
        propellant -= used
        if z < 0:
            z = 0
            impact = True
            events.append({"time_s": round(t + DT, 2), "name": "Ground intercept", "detail": "Integration stopped at local ground plane; no recovery model."})
    events.append({"time_s": round(max_q_t, 2), "name": "Maximum dynamic pressure", "detail": f"{max_q:.2f} kPa"})
    events.append({"time_s": round(t, 2), "name": "Simulation complete", "detail": "Ground intercept" if impact else "Requested simulation horizon reached; not an orbital insertion claim"})
    layers = weather["layers"]
    shear = max((math.hypot(b["wind_east_ms"] - a["wind_east_ms"], b["wind_north_ms"] - a["wind_north_ms"])
                 / max((b["altitude_m"] - a["altitude_m"]) / 1000, 0.001)
                 for a, b in zip(layers, layers[1:])), default=0)
    heat_load = cumulative_trapezoid([row["heating_kw_m2"] for row in telemetry],
                                     [row["time_s"] for row in telemetry], initial=0)
    summary = {
        "max_altitude_km": round(max_alt, 3), "max_velocity_ms": round(max_velocity, 2),
        "max_q_kpa": round(max_q, 3), "max_q_time_s": round(max_q_t, 2),
        "burnout_time_s": burnout_time, "flight_time_s": round(t, 2),
        "max_heating_kw_m2": round(max_heat, 3), "max_shear_ms_km": round(shear, 3),
        "heat_load_kj_m2": round(float(heat_load[-1]), 3),
    }
    return summary, telemetry, sorted(events, key=lambda e: e["time_s"])
