import openmeteo_requests
import pandas as pd
import pvlib
from openmeteo_sdk.Variable import Variable

from utils import extract_weather_hourly_variables_by_name
import config

def get_pvlib_prediction(start, end):
    filename = f'generation_profiles/{start} - {end} {config.LONGITUDE} {config.LATITUDE}_{config.NUMBER_OF_PANELS}_panels.csv'.replace(' ', '_').replace(':', '-')
    # try:
    #     df_input_lib = pd.read_csv(filename, sep=';', index_col='datetime', parse_dates=True)
    #     print('file found, skipping api query')
    #     return df_input_lib['predicted_ac_MW']
    # except Exception as exc:
    #     print(exc)
    #     print('no file found, generating prediction')
    openmeteo = openmeteo_requests.Client()

    # TODO maybe add another forecast model and average results?
    params = {
            "latitude": config.LATITUDE,
            "longitude": config.LONGITUDE,
            "hourly": ["shortwave_radiation", "direct_normal_irradiance", "diffuse_radiation", "temperature_2m",
                       "wind_speed_10m"],
            "timezone": "auto",
            "wind_speed_unit": "ms",
        "start_date": start.date(),
        "end_date": end.date()
        }

    url = config.WEATHER_API_URL
    location = pvlib.location.Location(latitude=config.LATITUDE, longitude=config.LONGITUDE,
                                           tz=config.TIMEZONE, altitude=config.ALTITUDE)

    responses = openmeteo.weather_api(url, params=params)

    response = responses[0]

    hourly = response.Hourly()

    # data is returned from 00:00 utc, timestamps are read in utc, need to be aligned
    utc_timestamps = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
        )

    local_timestamps = pd.DatetimeIndex(utc_timestamps).tz_convert(config.TIMEZONE)

    pvlib_input_df = pd.DataFrame(index=pd.Index(data=local_timestamps, name="datetime"))

    extracted_variables = extract_weather_hourly_variables_by_name(hourly)

    pvlib_input_df["ghi"] = extracted_variables[Variable.shortwave_radiation].ValuesAsNumpy()
    pvlib_input_df["dni"] = extracted_variables[Variable.direct_normal_irradiance].ValuesAsNumpy()
    pvlib_input_df["dhi"] = extracted_variables[Variable.diffuse_radiation].ValuesAsNumpy()
    pvlib_input_df["temp_air"] = extracted_variables[Variable.temperature].ValuesAsNumpy()
    pvlib_input_df["wind_speed"] = extracted_variables[Variable.wind_speed].ValuesAsNumpy()

    # calculate all values in Watts
    panel_power_w = config.PANEL_POWER_WATTS
    number_of_panels = config.NUMBER_OF_PANELS
    total_dc_power = panel_power_w * number_of_panels

    # old PV mount
    system = pvlib.pvsystem.PVSystem(
        surface_tilt=config.SURFACE_TILT,
        surface_azimuth=config.SURFACE_AZIMUTH,
        module_parameters={
            'pdc0': total_dc_power,
            'gamma_pdc': config.PANEL_TEMPERATURE_LOSS
        },
        inverter_parameters={
            'pdc0': total_dc_power,
            'eta_inv_nom': config.INVERTER_EFFICIENCY
        },
        temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass'],
        losses_parameters={'soiling': 2, 'shading': 0, 'wiring': 2, 'connections': 0.5, 'mismatch': 2, 'availability': 1},
    )

    # new PV mount
    # tracker_mount = pvlib.pvsystem.SingleAxisTrackerMount(
    #     axis_tilt=config.SURFACE_TILT,  # Horizontal tracker axis parallel to ground
    #     axis_azimuth=config.SURFACE_AZIMUTH,  # Axis oriented North-South
    #     max_angle=60,  # Maximum rotation angle
    #     backtrack=True,  # Prevents row-to-row shading
    #     gcr=0.40  # Ground Coverage Ratio
    # )
    #
    # BIFACIALITY_FACTOR = 0.75
    # DESERT_SAND_ALBEDO = 0.25
    # bifacial_gain_multiplier = 1.0 + (BIFACIALITY_FACTOR * DESERT_SAND_ALBEDO * 0.5)
    # bifacial_adjusted_dc_power = total_dc_power * bifacial_gain_multiplier
    #
    # pv_array = pvlib.pvsystem.Array(
    #     mount=tracker_mount,  # Mount goes here inside the Array class!
    #     module_parameters={
    #         'pdc0': bifacial_adjusted_dc_power,
    #         'gamma_pdc': config.PANEL_TEMPERATURE_LOSS
    #     },
    #     temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass'],
    # )
    #
    # system = pvlib.pvsystem.PVSystem(
    #     arrays=[pv_array],  # Feeds the array list directly into the system
    #     inverter_parameters={
    #         'pdc0': total_dc_power,
    #         'eta_inv_nom': config.INVERTER_EFFICIENCY
    #     },
    #     losses_parameters={'soiling': 2, 'shading': 0, 'wiring': 2, 'connections': 0.5, 'mismatch': 2,
    #                        'availability': 1},
    # )
    # new PV mount END

    mc = pvlib.modelchain.ModelChain(
        system,
        location = location,
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
    pvlib_input_df.to_csv(filename, sep=';', index='datetime')
    #
    # with pd.option_context('display.max_rows', None, 'display.max_columns', None):
    #     print(pvlib_input_df.head(n=100))

    return pvlib_input_df['predicted_ac_MW']