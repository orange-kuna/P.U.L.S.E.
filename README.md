# 🚀 P.U.L.S.E.
> **Predictive Upper-Atmosphere Launch & Simulation Engine**

An interactive, physics-driven rocket flight trajectory and atmospheric risk-analysis platform built to evaluate weather-driven scrub factors, dynamic pressure ($Max\text{-}Q$) stress, and upper-altitude wind shear structural limits.

---

## 📌 Overview

**P.U.L.S.E.** combines numerical flight dynamics with meteorological forecasting to simulate orbital rocket launches, predict mission failure vectors, and recommend optimized launch windows.

* **3-DOF Flight Dynamics Engine:** Step-by-step numerical integration ($dt = 0.01\text{s}$) modeling thrust curves, variable mass burn rates, gravity loss, and atmospheric drag.
* **Atmospheric & Weather Integration:** Live and predictive upper-atmosphere wind profiles, air density dynamics ($\rho$), dynamic pressure ($q$), and temperature gradients using open meteorological data.
* **Failure & Structural Analysis:** Real-time threshold monitoring for $Max\text{-}Q$ stress limits, lateral wind shear vectors, thermal dissipation bounds, and icing conditions.
* **AI Launch Window Optimization:** Predictive analysis of atmospheric stability to suggest scrub-minimizing launch windows and trajectory mitigations.

---

## 🛠️ Architecture & Tech Stack

* **Physics & Calculation Engine:** Python (`NumPy`, `SciPy`)
* **Backend API Service:** Python (`FastAPI`)
* **Frontend Visualization:** JavaScript, HTML5, CSS3 (`Chart.js` for real-time telemetry, `Leaflet` / `Three.js` for geospatial/3D trajectory tracking)
* **APIs:** Open-Meteo Atmospheric Sounding & Global Forecast System (GFS)
* **Development Environment:** Android (Xiaomi Pad 8 via Termux & Linux environment)

---

## 🧮 Mathematical Model & Core Equations

The physics core calculates vehicle translational motion across changing atmospheric layers:

### 1. Translational Motion Equation
$$a(t) = \frac{T(t) - D(t) - m(t) \cdot g(h)}{m(t)}$$

* $T(t)$: Altitude-adjusted thrust ($T_{sea} \rightarrow T_{vac}$)
* $D(t)$: Aerodynamic drag force $D = \frac{1}{2} \rho(h) v^2 C_d A$
* $m(t)$: Mass degradation profile over burn duration
* $g(h)$: Altitude-dependent gravitational acceleration $g(h) = g_0 \left(\frac{R_e}{R_e + h}\right)^2$

### 2. Dynamic Pressure ($Max\text{-}Q$)
$$q = \frac{1}{2} \rho(h) v^2$$

---

## 📁 Repository Structure

```text
pulse/
├── backend/
│   ├── physics/            # 3-DOF trajectory numerical solver & equations
│   ├── weather/            # API integration for atmospheric profile retrieval
│   └── main.py             # FastAPI REST endpoint
├── frontend/               # Interactive UI for telemetry, launch controls, & graphs
├── data/                   # Rocket profiles (wet/dry mass, C_d, thrust specs)
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
└── LICENSE                 # MIT License

Note:
=) I use replit agents to create the initial framework and then analyse every line of the code and tweak it according to the needs.
   (Use code with caution.)