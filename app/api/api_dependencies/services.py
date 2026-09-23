from typing import Annotated

from fastapi.params import Depends

from app.api.services.prediction_service import SolarPredictionService
from app.api.services.system_feasibility_service import SystemFeasibilityService


async def get_prediction_service() -> SolarPredictionService:
    return SolarPredictionService()


async def get_system_feasibility_service(solar_prediction_service: Annotated[SolarPredictionService, Depends(get_prediction_service)]) -> SystemFeasibilityService:
    return SystemFeasibilityService(solar_prediction_service=solar_prediction_service)
