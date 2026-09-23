from fastapi import APIRouter
from starlette.responses import JSONResponse

system_feasibility_router = APIRouter()


@system_feasibility_router.post('/get-system-report')
async def get_system_report():
    return JSONResponse({'status': 'ok', 'message': 'this will be your report'})