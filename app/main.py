from fastapi import FastAPI

from app.api.v1.api_router import api_v1_router

main_app = FastAPI()

main_app.include_router(api_v1_router)

