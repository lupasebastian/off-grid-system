import pandas as pd
import pvlib
from openmeteo_sdk.Variable import Variable

from app.api.schemas.prediction_schemas import PredictionRequest
from app.utils.global_utils import extract_weather_hourly_variables_by_name, fetch_hourly_weather_data


class SolarPredictionService:
    def __init__(self, ):
        pass

    async def get_pvlib_prediction(self, payload: PredictionRequest):
        hourly = await fetch_hourly_weather_data(payload=payload)

        # data is returned from 00:00 utc, timestamps are read in utc, need to be aligned
        utc_timestamps = pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        )

        local_timestamps = pd.DatetimeIndex(utc_timestamps).tz_convert(payload.timezone)

        pvlib_input_df = pd.DataFrame(index=pd.Index(data=local_timestamps, name="datetime"))

        extracted_variables = extract_weather_hourly_variables_by_name(hourly)

        pvlib_input_df["ghi"] = extracted_variables[Variable.shortwave_radiation].ValuesAsNumpy()
        pvlib_input_df["dni"] = extracted_variables[Variable.direct_normal_irradiance].ValuesAsNumpy()
        pvlib_input_df["dhi"] = extracted_variables[Variable.diffuse_radiation].ValuesAsNumpy()
        pvlib_input_df["temp_air"] = extracted_variables[Variable.temperature].ValuesAsNumpy()
        pvlib_input_df["wind_speed"] = extracted_variables[Variable.wind_speed].ValuesAsNumpy()

        # calculate all values in Watts
        panel_power_w = payload.panel_power_watts
        number_of_panels = payload.number_of_panels
        total_dc_power = panel_power_w * number_of_panels

        system = pvlib.pvsystem.PVSystem(
            surface_tilt=payload.surface_tilt,
            surface_azimuth=payload.surface_azimuth,
            module_parameters={
                'pdc0': total_dc_power,
                'gamma_pdc': payload.panel_temperature_loss
            },
            inverter_parameters={
                'pdc0': total_dc_power,
                'eta_inv_nom': payload.inverter_efficiency
            },
            temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm'][
                'open_rack_glass_glass'],
            losses_parameters={'soiling': 2, 'shading': 0, 'wiring': 2, 'connections': 0.5, 'mismatch': 2,
                               'availability': 1},
        )

        location = pvlib.location.Location(latitude=payload.latitude, longitude=payload.longitude,
                                           tz=payload.timezone, altitude=payload.altitude)

        mc = pvlib.modelchain.ModelChain(
            system,
            location=location,
            transposition_model='perez',
            aoi_model='no_loss',
            losses_model='pvwatts'
        )

        mc.run_model(pvlib_input_df)

        # convert predicted output to MW for PyPSA compatibility
        pvlib_input_df['predicted_dc_MW'] = pd.Series(mc.results.dc.fillna(0).clip(lower=0) / 1000000, dtype='float64')
        pvlib_input_df['predicted_ac_MW'] = pd.Series(mc.results.ac.fillna(0).clip(lower=0) / 1000000, dtype='float64')

        total_mwh = pvlib_input_df['predicted_ac_MW'].sum()
        print(f"Total Expected Yield For Chosen Period: {total_mwh:.2f} MWh")

        pvlib_input_df.index = pvlib_input_df.index.tz_localize(None)

        return pvlib_input_df['predicted_ac_MW']