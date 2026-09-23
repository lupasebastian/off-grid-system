from pydantic import BaseModel


class PredictionRequest(BaseModel):
    start: str
    end: str
    latitude: float
    longitude: float
    altitude: int
    timezone: str
    weather_api_url: str
    surface_tilt: int
    surface_azimuth: int
    panel_temperature_loss: float
    inverter_efficiency: float
    panel_power_watts: int
    number_of_panels: int

class PredictionResponse(BaseModel):
    status: str
    message: str