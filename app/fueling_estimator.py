"""
Exercise fueling estimator for Peak V1.

Calculates estimated fluid loss, sodium loss, and carbohydrate expenditure
for a planned run, using the runner's body weight, gender, intended speed and
distance, and forecasted weather at the run location and time.

Science references
──────────────────
Sweat rate / sodium:
  Barnes et al. (2019). Normative data for sweating rate, sweat sodium
  concentration, and sweat sodium loss in athletes: an update and analysis by
  sport. Journal of Sports Sciences, 37(20), 2356–2366.
  Average sweat [Na⁺] ≈ 950 mg/L (male), ≈ 800 mg/L (female).

Carbohydrate oxidation:
  Ainsworth et al. (2011). Compendium of Physical Activities: A second update
  of codes and MET values. Medicine & Science in Sports & Exercise, 43(8),
  1575–1581.
  Carb fraction scaling from intensity (% VO₂max) follows the well-documented
  crossover concept (Brooks & Mercier, 1994).

Weather:
  Open-Meteo free forecast API (https://open-meteo.com).
  Geocoding: Open-Meteo geocoding API.
"""

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Defaults used when weather cannot be fetched
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULT_TEMP_C = 18.0       # mild day
_DEFAULT_HUMIDITY_PCT = 55.0  # moderate humidity

_HTTP_TIMEOUT_SECONDS = 5


