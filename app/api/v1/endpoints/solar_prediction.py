from fastapi import APIRouter
from starlette.responses import JSONResponse


solar_prediction_router = APIRouter()


@solar_prediction_router.post('/get-solar-prediction')
async def get_solar_prediction():
    return JSONResponse({'status': 'ok', 'message': 'this will be your prediction'})