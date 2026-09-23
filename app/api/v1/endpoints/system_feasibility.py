from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse

from app.api.api_dependencies.services import get_system_feasibility_service
from app.api.schemas.report_schemas import SystemFeasibilityRequest
from app.api.services.system_feasibility_service import SystemFeasibilityService

system_feasibility_router = APIRouter()


@system_feasibility_router.post('/get-system-report', summary="Download Hourly Dispatch Profile")
async def get_system_report(payload: SystemFeasibilityRequest,
                            system_feasibility_service: SystemFeasibilityService = Depends(get_system_feasibility_service)):
    try:
        excel_stream = await system_feasibility_service.get_feasibility_report(payload=payload)
        headers = {
            'Content-Disposition': 'attachment; filename="hourly_dispatch_profile.xlsx"'
        }
        return StreamingResponse(
            excel_stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )

    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error occurred"
        )
