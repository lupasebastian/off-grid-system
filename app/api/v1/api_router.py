from fastapi import APIRouter

from app.api.v1.endpoints.solar_prediction import solar_prediction_router
from app.api.v1.endpoints.system_feasibility import system_feasibility_router

api_v1_router = APIRouter()

api_v1_router.include_router(solar_prediction_router, prefix='/prediction')
api_v1_router.include_router(system_feasibility_router, prefix='/system')