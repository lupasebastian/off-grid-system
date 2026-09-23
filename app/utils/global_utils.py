import pandas as pd
import numpy as np

import config


def generate_demand(snapshots):
    df = pd.DataFrame(index=snapshots)

    daily_hours = np.arange(24)
    base_daily_shape = (
            0.35  # baseload floor (fridges, community security lighting, basic facilities)
            + 0.15 * np.exp(-((daily_hours - 7.5) / 1.5) ** 2)  # morning breakfast bump (6:30 - 9:00 AM)
            + 0.55 * np.exp(-((daily_hours - 19.5) / 2.0) ** 2)  # sharp evening peak (6:00 - 9:30 PM)
    )
    df['daily_factor'] = np.tile(base_daily_shape, len(snapshots) // 24)

    day_of_year = df.index.dayofyear
    df['seasonal_factor'] = 1.0 + 0.10 * np.cos(2 * np.pi * (day_of_year - 45) / 365)

    np.random.seed(101)
    raw_profile = df['daily_factor'] * df['seasonal_factor']
    noise = np.random.normal(1.0, 0.10, len(snapshots))
    combined_profile = raw_profile * noise

    demand_profile = (combined_profile / combined_profile.sum()) * config.DEMAND_PER_BUILDING_MWH_ANNUALLY * config.NUM_BUILDINGS
    return demand_profile


def generate_digester_thermal_load(snapshots: pd.DatetimeIndex, total_annual_mwh: float = 200.0) -> pd.Series:
    """
    Generates a temperature-dependent hourly thermal load profile (in MW)
    for an anaerobic digester, scaled precisely to a target annual MWh sum.
    """
    day_of_year = snapshots.dayofyear.to_numpy()
    hour_of_day = snapshots.hour.to_numpy()
    seasonal_thermal_stress = np.cos(2 * np.pi * (day_of_year - 195) / 365.25)
    daily_thermal_stress = np.cos(2 * np.pi * (hour_of_day - 4) / 24)
    unscaled_profile = 1.0 + (0.45 * seasonal_thermal_stress) + (0.15 * daily_thermal_stress)
    scale_factor = total_annual_mwh / np.sum(unscaled_profile)
    scaled_profile_mw = unscaled_profile * scale_factor
    thermal_load_series = pd.Series(scaled_profile_mw, index=snapshots, name="Digester_Thermal_Load_MW")

    return thermal_load_series


def extract_weather_hourly_variables_by_name(hourly) -> dict:
    return {hourly.Variables(i).Variable(): hourly.Variables(i) for i in range(hourly.VariablesLength())}
