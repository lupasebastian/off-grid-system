from pandas import date_range, Series
import datetime

import config
from pypsa import Network

from app.api.services.prediction_service import SolarPredictionService
from app.utils.global_utils import generate_demand, generate_digester_thermal_load

class SystemFeasibilityService:
    def __init__(self, solar_prediction_service: SolarPredictionService):
        self.solar_prediction_service = solar_prediction_service

    async def get_report(self):
        # TODO network setup
        # initialize network
        n = Network(name='off_grid')

        # set hourly snapshots for a whole year in question
        sim_start = datetime.datetime.combine(
            datetime.datetime.now().replace(day=1, month=1, year=config.SIMULATION_YEAR), datetime.time.min)
        sim_end = datetime.datetime.combine(sim_start.replace(month=12, day=31), datetime.time.max).replace(
            microsecond=0)
        n.set_snapshots(date_range(start=sim_start, end=sim_end, freq='h'))

        # TODO ELECTRICITY ELECTRICITY ELECTRICITY ELECTRICITY ELECTRICITY ELECTRICITY ELECTRICITY

        hourly_demand = generate_demand(snapshots=n.snapshots)

        n.add("Bus", "Electricity_Bus", carrier="AC")

        n.add("Carrier", "AC", co2_emissions=0.0)

        # attach electricity demand to electricity bus
        n.add("Load", "Electrical_Load",
              bus="Electricity_Bus",
              p_set=hourly_demand.values)

        # create a dedicated internal DC Bus, storage and charger/discharger objects for the storage system
        n.add("Bus", "BESS_DC_Bus")
        n.add(
            "Store",
            "BESS_reservoir",
            bus="BESS_DC_Bus",
            e_nom=config.BESS_CAPACITY_MWH,
            e_min_pu=0.15,
            e_max_pu=0.95,
            e_cyclic=True,
            standing_loss=0.0,
        )

        n.add(
            "Link",
            "BESS_charger",
            bus0="Electricity_Bus",
            bus1="BESS_DC_Bus",
            p_nom=config.BESS_POWER_MWH,
            efficiency=0.95,
            p_nom_extendable=False,
            p_max_pu=1.0,
            p_min_pu=0.0,
            marginal_cost=0.0
        )

        n.add(
            "Link",
            "BESS_discharger",
            bus0="BESS_DC_Bus",
            bus1="Electricity_Bus",
            p_nom=config.BESS_POWER_MWH,
            efficiency=0.95,
            p_nom_extendable=False,
            p_max_pu=1.0,
            p_min_pu=0.0,
            marginal_cost=0.0
        )

        # attach pv Generator with predicted output
        solar_profile_raw = self.solar_prediction_service.get_pvlib_prediction(start=sim_start, end=sim_end)
        # with pd.option_context('display.max_rows', None, 'display.max_columns', None):
        #     print(solar_profile_raw.head(n=100))

        true_farm_size_mw = config.PANEL_POWER_WATTS * config.NUMBER_OF_PANELS / 1000000

        # pv prediction is converted to efficiency ratio at given snapshots
        normalized_weather_shape = (solar_profile_raw / true_farm_size_mw).clip(lower=0.0, upper=1.0)

        # nominal farm power in MW equals configurable number of panel * their nominal power divided by 1000000 to get MW
        n.add("Generator", "PV_System",
              bus="Electricity_Bus",
              p_nom_extendable=False,
              p_nom=true_farm_size_mw,
              p_max_pu=normalized_weather_shape,
              marginal_cost=-1.0)

        # sink bus for electricity (best to never be used - excess gas should be best vented through a heater)
        n.add('Bus', 'Electricity_Atmosphere_Bus')

        n.add(
            "Store", "Electricity_Atmosphere_Dump",
            bus="Electricity_Atmosphere_Bus",
            e_nom_extendable=True,
            e_cyclic=False,
            marginal_cost=0.0
        )

        n.add(
            "Link", "Electrical_Emergency_Dump",
            bus0='Electricity_Bus',
            bus1="Electricity_Atmosphere_Bus",
            p_nom=0.0,
            p_nom_extendable=True,
            efficiency=1.0,
            marginal_cost=100.0,
            p_min_pu=0.0,
            p_max_pu=1.0
        )

        # TODO HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT HEAT

        n.add("Bus", "Heat_Bus", carrier="heat")

        n.add("Carrier", "heat", co2_emissions=0.0)

        # TODO BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS BIOGAS

        n.add("Bus", "Biogas_Bus", carrier="biogas")

        n.add("Carrier", "biogas", co2_emissions=0.0)

        DIGESTER_VOLUME_M3 = 1000

        hourly_digester_heat = generate_digester_thermal_load(
            snapshots=n.snapshots,
            total_annual_mwh=200
        )

        # dedicated heat atmosphere bus as an emergency sink (preferred over direct electrical vent)
        n.add('Bus', 'Heat_Atmosphere_Bus')

        # thermal storage dump
        n.add(
            "Store", "Heat_Atmosphere_Dump",
            bus="Heat_Atmosphere_Bus",
            e_nom_extendable=True,
            e_cyclic=False,
            marginal_cost=0.0
        )

        n.add(
            "Link", "Heat_Emergency_Vent",
            bus0='Heat_Bus',
            bus1="Heat_Atmosphere_Bus",
            p_nom=0.0,
            p_nom_extendable=True,
            efficiency=1.0,
            marginal_cost=0.0,
            p_min_pu=0.0,
            p_max_pu=1.0,
        )

        n.add(
            "Link",
            "Biogas_Backup_Heater",
            bus0="Biogas_Bus",
            bus1="Heat_Bus",
            p_nom=0.35,  # huge non-realistic power, just so the energy has somewhere to vent
            p_nom_extendable=False,
            efficiency=config.BIOGAS_BOILER_THERMAL_EFFICIENCY,
            marginal_cost=15.0,
            p_min_pu=0.0,
            p_max_pu=1.0,
        )

        n.add("Load", "Digester_Thermal_Load",
              bus="Heat_Bus",
              p_set=hourly_digester_heat.values)

        n.add(
            "Generator", "Digester_Biogas_Output",
            bus="Biogas_Bus",
            p_nom=config.DIGESTER_CONSTANT_OUTPUT_MW,
            p_max_pu=1.0,
            p_min_pu=1.0,
            p_nom_extendable=False,
            marginal_cost=0.0
        )

        n.add(
            "Store", "Biogas_Storage_Tank",
            bus="Biogas_Bus",
            e_nom=5.0,  # 1000 m3
            e_nom_extendable=False,
            e_cyclic=False,
            e_initial=0.5,  # start with some fuel to get things going (100 m³)
            standing_loss=0.001
        )

        # also best to never use, gas should be vented through heater to get heat as a by-product

        n.add('Bus', 'Biogas_Atmosphere_Bus')

        n.add(
            "Store", "Biogas_Atmosphere_Dump",
            bus="Biogas_Atmosphere_Bus",
            e_nom_extendable=True,
            e_cyclic=False,
            marginal_cost=0.0
        )

        n.add(
            "Link", "Biogas_Emergency_Flare",
            bus0='Biogas_Bus',
            bus1="Biogas_Atmosphere_Bus",
            p_nom=0.0,
            p_nom_extendable=True,
            efficiency=1.0,
            marginal_cost=30.0,
            p_min_pu=0.0,
            p_max_pu=1.0,
        )

        chp_max_profile = Series(1.0, index=n.snapshots)
        night_max_hours = chp_max_profile.index.hour < 5
        chp_max_profile[night_max_hours] = 0.0

        chp_min_profile = Series(0.85, index=n.snapshots)
        night_min_hours = chp_min_profile.index.hour < 5
        chp_min_profile[night_min_hours] = 0.0

        n.add("Link", "CHP_Biogas_Generator",
              bus0="Biogas_Bus",
              bus1="Electricity_Bus",
              bus2="Heat_Bus",
              efficiency=config.ELECTRICAL_EFFICIENCY,
              # efficiencies based on an example of turning 120 kW of fuel into 50 kW el and 60 kW of heat
              efficiency2=config.CHP_THERMAL_EFFICIENCY,
              p_nom=0.05 / config.ELECTRICAL_EFFICIENCY,  # p_nom is always applied to input energy (bus0)
              p_nom_extendable=False,
              p_min_pu=chp_min_profile,
              p_max_pu=chp_max_profile,
              marginal_cost=20.0,
              committable=True,
              min_down_time=2,
              min_up_time=2,
              )

        n.add("Link", "CHP_Biogas_Generator_2",
              bus0="Biogas_Bus",
              bus1="Electricity_Bus",
              bus2="Heat_Bus",
              efficiency=config.ELECTRICAL_EFFICIENCY,
              # efficiencies based on an example of turning 120 kW of fuel into 50 kW el and 60 kW of heat
              efficiency2=config.CHP_THERMAL_EFFICIENCY,
              p_nom=0.05 / config.ELECTRICAL_EFFICIENCY,  # p_nom is always applied to input energy (bus0)
              p_nom_extendable=False,
              p_min_pu=chp_min_profile,
              p_max_pu=chp_max_profile,
              marginal_cost=25.0,
              committable=True,
              min_down_time=2,
              min_up_time=2
              )

        # TODO DIESEL DIESEL DIESEL DIESEL DIESEL DIESEL DIESEL DIESEL DIESEL DIESEL DIESEL

        n.add("Bus", "Diesel_Bus", carrier="diesel")

        n.add("Carrier", "diesel", co2_emissions=0.24)

        n.add(
            "Generator", "Diesel_Commodity_Supply",
            bus="Diesel_Bus",
            p_nom_extendable=True,
            marginal_cost=0.0
        )

        n.add(
            "Link", "Diesel_Generator",
            bus0="Diesel_Bus",
            bus1="Electricity_Bus",
            p_nom=0.05 / config.ELECTRICAL_EFFICIENCY,
            p_nom_extendable=False,
            efficiency=config.ELECTRICAL_EFFICIENCY,
            marginal_cost=2000.0,
            committable=True,
            p_min_pu=0.5,
            p_max_pu=1.0,
        )

        # TODO RUN SIMULATION RUN SIMULATION RUN SIMULATION RUN SIMULATION RUN SIMULATION RUN SIMULATION

        status, condition = n.optimize(
            solver_name='highs',
            include_objective_constant=False,
            solver_options={
                "threads": 8,
                "presolve": "choose",
                "mip_rel_gap": 0.1,
                "mip_feasibility_tolerance": 1e-6,
                "parallel": "on",
            }
        )

        print(f"Simulation Status: {status}")
        print(f"Solver Termination Condition: {condition}")

        # TODO REPORT REPORT REPORT REPORT REPORT REPORT REPORT REPORT REPORT REPORT REPORT REPORT REPORT

        import os
        import pandas as pd
        from openpyxl.utils import get_column_letter

        excel_filename = (
            f"2_CHP_Load_{round(hourly_demand.values.sum(), ndigits=2)}_{config.SIMULATION_YEAR}_digester{config.DIGESTER_CONSTANT_OUTPUT_MW}_bess_{config.BESS_CAPACITY_MWH}_{config.BESS_POWER_MWH}_panels_{config.NUMBER_OF_PANELS}.xlsx"
        )

        os.makedirs("generation_profiles", exist_ok=True)
        print(
            f"Compiling convention-adjusted annual report into: {excel_filename}..."
        )

        actual_pv_kw = n.generators_t.p.loc[:, "PV_System"] * 1000
        theoretical_pv_kw = (
                n.generators_t.p_max_pu.loc[:, "PV_System"]
                * n.generators.at["PV_System", "p_nom"]
                * 1000
        )
        curtailment_profile_kw = theoretical_pv_kw - actual_pv_kw

        electrical_surplus_dump_kw = n.links_t.p0.loc[:, "Electrical_Emergency_Dump"] * 1000

        raw_soc_series = n.stores_t.e.loc[:, "BESS_reservoir"]
        physical_soc_kwh = raw_soc_series * 1000
        physical_soc_pct = (raw_soc_series / config.BESS_CAPACITY_MWH) * 100.0

        bess_charging_kw = n.links_t.p0.loc[:, "BESS_charger"] * 1000
        bess_discharging_kw = -1 * n.links_t.p1.loc[:, "BESS_discharger"] * 1000
        bess_raw_power_kw = (bess_charging_kw * -1) + bess_discharging_kw

        biogas_produced_kw = n.generators_t.p.loc[:, "Digester_Biogas_Output"] * 1000
        biogas_consumed_chp1_kw = n.links_t.p0.loc[:, "CHP_Biogas_Generator"] * 1000
        biogas_consumed_chp2_kw = n.links_t.p0.loc[:, "CHP_Biogas_Generator_2"] * 1000

        biogas_heater_consumed_kw = n.links_t.p0.loc[:, "Biogas_Backup_Heater"] * 1000
        biogas_heater_consumed_m3_h = biogas_heater_consumed_kw / config.KWH_IN_M3_OF_BIOGAS
        heater_thermal_output_kw = n.links_t.p1.loc[:, "Biogas_Backup_Heater"] * 1000

        biogas_tank_store_kw = n.stores_t.e.loc[:, "Biogas_Storage_Tank"].diff().fillna(0) * 1000
        biogas_tank_soc_m3 = (n.stores_t.e.loc[:, "Biogas_Storage_Tank"] * 1000) / config.KWH_IN_M3_OF_BIOGAS
        biogas_vented_kw = n.links_t.p0.loc[:, "Biogas_Emergency_Flare"] * 1000

        biogas_standing_losses_kw = n.stores_t.e.loc[:, "Biogas_Storage_Tank"] * 0.001 * 1000
        biogas_standing_losses_m3_h = biogas_standing_losses_kw / config.KWH_IN_M3_OF_BIOGAS

        system_heat_vented_kw = n.links_t.p0.loc[:, "Heat_Emergency_Vent"] * 1000

        biogas_mass_balance_error_kw = (
                biogas_produced_kw
                - (
                            biogas_consumed_chp1_kw + biogas_consumed_chp2_kw + biogas_heater_consumed_kw + biogas_vented_kw + biogas_standing_losses_kw)
                - biogas_tank_store_kw
        )

        hourly_dispatch_df = pd.DataFrame(
            {
                "Electrical_Demand_kW": n.loads_t.p.loc[:, "Electrical_Load"].values * 1000,
                "Actual_PV_Generation_kW": -1 * actual_pv_kw.values,
                "Raw_PV_Prediction_kW": -1 * theoretical_pv_kw.values,
                "Solar_Curtailment_kW": curtailment_profile_kw.values,
                "Electrical_Surplus_Dumped_kW": electrical_surplus_dump_kw.values,
                "CHP_Electrical_Output_kW": n.links_t.p1.loc[:, "CHP_Biogas_Generator"].values * 1000,
                "Biogas_CHP_Input_kW": biogas_consumed_chp1_kw.values,
                "Biogas_CHP_Input_m3_h": (biogas_consumed_chp1_kw / config.KWH_IN_M3_OF_BIOGAS).values,
                "CHP_2_Electrical_Output_kW": n.links_t.p1.loc[:, "CHP_Biogas_Generator_2"].values * 1000,
                "Biogas_CHP_2_Input_kW": biogas_consumed_chp2_kw.values,
                "Biogas_CHP_2_Input_m3_h": (biogas_consumed_chp2_kw / config.KWH_IN_M3_OF_BIOGAS).values,
                "Digester_Thermal_Load_Required_kW": n.loads_t.p.loc[:, "Digester_Thermal_Load"].values * 1000,
                "Biogas_Heater_Input_kW": biogas_heater_consumed_kw.values,
                "Biogas_Heater_Input_m3_h": biogas_heater_consumed_m3_h.values,
                "Heater_Thermal_Output_kW": heater_thermal_output_kw.values,
                "System_Thermal_Energy_Vented_kW": system_heat_vented_kw.values,
                "Diesel_Electrical_Output_kW": (n.links_t.p1.loc[:, "Diesel_Generator"].values * 1000),
                "Biogas_Digester_Production_kW": -1 * biogas_produced_kw.values,
                "Biogas_Digester_Production_m3_h": ((-1 * biogas_produced_kw) / config.KWH_IN_M3_OF_BIOGAS).values,
                "Biogas_Storage_Level_m3": biogas_tank_soc_m3.values,
                "Biogas_Storage_Net_Flow_kW": biogas_tank_store_kw.values,
                "Biogas_Emergency_Vented_kW": biogas_vented_kw.values,
                "Biogas_Emergency_Vented_m3_h": (biogas_vented_kw / config.KWH_IN_M3_OF_BIOGAS).values,
                "Biogas_Tank_Standing_Loss_kW": biogas_standing_losses_kw.values,
                "Biogas_Tank_Standing_Loss_m3_h": biogas_standing_losses_m3_h.values,
                "Biogas_Mass_Balance_Error_kW": biogas_mass_balance_error_kw.values,
                "BESS_Power_Flow_kW": bess_raw_power_kw.values,
                "BESS_State_of_Charge_kWh": physical_soc_kwh.values,
                "BESS_State_of_Charge_Pct": physical_soc_pct.values,
            },
            index=n.snapshots,
        ).round(2)

        simplified_hourly_dispatch_df = pd.DataFrame(
            {
                "Odbiory Elektryczne": n.loads_t.p.loc[:, "Electrical_Load"].values * 1000,
                "PV Użyte kW": -1 * actual_pv_kw.values,
                "PV Maksymalna Predykcja kW": -1 * theoretical_pv_kw.values,
                "PV Curtailment kW": curtailment_profile_kw.values,
                "CHP Produkcja kW": n.links_t.p1.loc[:, "CHP_Biogas_Generator"].values * 1000,
                "CHP Godzinne zużycie biogazu m3": (biogas_consumed_chp1_kw / config.KWH_IN_M3_OF_BIOGAS).values,
                "CHP 2 Produkcja kW": n.links_t.p1.loc[:, "CHP_Biogas_Generator_2"].values * 1000,
                "CHP 2 Godzinne zużycie biogazu": (biogas_consumed_chp2_kw / config.KWH_IN_M3_OF_BIOGAS).values,
                "Kocioł Produkcja kW th": heater_thermal_output_kw.values,
                "Nadmiar Energii Termalnej kW": system_heat_vented_kw.values,
                "Diesel Produkcja kW": (n.links_t.p1.loc[:, "Diesel_Generator"].values * 1000),
                "Poziom Zbiornika Biogazu m3": biogas_tank_soc_m3.values,
                "BESS Przepływ kW (-ładowanie, +rozładowywanie)": bess_raw_power_kw.values,
                "BESS SOC kWh": physical_soc_kwh.values,
                "BESS SOC %": physical_soc_pct.values,
            },
            index=n.snapshots,
        ).round(2)

        total_mwh_to_bess = bess_charging_kw.sum() / 1000
        total_mwh_from_bess = -1 * (bess_discharging_kw.sum() / 1000)
        bess_losses_mwh = total_mwh_to_bess + total_mwh_from_bess

        demand_mwh = hourly_dispatch_df["Electrical_Demand_kW"].sum() / 1000
        pv_mwh = hourly_dispatch_df["Actual_PV_Generation_kW"].sum() / 1000
        chp_mwh = hourly_dispatch_df["CHP_Electrical_Output_kW"].sum() / 1000
        chp2_mwh = hourly_dispatch_df["CHP_2_Electrical_Output_kW"].sum() / 1000
        diesel_mwh = hourly_dispatch_df["Diesel_Electrical_Output_kW"].sum() / 1000

        electrical_dump_total_mwh = hourly_dispatch_df["Electrical_Surplus_Dumped_kW"].sum() / 1000

        thermal_demand_mwh = hourly_dispatch_df["Digester_Thermal_Load_Required_kW"].sum() / 1000
        thermal_vented_mwh = hourly_dispatch_df["System_Thermal_Energy_Vented_kW"].sum() / 1000

        biogas_prod_mwh = hourly_dispatch_df["Biogas_Digester_Production_kW"].sum() / 1000
        biogas_prod_m3 = hourly_dispatch_df["Biogas_Digester_Production_m3_h"].sum()
        biogas_cons_chp1_mwh = hourly_dispatch_df["Biogas_CHP_Input_kW"].sum() / 1000
        biogas_cons_chp1_m3 = hourly_dispatch_df["Biogas_CHP_Input_m3_h"].sum()
        biogas_cons_chp2_mwh = hourly_dispatch_df["Biogas_CHP_2_Input_kW"].sum() / 1000
        biogas_cons_chp2_m3 = hourly_dispatch_df["Biogas_CHP_2_Input_m3_h"].sum()

        biogas_heater_mwh = hourly_dispatch_df["Biogas_Heater_Input_kW"].sum() / 1000
        biogas_heater_m3 = hourly_dispatch_df["Biogas_Heater_Input_m3_h"].sum()
        heater_heat_output_mwh = hourly_dispatch_df["Heater_Thermal_Output_kW"].sum() / 1000

        biogas_flare_mwh = hourly_dispatch_df["Biogas_Emergency_Vented_kW"].sum() / 1000
        biogas_flare_m3 = hourly_dispatch_df["Biogas_Emergency_Vented_m3_h"].sum()

        biogas_standing_losses_total_mwh = biogas_standing_losses_kw.sum() / 1000
        biogas_standing_losses_total_m3 = biogas_standing_losses_m3_h.sum()

        boiler_useful_heat_mwh = n.links_t.p1["Biogas_Backup_Heater"].sum()
        chp1_useful_heat_mwh = n.links_t.p2["CHP_Biogas_Generator"].sum()

        chp2_useful_heat_mwh = n.links_t.p2["CHP_Biogas_Generator_2"].sum()

        total_useful_thermal_output_mwh = boiler_useful_heat_mwh + chp1_useful_heat_mwh + chp2_useful_heat_mwh

        biogas_series_values = n.stores_t.e.loc[:, "Biogas_Storage_Tank"].values
        bess_series_values = n.stores_t.e.loc[:, "BESS_reservoir"].values
        soc_series_values = physical_soc_kwh.values

        biogas_start_val = float(n.stores.at["Biogas_Storage_Tank", "e_initial"])
        biogas_end_val = float(biogas_series_values[-1])
        annual_storage_delta_mwh = biogas_end_val - biogas_start_val

        total_accounted_biogas_mwh = (
                abs(biogas_cons_chp1_mwh)
                + abs(biogas_cons_chp2_mwh)
                + abs(biogas_heater_mwh)
                + abs(biogas_flare_mwh)
                + annual_storage_delta_mwh
                + abs(biogas_standing_losses_total_mwh)
        )
        absolute_biogas_error_mwh = abs(abs(biogas_prod_mwh) - total_accounted_biogas_mwh)
        biogas_balance_status = "PASS" if absolute_biogas_error_mwh < 0.10 else "FAIL"

        total_elec_generation = abs(pv_mwh) + abs(chp_mwh) + abs(chp2_mwh) + abs(diesel_mwh) + abs(total_mwh_from_bess)
        total_elec_consumption = abs(demand_mwh) + abs(total_mwh_to_bess) + electrical_dump_total_mwh
        absolute_elec_error_mwh = abs(total_elec_generation - total_elec_consumption)
        elec_balance_status = "PASS" if absolute_elec_error_mwh < 0.05 else "FAIL"

        total_system_inputs_mwh = abs(pv_mwh) + abs(biogas_prod_mwh) + abs(diesel_mwh)

        bess_start_val = float(bess_series_values[0])
        bess_end_val = float(bess_series_values[-1])
        total_bess_reservoir_delta_mwh = bess_end_val - bess_start_val

        net_storage_accumulations_mwh = total_bess_reservoir_delta_mwh + annual_storage_delta_mwh

        total_system_outputs_mwh = (
                abs(demand_mwh)
                + abs(thermal_demand_mwh)
                + abs(biogas_flare_mwh)
                + abs(thermal_vented_mwh)
                + abs(biogas_standing_losses_total_mwh)
                + electrical_dump_total_mwh
                + net_storage_accumulations_mwh
        )

        chps_conversion_losses_mwh = abs(biogas_cons_chp1_mwh) + abs(biogas_cons_chp2_mwh) - (
                    abs(chp_mwh) + abs(chp2_mwh) + (
                        abs(biogas_cons_chp1_mwh + biogas_cons_chp2_mwh) * config.CHP_THERMAL_EFFICIENCY))
        boiler_conversion_losses_mwh = abs(biogas_heater_mwh) - abs(heater_heat_output_mwh)

        bess_conversion_losses_mwh = abs(bess_losses_mwh)

        conversion_losses_mwh = (
                chps_conversion_losses_mwh
                + boiler_conversion_losses_mwh
                + bess_conversion_losses_mwh
        )

        absolute_total_energy_error_mwh = abs(
            total_system_inputs_mwh - (total_system_outputs_mwh + conversion_losses_mwh))

        total_energy_balance_status = "PASS" if absolute_total_energy_error_mwh < 0.50 else "FAIL"

        summary_data = [
            ("Total Electrical Demand (MWh)", demand_mwh),
            ("Total Digester Thermal Demand Required (MWh)", thermal_demand_mwh),
            ("Total System Thermal Energy Vented (MWh)", thermal_vented_mwh),
            ("Total System Thermal Energy Produced (MWh)", total_useful_thermal_output_mwh),
            ("Total System Forced Excess Electrical Energy Dumped to Atmosphere (MWh)", electrical_dump_total_mwh),
            ("PV Raw Prediction (MWh)", float(theoretical_pv_kw.values.sum() / 1000)),
            ("PV Utilized Generation (MWh)", pv_mwh),
            ("PV Curtailment (MWh)", float(curtailment_profile_kw.values.sum() / 1000)),
            ("CHP Generation (MWh)", chp_mwh),
            ("CHP 2 Generation (MWh)", chp2_mwh),
            ("Diesel Generation (MWh)", diesel_mwh),
            ("Total Biogas Produced by Digester (MWh_thermal)", biogas_prod_mwh),
            ("Total Biogas Produced by Digester (m³)", biogas_prod_m3),
            ("Total Biogas Consumed by CHP Engine (MWh_thermal)", biogas_cons_chp1_mwh),
            ("Total Biogas Consumed by CHP Engine (m³)", biogas_cons_chp1_m3),
            ("Total Biogas Consumed by CHP_2 Engine (MWh_thermal)", biogas_cons_chp2_mwh),
            ("Total Biogas Consumed by CHP_2 Engine (m³)", biogas_cons_chp2_m3),
            ("Total Biogas Consumed by Backup Heater (MWh_thermal)", biogas_heater_mwh),
            ("Total Biogas Consumed by Backup Heater (m³)", biogas_heater_m3),
            ("Total Thermal Heat Delivered by Backup Heater (MWh_thermal)", heater_heat_output_mwh),
            ("Total Biogas Lost via Tank Standing Losses (MWh_thermal)", biogas_standing_losses_total_mwh),
            ("Total Biogas Lost via Tank Standing Losses (m³)", biogas_standing_losses_total_m3),
            ("Total Biogas Lost / Vented in Emergency Flare (MWh_thermal)", biogas_flare_mwh),
            ("Total Biogas Lost / Vented in Emergency Flare (m³)", biogas_flare_m3),
            ("Peak Biogas Storage Tank Volume Required (m³)", hourly_dispatch_df["Biogas_Storage_Level_m3"].max()),
            ("Total Energy Sent to Battery (MWh)", total_mwh_to_bess),
            ("Total Energy Drawn from BESS (MWh)", total_mwh_from_bess),
            ("Net Energy Lost inside BESS (MWh)", bess_losses_mwh),
            ("True Calendar Start SoC Energy (MWh)", float(soc_series_values[0]) / 1000),
            ("True Calendar End SoC Energy (MWh)", float(soc_series_values[-1]) / 1000),
            ("Biogas Sub-Grid Mass Balance Closure Error (MWh)", absolute_biogas_error_mwh),
            ("Biogas Grid Data Integrity Check Status", biogas_balance_status),
            ("Electrical Sub-Grid Mass Balance Closure Error (MWh)", absolute_elec_error_mwh),
            ("Electrical Grid Data Integrity Check Status", elec_balance_status),
            ("Total Combined Network Energy Balance Closure Error (MWh)", absolute_total_energy_error_mwh),
            ("Comprehensive System Energy Integrity Check Status", total_energy_balance_status)]
        summary_df = pd.DataFrame(summary_data, columns=["Performance Metric", "Annual Value"]).round(4)

        simplified_summary_data = [
            ("Roczne odbiory elektryczne (MWh)", demand_mwh),
            ("Roczny odbiór termalny (fermentator) (MWh)", thermal_demand_mwh),
            ("Roczna nadprodukcja energii termalnej - zużyta/zrzucona poprzez kocioł (MWh)", thermal_vented_mwh),
            ("Roczna produkcja energii termalnej (MWh)", total_useful_thermal_output_mwh),
            ("PV Roczna Predykcja (MWh)", float(theoretical_pv_kw.values.sum() / 1000)),
            ("PV Roczne Zużycie (MWh)", pv_mwh),
            ("PV Roczny Curtailment (MWh)", float(curtailment_profile_kw.values.sum() / 1000)),
            ("CHP Produkcja roczna (MWh)", chp_mwh),
            ("CHP 2 Produkcja roczna (MWh)", chp2_mwh),
            ("Diesel Produkcja roczna (MWh)", diesel_mwh),
            ("Roczna produkcja biogazu (m³)", biogas_prod_m3),
            ("CHP Roczne zużycie biogazu (m³)", biogas_cons_chp1_m3),
            ("CHP 2 Roczne zużycie biogazu (m³)", biogas_cons_chp2_m3),
            ("Kocioł Roczne zużycie biogazu (m³)", biogas_heater_m3),
            ("Biogaz spalony w pochodni (m³)", biogas_flare_m3),
            ("Energia wysłana do BESS (MWh)", total_mwh_to_bess),
            ("Energia pobrana z BESS (MWh)", total_mwh_from_bess),
            ("Energia stracona w BESS (efektywność) (MWh)", bess_losses_mwh)]
        simplified_summary_df = pd.DataFrame(simplified_summary_data, columns=["Metryka", "Roczna Wartość"]).round(4)

        with pd.ExcelWriter('generation_profiles/' + excel_filename, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Annual_Summary", index=False)
            hourly_dispatch_df.to_excel(writer, sheet_name="Hourly_Dispatch", index=True)
            ws_hourly = writer.sheets["Hourly_Dispatch"]
            first_data_row = 2
            last_data_row = len(hourly_dispatch_df) + 1
            summary_row = last_data_row + 1
            ws_hourly.cell(row=summary_row, column=1, value="TOTAL SUMMARY (SUM/AVG)")
            for col_idx in range(2, ws_hourly.max_column + 1):
                col_letter = get_column_letter(col_idx)
                header_name = ws_hourly.cell(row=1, column=col_idx).value
                if "State_of_Charge" in header_name or "Level_m3" in header_name:
                    formula = f"=AVERAGE({col_letter}{first_data_row}:{col_letter}{last_data_row})"
                else:
                    formula = f"=SUM({col_letter}{first_data_row}:{col_letter}{last_data_row})"
                ws_hourly.cell(row=summary_row, column=col_idx, value=formula)

        with pd.ExcelWriter('generation_profiles/simplified_' + excel_filename, engine="openpyxl") as writer:
            simplified_summary_df.to_excel(writer, sheet_name="Roczny raport", index=False)
            simplified_hourly_dispatch_df.to_excel(writer, sheet_name="Bilans godzinowy", index=True)
            ws_hourly = writer.sheets["Bilans godzinowy"]
            first_data_row = 2
            last_data_row = len(simplified_hourly_dispatch_df) + 1
            summary_row = last_data_row + 1
            ws_hourly.cell(row=summary_row, column=1, value="Podsumowanie (Suma/Średnia)")
            for col_idx in range(2, ws_hourly.max_column + 1):
                col_letter = get_column_letter(col_idx)
                header_name = ws_hourly.cell(row=1, column=col_idx).value
                if "SOC" in header_name or "Poziom Zbiornika Biogazu m3" in header_name:
                    formula = f"=AVERAGE({col_letter}{first_data_row}:{col_letter}{last_data_row})"
                else:
                    formula = f"=SUM({col_letter}{first_data_row}:{col_letter}{last_data_row})"
                ws_hourly.cell(row=summary_row, column=col_idx, value=formula)

        print(f"Annual report generated successfully with full Bus-Link-Bus-Store symmetry alignment!")

