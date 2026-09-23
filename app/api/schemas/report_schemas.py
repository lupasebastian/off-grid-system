from typing import Any

from pydantic import BaseModel, Base64Bytes

from app.api.schemas.prediction_schemas import PredictionRequest


class SystemFeasibilityRequest(PredictionRequest):
    simulation_year: int
    bess_capacity_mwh: float
    bess_power_mwh: float
    panel_power_watts: int
    number_of_panels: int
    biogas_boiler_thermal_efficiency: float
    digester_constant_output_mw: float
    electrical_efficiency: float
    chp_thermal_efficiency: float
    kwh_in_m3_of_biogas: float
    demand_per_building_mwh_annually: float| int
    num_buildings: int