# ──────────────────────────────────────────────────────────────────────────────
# Weather helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_json(url: str) -> Optional[Dict[str, Any]]:
    """HTTP GET → parsed JSON dict, or None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PeakV1/1.0"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        log.warning("HTTP fetch failed (%s): %s", url, exc)
        return None


def _geocode(location_name: str) -> Optional[Tuple[float, float]]:
    """Return (latitude, longitude) for a free-text place name, or None."""
    query = urllib.parse.quote(location_name)
    url = (
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={query}&count=1&language=en&format=json"
    )
    data = _get_json(url)
    if data is None:
        return None
    results = data.get("results") or []
    if not results:
        return None
    first = results[0]
    lat = first.get("latitude")
    lon = first.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _weather_at(lat: float, lon: float, planned_at: datetime) -> Tuple[float, float]:
    """
    Fetch forecasted temperature (°C) and relative humidity (%) from
    Open-Meteo for the hour nearest to *planned_at*.

    Returns (temp_c, humidity_pct). Falls back to defaults on any error.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        "&hourly=temperature_2m,relative_humidity_2m"
        "&forecast_days=16&timezone=auto"
    )
    data = _get_json(url)
    if data is None:
        return _DEFAULT_TEMP_C, _DEFAULT_HUMIDITY_PCT

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    humids = hourly.get("relative_humidity_2m") or []

    if not times:
        return _DEFAULT_TEMP_C, _DEFAULT_HUMIDITY_PCT

    # Make planned_at timezone-aware for comparison
    target = planned_at
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)

    # Find the forecast slot closest in time to the planned run
    best_idx = 0
    best_diff = float("inf")
    for i, ts_str in enumerate(times):
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            diff = abs((ts - target).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best_idx = i
        except ValueError:
            continue

    temp = temps[best_idx] if best_idx < len(temps) else None
    hum = humids[best_idx] if best_idx < len(humids) else None
    return (
        float(temp) if temp is not None else _DEFAULT_TEMP_C,
        float(hum) if hum is not None else _DEFAULT_HUMIDITY_PCT,
    )


def fetch_weather_for_plan(
    location: Optional[str],
    planned_at: datetime,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (temp_celsius, humidity_pct) for the planned run location and time.
    Returns (None, None) when no location is provided or on any API failure.
    """
    if not location:
        return None, None

    coords = _geocode(location)
    if coords is None:
        log.info("Could not geocode location: %r", location)
        return None, None

    lat, lon = coords
    temp, hum = _weather_at(lat, lon, planned_at)
    return temp, hum


# ──────────────────────────────────────────────────────────────────────────────
# Fueling estimation
# ──────────────────────────────────────────────────────────────────────────────

def estimate_run_fueling(
    weight_kg: int,
    is_male: bool,
    distance_km: float,
    speed_kph: float,
    temp_celsius: Optional[float] = None,
    humidity_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Estimate fluid loss, sodium loss, and carbohydrate expenditure for a run.

    Model summary
    ─────────────────────────────────────────────────────────────────────────
    Sweat rate (L/hr)
      base_rate = 0.5 + max(0, temp_c) × 0.04
        → 0.5 L/hr at 0 °C, 1.9 L/hr at 35 °C (linear with temperature)
      humidity_factor = 1 + max(0, humidity% − 40) × 0.005
        → +0.5 % per % RH above 40 % (less evaporative cooling → more sweat)
      weight_factor = (weight_kg / 70) ^ 0.5
        → square-root scaling; a 100 kg runner sweats ~20 % more than 70 kg
      gender_factor = 1.0 (male) | 0.85 (female)  [Barnes et al. 2019]
      sweat_rate = base_rate × humidity_factor × weight_factor × gender_factor
      Physiological bounds: clamped to [0.3, 3.0] L/hr

    Sodium loss (mg)
      Sweat [Na⁺]: 950 mg/L (male) | 800 mg/L (female)  [Barnes et al. 2019]
      total_sodium = sweat_rate × duration_hr × [Na⁺]

    Carbohydrate expenditure (g)
      MET ≈ 2.8 + 0.82 × speed_kph  (Compendium of Physical Activities)
      kcal/hr ≈ MET × weight_kg  (standard exercise physiology approximation)
      % VO₂max → % energy from carbs:
        VO₂ (ml/kg/min) = MET × 3.5
        VO₂max assumed 45 ml/kg/min (male) | 40 ml/kg/min (female)
        intensity = min(1.0, VO₂ / VO₂max)
        carb_fraction = 0.40 + intensity × 0.35  → 40 % (low) to 75 % (max)
      total_carbs = (kcal/hr × duration_hr × carb_fraction) / 4  [4 kcal/g]
    ─────────────────────────────────────────────────────────────────────────

    Returns
    -------
    {
      "estimated_fluid_ml":    int   total fluid to replace (mL)
      "estimated_sodium_mg":   int   total sodium to replace (mg)
      "estimated_carbs_g":     int   total carbohydrate to consume (g)
      "weather_temp_c":        float | None   temperature used in model
      "weather_humidity_pct":  float | None   humidity used in model
    }
    """
    temp_c = temp_celsius if temp_celsius is not None else _DEFAULT_TEMP_C
    hum = humidity_pct if humidity_pct is not None else _DEFAULT_HUMIDITY_PCT
    duration_hr = distance_km / speed_kph

    # ── Sweat rate ────────────────────────────────────────────────────────────
    base_rate = 0.5 + max(0.0, temp_c) * 0.04
    humidity_factor = 1.0 + max(0.0, (hum - 40.0)) * 0.005
    weight_factor = (weight_kg / 70.0) ** 0.5
    gender_factor = 1.0 if is_male else 0.85

    sweat_rate_L_hr = base_rate * humidity_factor * weight_factor * gender_factor
    sweat_rate_L_hr = max(0.3, min(3.0, sweat_rate_L_hr))

    total_fluid_ml = sweat_rate_L_hr * duration_hr * 1_000.0  # L → mL

    # ── Sodium ────────────────────────────────────────────────────────────────
    sodium_conc = 950.0 if is_male else 800.0  # mg/L
    total_sodium_mg = sweat_rate_L_hr * duration_hr * sodium_conc

    # ── Carbohydrate ──────────────────────────────────────────────────────────
    met = max(6.0, 2.8 + 0.82 * speed_kph)
    kcal_hr = met * weight_kg

    vo2_ml_kg_min = met * 3.5
    vo2max = 45.0 if is_male else 40.0
    intensity = min(1.0, vo2_ml_kg_min / vo2max)
    carb_fraction = 0.40 + intensity * 0.35  # 40 % – 75 %

    total_carbs_g = (kcal_hr * duration_hr * carb_fraction) / 4.0

    return {
        "estimated_fluid_ml": round(total_fluid_ml),
        "estimated_sodium_mg": round(total_sodium_mg),
        "estimated_carbs_g": round(total_carbs_g),
        "weather_temp_c": round(temp_c, 1) if temp_celsius is not None else None,
        "weather_humidity_pct": round(hum, 1) if humidity_pct is not None else None,
    }
