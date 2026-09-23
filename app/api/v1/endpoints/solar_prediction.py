from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.api.api_dependencies.services import get_prediction_service
from app.api.schemas.prediction_schemas import PredictionRequest, PredictionResponse
from app.api.services.prediction_service import SolarPredictionService


solar_prediction_router = APIRouter()


@solar_prediction_router.post('/get-solar-prediction')
async def get_solar_prediction(payload: PredictionRequest, prediction_service: SolarPredictionService = Depends(get_prediction_service)):
    prediction = (await prediction_service.get_pvlib_prediction(payload=payload)).sum()
    return PredictionResponse(status='ok', message=f'Estimated yield for passed parameters is {prediction} MWh')