"""
WattCredit Unified Digital Twin — Appliance + Rev B0 Meter + NGO Underwriting
=============================================================================

Combines the three Python prototypes into ONE dashboard:
  1) Appliance electrical behavior (tailoring/overlock and wet-grinder)
  2) Rev B0 smart-plug metrology, protection, supercapacitor and BLE ledger
  3) NGO officer card-tap state machine, CSV import/sample generation and credit scoring



Install:
    pip install numpy matplotlib

Run:
    python wattcredit_unified_twin.py

"""

import csv
import hashlib
import math
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import deque
from datetime import datetime, timedelta

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
# Bundled Matplotlib font keeps plot rendering consistent on Windows, Linux and WSL.
matplotlib.rcParams["font.family"] = "DejaVu Serif"
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# =============================================================================
# REV B0 MODEL CONSTANTS
# =============================================================================
F_LINE_HZ = 50.0
ADC_SAMPLE_RATE = 4000
SAMPLES_PER_CYCLE = int(ADC_SAMPLE_RATE / F_LINE_HZ)  # 80 samples at 4 kSPS
SHUNT_OHM = 0.005
DIV_TOP_OHM = 4 * 330_000.0
DIV_BOTTOM_OHM = 499.0
AMC1301_GAIN = 8.2
ADC_INPUT_LIMIT_V = 1.2
RELAY_TRIP_A = 10.0
OVERCURRENT_DELAY_S = 0.35
GRID_UV_V = 175.0
GRID_OV_V = 265.0
SUPERCAP_F = 0.1
SUPERCAP_NOM_V = 5.0
PWR_FAIL_V = 4.55
LDO_MIN_INPUT_V = 3.60
RECORD_PERIOD_S = 1.0

# Retro navy/yellow style retained from the earlier twins.
NAVY_BG = "#08142C"
NAVY_PANEL = "#0D1E40"
NAVY_WELL = "#050D1E"
YELLOW = "#FFD60A"
AMBER = "#FFB703"
CREAM = "#FFFBEB"
MUTED = "#D6C778"
CYAN = "#72EFDD"
CORAL = "#FF6B6B"
GREEN = "#7AE582"
GRID = "#1B3157"

FONT_TITLE = ("Georgia", 15, "bold")
FONT_SECTION = ("Georgia", 10, "bold")
FONT_BODY = ("Times New Roman", 10)
FONT_MONO = ("Courier New", 9)
FONT_MONO_BOLD = ("Courier New", 10, "bold")


# =============================================================================
# APPLIANCE PROFILES
# =============================================================================
APPLIANCE_PROFILES = {
    "Tailoring & Overlock Machine": {
        "rated_w": 650.0,
        "pf": 0.86,
        "idle_w": 28.0,
        "start_mult": 2.8,
        "start_tau": 0.14,
        "active_days": 26,
        "daily_hours": 6.5,
        "description": "Motor-driven sewing/overlock operation with intermittent needle and fabric-load cycles."
    },
    "Commercial Wet-Grinder": {
        "rated_w": 1200.0,
        "pf": 0.82,
        "idle_w": 35.0,
        "start_mult": 3.2,
        "start_tau": 0.18,
        "active_days": 28,
        "daily_hours": 5.0,
        "description": "Motor-driven grinding with changing mechanical load as material is added or removed."
    },
    "Solar-Assisted Mini Bakery & Oven": {
        "rated_w": 1850.0,
        "pf": 0.96,
        "idle_w": 35.0,
        "start_mult": 1.15,
        "start_tau": 0.25,
        "active_days": 24,
        "daily_hours": 4.5,
        "description": "Oven heating element with intermittent dough-mixer load; predominantly resistive with a small motor component."
    },
}


def clamp(value, low, high):
    return max(low, min(high, value))


# =============================================================================
# APPLIANCE BEHAVIORAL MODEL
# =============================================================================
class ApplianceModel:
    """Approximate motor/load profile for a tailoring machine or wet-grinder."""

    def __init__(self):
        self.profile_name = "Tailoring & Overlock Machine"
        self.running = False
        self.mechanical_load_pct = 65.0
        self.elapsed_s = 0.0
        self.start_elapsed_s = 999.0
        self.speed_pu = 0.0
        self.state = "STOPPED"
        self.current_a = 0.0
        self.pf = 0.0
        self.active_power_w = 0.0
        self.torque_pu = 0.0

    @property
    def profile(self):
        return APPLIANCE_PROFILES[self.profile_name]

    def select_profile(self, name):
        self.profile_name = name
        self.stop()

    def start(self):
        if not self.running:
            self.running = True
            self.elapsed_s = 0.0
            self.start_elapsed_s = 0.0
            self.speed_pu = 0.0
            self.state = "STARTING / ACCELERATING"

    def stop(self):
        self.running = False
        self.speed_pu = 0.0
        self.current_a = 0.0
        self.pf = 0.0
        self.active_power_w = 0.0
        self.torque_pu = 0.0
        self.state = "STOPPED"

    def step(self, dt, voltage_rms, mechanical_load_pct):
        self.mechanical_load_pct = clamp(mechanical_load_pct, 10.0, 125.0)
        if not self.running or voltage_rms <= 1.0:
            self.stop()
            return

        p = self.profile
        self.elapsed_s += dt
        self.start_elapsed_s += dt

        accel_time = 0.35 if "Tailoring" in self.profile_name else 0.55
        self.speed_pu = min(1.0, self.speed_pu + dt / accel_time)

        load_pu = self.mechanical_load_pct / 100.0

        if "Tailoring" in self.profile_name:
            # Repeated needle/fabric engagement creates a mild cyclic load.
            phase = (self.elapsed_s % 2.4) / 2.4
            cycle = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))
            pf_base = 0.84 + 0.035 * cycle
            self.state = (
                "SEWING / NEEDLE LOAD" if phase < 0.73
                else "MOTOR IDLE / FABRIC POSITION"
            )
        elif "Grinder" in self.profile_name:
            # Grinding material changes the torque/current demand over time.
            phase = (self.elapsed_s % 5.0) / 5.0
            cycle = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))
            pf_base = 0.79 + 0.06 * cycle
            self.state = (
                "GRINDING / MATERIAL LOAD" if phase < 0.80
                else "LOW MECHANICAL LOAD"
            )
        else:
            # Bakery oven is mainly a resistive heater with a smaller mixer motor.
            phase = (self.elapsed_s % 8.0) / 8.0
            cycle = 0.90 + 0.10 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))
            pf_base = 0.94 + 0.02 * cycle
            self.state = (
                "OVEN HEATING / MIXER ACTIVE" if phase < 0.75
                else "THERMOSTAT HOLD / LOW LOAD"
            )

        steady_power = p["idle_w"] + p["rated_w"] * load_pu * cycle
        steady_power *= clamp(voltage_rms / 230.0, 0.70, 1.08) ** 0.25
        steady_power *= 0.88 + 0.12 * self.speed_pu

        # Starting inrush: current is temporarily elevated; effective PF falls.
        start_extra = (p["start_mult"] - 1.0) * math.exp(
            -self.start_elapsed_s / p["start_tau"]
        )
        steady_current = steady_power / max(1.0, voltage_rms * pf_base)
        self.current_a = steady_current * (1.0 + start_extra)
        self.pf = clamp(
            steady_power / max(1.0, voltage_rms * self.current_a),
            0.30, 0.98
        )
        self.active_power_w = voltage_rms * self.current_a * self.pf
        self.torque_pu = clamp(load_pu * cycle, 0.0, 1.25)

        if self.start_elapsed_s < 0.75:
            self.state = "STARTING / ACCELERATING"


# =============================================================================
# CSV / CREDIT ENGINE
# =============================================================================
def generate_sample_record_csv(filepath):
    """Generate a deterministic 30-day hourly sample log, matching the legacy CSV schema."""
    rng = np.random.default_rng(42)
    rows = []
    start_date = datetime(2026, 10, 1, 8, 0, 0)
    for day in range(30):
        date = start_date + timedelta(days=day)
        working_day = date.weekday() != 6
        for hour in range(8, 20):
            ts = date.replace(hour=hour)
            voltage = float(np.clip(rng.normal(231.0, 3.2), 218.0, 245.0))
            if working_day and 9 <= hour <= 16:
                power = float(rng.normal(665.0, 48.0))
                pf = float(np.clip(rng.normal(0.87, 0.02), 0.78, 0.96))
            else:
                power = float(max(5.0, rng.normal(28.0, 5.0)))
                pf = 0.65
            current = power / max(1.0, voltage * pf)
            rows.append([
                ts.isoformat(timespec="seconds"),
                round(voltage, 2), round(current, 3), round(pf, 3), 0
            ])
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "voltage_v", "current_a", "power_factor", "tamper"])
        writer.writerows(rows)
    return filepath


def load_shift_csv(filepath):
    """Load legacy WattCredit shift CSV; each row is treated as one observation interval."""
    records = []
    with open(filepath, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"voltage_v", "current_a", "power_factor"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                "CSV must contain timestamp, voltage_v, current_a, power_factor and optionally tamper."
            )
        for row in reader:
            v = float(row.get("voltage_v") or 0.0)
            i = float(row.get("current_a") or 0.0)
            pf = clamp(float(row.get("power_factor") or 0.0), 0.0, 1.0)
            tamper = int(float(row.get("tamper") or 0))
            ts = row.get("timestamp", "")
            records.append({
                "timestamp": ts, "v": v, "i": i, "pf": pf,
                "p": v * i * pf, "tamper": tamper
            })
    if not records:
        raise ValueError("The selected CSV contains no data rows.")
    return records


class WattCreditUnifiedEngine:
    """One shared source of truth for appliance, meter, protection, ledger and underwriting."""

    def __init__(self):
        self.dt = 1.0 / 20.0
        self.sim_time = 0.0
        self.fps = 20

        # Grid and appliance
        self.grid_voltage_set = 230.0
        self.grid_connected = True
        self.appliance = ApplianceModel()
        self.mechanical_load_pct = 65.0
        self.forced_overload_until = 0.0
        self.forced_overload_a = 12.5

        # Protection / backup power
        self.relay_closed = True
        self.fault_latched = False
        self.fault_reason = "NONE"
        self.tamper_active = False
        self.cap_voltage = SUPERCAP_NOM_V
        self.pwr_fail_active = False
        self.last_gasp_committed = False
        self.ldo_dropout_logged = False
        self.overcurrent_elapsed = 0.0

        # Measured electrical values
        self.v_rms = 230.0
        self.i_rms = 0.0
        self.pf = 0.0
        self.p_active_w = 0.0
        self.s_apparent_va = 0.0
        self.energy_wh = 0.0
        self.session_wh = 0.0
        self.v_adc_peak = 0.0
        self.i_adc_peak = 0.0
        self.v_adc_clip = False
        self.i_adc_clip = False
        self.sample_v = np.zeros(SAMPLES_PER_CYCLE)
        self.sample_i = np.zeros(SAMPLES_PER_CYCLE)
        self.wave_t_ms = np.arange(SAMPLES_PER_CYCLE) / ADC_SAMPLE_RATE * 1000.0

        # Ledger / BLE
        self.sequence = 0
        self.previous_hash = "0" * 64
        self.ledger_records = deque(maxlen=2000)
        self.flash_queue = deque()
        self.ble_connected = True
        self.ble_packets_sent = 0
        self.last_record_time = 0.0
        self.ledger_event_count = 0

        # NGO card-tap flow
        self.tap_stage = "IDLE"
        self.tap_elapsed = 0.0
        self.officer_id = "NGO-TN-SHG-0418"
        self.synced_this_tap = 0
        self.credit_score = 0
        self.loan_limit_inr = 0
        self.rebate_pct = 0.0
        self.credit_tier = "NOT CALCULATED"
        self.score_parts = {}
        self.underwriting_ready = False

        # Credit defaults / calibration
        prof = self.appliance.profile
        self.active_days_30d = prof["active_days"]
        self.daily_prod_hours = prof["daily_hours"]
        self.productive_threshold_w = 300.0
        self.credit_rate_inr_kwh = 185.0
        self.productive_power_w = prof["rated_w"] * 0.65
        self.tamper_events_30d = 0
        self.avg_pf_30d = prof["pf"]

        # CSV import and optional replay
        self.csv_records = []
        self.csv_name = "Synthetic profile / no CSV loaded"
        self.csv_replay_active = False
        self.csv_replay_index = 0
        self.csv_replay_accum = 0.0
        self.csv_replay_interval = 0.5
        self.csv_underwriting_stats = None

        # Time series, event log and text cache
        self.history_t = deque(maxlen=240)
        self.history_p = deque(maxlen=240)
        self.history_i = deque(maxlen=240)
        self.history_cap = deque(maxlen=240)
        self.event_log = deque(maxlen=160)
        self.last_explanation = ""
        self.last_ui_log_count = 0
        self._add_event("System initialized. Grid nominal 230 V RMS / 50 Hz.")

    def _add_event(self, text):
        self.event_log.appendleft(f"{self.sim_time:8.2f}s  {text}")

    def select_appliance(self, name):
        self.appliance.select_profile(name)
        prof = self.appliance.profile
        self.csv_replay_active = False
        if self.csv_records:
            # Keep imported 30-day underwriting evidence when changing the live appliance view.
            self._recalculate_csv_stats()
            self.underwriting_ready = True
            self.compute_credit_underwriting()
        else:
            self.active_days_30d = prof["active_days"]
            self.daily_prod_hours = prof["daily_hours"]
            self.productive_power_w = prof["rated_w"] * self.mechanical_load_pct / 100.0
            self.avg_pf_30d = prof["pf"]
            self.underwriting_ready = False
        self._add_event(f"Appliance profile selected: {name}.")

    def start_appliance(self):
        if self.fault_latched:
            return False
        if not self.grid_connected or not self.relay_closed:
            return False
        self.appliance.start()
        self._add_event("Appliance switched ON.")
        return True

    def stop_appliance(self):
        self.appliance.stop()
        self._add_event("Appliance switched OFF.")

    def inject_overload(self):
        if not self.fault_latched and self.grid_connected and self.relay_closed:
            self.forced_overload_until = self.sim_time + 0.65
            self._add_event("12.5 A RMS overload scenario injected (timed protection test).")

    def set_grid(self, connected):
        self.grid_connected = bool(connected)
        self._add_event("Grid restored." if connected else "GRID BLACKOUT injected.")

    def set_ble(self, connected):
        was_connected = self.ble_connected
        self.ble_connected = bool(connected)
        self._add_event(
            "BLE connected." if connected else "BLE disconnected; records will queue in W25Q64 model."
        )
        if connected and not was_connected:
            self._flush_flash_queue()
            if self.tap_stage == "SYNCING":
                self._finish_card_sync()

    def trigger_tamper(self):
        if not self.tamper_active:
            self.tamper_active = True
            self.tamper_events_30d += 1
            self._add_event("SW1 enclosure tamper input asserted.")

    def reset_faults(self):
        self.fault_latched = False
        self.fault_reason = "NONE"
        self.tamper_active = False
        self.overcurrent_elapsed = 0.0
        self.forced_overload_until = 0.0
        self.appliance.stop()
        if self.grid_connected and self.cap_voltage > PWR_FAIL_V:
            self.relay_closed = True
        self._add_event("Fault latch reset; appliance remains stopped.")

    def import_csv(self, filepath):
        self.csv_records = load_shift_csv(filepath)
        self.csv_name = os.path.basename(filepath)
        self.csv_replay_index = 0
        self.csv_replay_accum = 0.0
        prod = [r for r in self.csv_records if r["p"] >= self.productive_threshold_w]
        if prod:
            days = {
                r["timestamp"][:10] for r in prod
                if len(r["timestamp"]) >= 10
            }
            self.active_days_30d = clamp(len(days) if days else 1, 1, 30)
            self.daily_prod_hours = min(
                14.0, len(prod) / max(1, self.active_days_30d)
            )
            self.productive_power_w = float(np.mean([r["p"] for r in prod]))
            self.avg_pf_30d = float(np.mean([r["pf"] for r in prod]))
        else:
            self.active_days_30d = 1
            self.daily_prod_hours = 0.0
            self.productive_power_w = float(np.mean([r["p"] for r in self.csv_records]))
            self.avg_pf_30d = float(np.mean([r["pf"] for r in self.csv_records]))
        self.tamper_events_30d = sum(r["tamper"] for r in self.csv_records)
        self.csv_underwriting_stats = {
            "rows": len(self.csv_records),
            "productive_rows": len(prod),
            "days": self.active_days_30d,
            "hours_per_day": self.daily_prod_hours,
            "productive_power": self.productive_power_w,
            "avg_pf": self.avg_pf_30d,
            "tamper_events": self.tamper_events_30d,
        }
        self.underwriting_ready = True
        self.compute_credit_underwriting()
        self.tap_stage = "IDLE"
        self._add_event(
            f"Imported {len(self.csv_records)} shift records from {self.csv_name}; "
            f"{len(prod)} above productive cutoff."
        )

    def toggle_csv_replay(self):
        if not self.csv_records:
            return False
        self.csv_replay_active = not self.csv_replay_active
        self.csv_replay_index = 0
        self.csv_replay_accum = 0.0
        self.appliance.stop()
        self._add_event(
            "CSV telemetry replay started." if self.csv_replay_active
            else "CSV telemetry replay stopped."
        )
        return self.csv_replay_active

    def set_credit_calibration(self, threshold=None, rate=None, days=None, hours=None):
        if threshold is not None:
            self.productive_threshold_w = float(threshold)
            if self.csv_records:
                # Recalculate the imported productive statistics against the new cutoff.
                self._recalculate_csv_stats()
        if rate is not None:
            self.credit_rate_inr_kwh = float(rate)
        if days is not None:
            self.active_days_30d = int(round(days))
        if hours is not None:
            self.daily_prod_hours = float(hours)
        if self.underwriting_ready:
            self.compute_credit_underwriting()

    def _recalculate_csv_stats(self):
        prod = [r for r in self.csv_records if r["p"] >= self.productive_threshold_w]
        if prod:
            days = {r["timestamp"][:10] for r in prod if len(r["timestamp"]) >= 10}
            self.active_days_30d = clamp(len(days) if days else 1, 1, 30)
            self.daily_prod_hours = min(14.0, len(prod) / max(1, self.active_days_30d))
            self.productive_power_w = float(np.mean([r["p"] for r in prod]))
            self.avg_pf_30d = float(np.mean([r["pf"] for r in prod]))
        else:
            self.active_days_30d = 1
            self.daily_prod_hours = 0.0
            self.productive_power_w = 0.0
            self.avg_pf_30d = 0.0
        self.tamper_events_30d = sum(r["tamper"] for r in self.csv_records)

    def start_card_tap(self):
        self.tap_stage = "HANDSHAKE"
        self.tap_elapsed = 0.0
        self.synced_this_tap = 0
        self._add_event(f"Officer credential presented: {self.officer_id}.")

    def _finish_card_sync(self):
        self.synced_this_tap = len(self.flash_queue)
        self._flush_flash_queue()
        self.compute_credit_underwriting()
        self.tap_stage = "VERIFIED"
        self._add_event(
            f"Underwriting verified: score {self.credit_score}/100, "
            f"indicative limit ₹{self.loan_limit_inr:,}."
        )

    def compute_credit_underwriting(self):
        est_30d_kwh = (
            max(0.0, self.productive_power_w) / 1000.0
            * max(0.0, self.daily_prod_hours)
            * max(0, self.active_days_30d)
        )
        score_consistency = min(100.0, self.active_days_30d / 26.0 * 100.0)
        productive_factor = (
            1.0 if self.productive_power_w >= self.productive_threshold_w
            else self.productive_power_w / max(1.0, self.productive_threshold_w)
        )
        score_utilization = min(
            100.0, (self.daily_prod_hours / 6.0 * 100.0) * productive_factor
        )
        score_integrity = max(0.0, 100.0 - self.tamper_events_30d * 45.0)
        score_power = (
            100.0 if 0.75 <= self.avg_pf_30d <= 1.0 and self.i_rms <= RELAY_TRIP_A
            else 65.0
        )
        total = int(round(
            0.35 * score_consistency
            + 0.35 * score_utilization
            + 0.20 * score_integrity
            + 0.10 * score_power
        ))

        if self.tamper_events_30d >= 2 or total < 45:
            loan = 0
            rebate = 0.0
            tier = "HOLD — MANUAL FIELD AUDIT"
        else:
            raw = est_30d_kwh * self.credit_rate_inr_kwh * total / 100.0
            loan = int(min(50000, max(5000, round(raw / 500.0) * 500)))
            rebate = 2.0 if total >= 80 else (1.0 if total >= 65 else 0.0)
            tier = "TIER 1 — SHG FAST TRACK" if total >= 80 else "TIER 2 — STANDARD"

        self.credit_score = total
        self.loan_limit_inr = loan
        self.rebate_pct = rebate
        self.credit_tier = tier
        self.score_parts = {
            "estimated_kwh": est_30d_kwh,
            "consistency": score_consistency,
            "utilization": score_utilization,
            "integrity": score_integrity,
            "power_quality": score_power,
            "tier": tier,
            "productive_power_w": self.productive_power_w,
            "active_days": self.active_days_30d,
            "daily_hours": self.daily_prod_hours,
        }
        self.underwriting_ready = True

    def _flush_flash_queue(self):
        if not self.ble_connected:
            return
        count = len(self.flash_queue)
        if count:
            self.ble_packets_sent += count
            self.flash_queue.clear()
            self._add_event(f"[BLE GATT 0xFF01] Burst-synced {count} queued records.")

    def _commit_ledger_record(self):
        self.sequence += 1
        payload = (
            f"SEQ={self.sequence}|T={self.sim_time:.3f}|V={self.v_rms:.3f}|"
            f"I={self.i_rms:.4f}|PF={self.pf:.4f}|P={self.p_active_w:.3f}|"
            f"WH={self.energy_wh:.6f}|TAMPER={int(self.tamper_active)}|"
            f"FAULT={self.fault_reason}"
        )
        digest = hashlib.sha256((self.previous_hash + payload).encode("utf-8")).hexdigest()
        self.previous_hash = digest
        record = {"sequence": self.sequence, "payload": payload, "hash": digest}
        self.ledger_records.append(record)

        if self.ble_connected and not self.pwr_fail_active:
            self.ble_packets_sent += 1
            self._flush_flash_queue()
            self._add_event(f"[BLE 0xFF01] SEQ {self.sequence} sent | SHA256 {digest[:12]}…")
        else:
            self.flash_queue.append(record)
            self._add_event(f"[W25Q64] SEQ {self.sequence} queued | SHA256 {digest[:12]}…")

    def _measure_from_waveforms(self, voltage_rms, current_rms, pf):
        t = np.arange(SAMPLES_PER_CYCLE) / ADC_SAMPLE_RATE
        v_peak = voltage_rms * math.sqrt(2.0)
        i_peak = current_rms * math.sqrt(2.0)
        phase = math.acos(clamp(pf, -1.0, 1.0)) if current_rms > 0 else 0.0

        self.sample_v = v_peak * np.sin(2.0 * math.pi * F_LINE_HZ * t)
        self.sample_i = i_peak * np.sin(2.0 * math.pi * F_LINE_HZ * t - phase)

        # Digital metrology is computed from the same simultaneous sample arrays.
        measured_v = math.sqrt(float(np.mean(self.sample_v ** 2)))
        measured_i = math.sqrt(float(np.mean(self.sample_i ** 2)))
        measured_p = float(np.mean(self.sample_v * self.sample_i))
        measured_s = measured_v * measured_i
        measured_pf = measured_p / measured_s if measured_s > 1e-9 else 0.0

        # Analog front-end equivalent signal levels (peak).
        divider_ratio = DIV_BOTTOM_OHM / (DIV_TOP_OHM + DIV_BOTTOM_OHM)
        v_adc = self.sample_v * divider_ratio * AMC1301_GAIN
        i_adc = self.sample_i * SHUNT_OHM * AMC1301_GAIN
        self.v_adc_clip = bool(np.max(np.abs(v_adc)) > ADC_INPUT_LIMIT_V)
        self.i_adc_clip = bool(np.max(np.abs(i_adc)) > ADC_INPUT_LIMIT_V)
        self.v_adc_peak = float(np.max(np.abs(v_adc)))
        self.i_adc_peak = float(np.max(np.abs(i_adc)))

        self.v_rms = measured_v
        self.i_rms = measured_i
        self.p_active_w = measured_p
        self.s_apparent_va = measured_s
        self.pf = measured_pf

    def _apply_csv_record(self, rec):
        self.appliance.stop()
        # Voltage channel is modeled on the module's line/input side, so it
        # remains live when K1 opens; the load current then falls to zero.
        self.v_rms = rec["v"] if self.grid_connected else 0.0
        self.i_rms = rec["i"] if self.relay_closed and self.grid_connected and not self.fault_latched else 0.0
        self.pf = rec["pf"] if self.i_rms > 0 else 0.0
        self.p_active_w = self.v_rms * self.i_rms * self.pf
        self.s_apparent_va = self.v_rms * self.i_rms
        # Recreate waveform with the CSV observation.
        t = np.arange(SAMPLES_PER_CYCLE) / ADC_SAMPLE_RATE
        phi = math.acos(clamp(self.pf, -1.0, 1.0)) if self.i_rms else 0.0
        self.sample_v = self.v_rms * math.sqrt(2) * np.sin(2 * math.pi * F_LINE_HZ * t)
        self.sample_i = self.i_rms * math.sqrt(2) * np.sin(2 * math.pi * F_LINE_HZ * t - phi)
        ratio = DIV_BOTTOM_OHM / (DIV_TOP_OHM + DIV_BOTTOM_OHM)
        self.v_adc_peak = float(np.max(np.abs(self.sample_v * ratio * AMC1301_GAIN)))
        self.i_adc_peak = float(np.max(np.abs(self.sample_i * SHUNT_OHM * AMC1301_GAIN)))
        self.v_adc_clip = self.v_adc_peak > ADC_INPUT_LIMIT_V
        self.i_adc_clip = self.i_adc_peak > ADC_INPUT_LIMIT_V
        if rec["tamper"]:
            self.tamper_active = True
            if not self.fault_latched:
                self.fault_latched = True
                self.fault_reason = "CSV TAMPER EVENT"
                self.relay_closed = False

    def step(self):
        dt = self.dt
        self.sim_time += dt

        # 1. Logic rail hold-up and last-gasp behavior.
        if self.grid_connected:
            self.cap_voltage = min(SUPERCAP_NOM_V, self.cap_voltage + 1.8 * dt)
            self.pwr_fail_active = False
            self.last_gasp_committed = False
            self.ldo_dropout_logged = False
            if not self.fault_latched:
                self.relay_closed = True
        else:
            draw_a = 0.25 if self.relay_closed else 0.08
            self.cap_voltage = max(
                0.0, self.cap_voltage - (draw_a / SUPERCAP_F) * dt
            )
            if self.cap_voltage <= PWR_FAIL_V:
                self.pwr_fail_active = True
                self.relay_closed = False
                self.appliance.stop()
                if not self.last_gasp_committed and self.cap_voltage > LDO_MIN_INPUT_V:
                    self.last_gasp_committed = True
                    self._commit_ledger_record()
                    self._add_event("U9 PWR_FAIL: K1 shed; last-gasp record committed.")
            if self.cap_voltage <= LDO_MIN_INPUT_V and not self.ldo_dropout_logged:
                self.ldo_dropout_logged = True
                self._add_event("3.3 V logic rail no longer guaranteed (LDO dropout region).")

        # 2. Tamper latch.
        if self.tamper_active and not self.fault_latched:
            self.fault_latched = True
            self.fault_reason = "ENCLOSURE TAMPER"
            self.relay_closed = False
            self.appliance.stop()
            self._add_event("SW1 tamper latch: K1 commanded OPEN.")

        # 3. Appliance or CSV-replay electrical source.
        if self.csv_replay_active and self.csv_records:
            self.csv_replay_accum += dt
            if self.csv_replay_accum >= self.csv_replay_interval:
                self.csv_replay_accum = 0.0
                self.csv_replay_index = (self.csv_replay_index + 1) % len(self.csv_records)
            rec = self.csv_records[self.csv_replay_index]
            if self.grid_connected and self.relay_closed and not self.fault_latched:
                self._apply_csv_record(rec)
            else:
                self._measure_from_waveforms(0.0, 0.0, 0.0)
        else:
            v_available = self.grid_voltage_set if self.grid_connected else 0.0
            if self.grid_connected and self.relay_closed and not self.fault_latched:
                if v_available < GRID_UV_V or v_available > GRID_OV_V:
                    self.fault_latched = True
                    self.fault_reason = f"GRID VOLTAGE {v_available:.1f} V"
                    self.relay_closed = False
                    self.appliance.stop()
                    self._add_event(f"Grid voltage outside modeled {GRID_UV_V:.0f}–{GRID_OV_V:.0f} V window; K1 OPEN.")

            if self.grid_connected and self.relay_closed and not self.fault_latched:
                if self.sim_time < self.forced_overload_until:
                    source_i = self.forced_overload_a
                    source_pf = 0.90
                    source_p = v_available * source_i * source_pf
                    self.appliance.stop()
                else:
                    self.appliance.step(dt, v_available, self.mechanical_load_pct)
                    source_i = self.appliance.current_a
                    source_pf = self.appliance.pf
                    source_p = self.appliance.active_power_w

                if source_i > RELAY_TRIP_A:
                    self.overcurrent_elapsed += dt
                else:
                    self.overcurrent_elapsed = 0.0

                if self.overcurrent_elapsed >= OVERCURRENT_DELAY_S:
                    self.fault_latched = True
                    self.fault_reason = f"OVERCURRENT {source_i:.2f} A"
                    self.relay_closed = False
                    self.appliance.stop()
                    source_i = 0.0
                    source_pf = 0.0
                    self._add_event(
                        f"Current exceeded {RELAY_TRIP_A:.1f} A for {OVERCURRENT_DELAY_S*1000:.0f} ms; K1 OPEN."
                    )
                self._measure_from_waveforms(v_available, source_i, source_pf)
            else:
                self.appliance.stop()
                # Sense the incoming grid voltage even with K1 open; only load
                # current is interrupted by the relay.
                self._measure_from_waveforms(v_available, 0.0, 0.0)

        # If any trip opened the relay during this tick, current must be zero,
        # but the upstream voltage measurement should remain visible.
        if not self.relay_closed or not self.grid_connected or self.fault_latched:
            if self.i_rms > 0:
                self._measure_from_waveforms(
                    self.grid_voltage_set if self.grid_connected else 0.0, 0.0, 0.0
                )

        # 4. Energy accumulation and local record generation.
        self.energy_wh += self.p_active_w * dt / 3600.0
        self.session_wh += self.p_active_w * dt / 3600.0

        if self.sim_time - self.last_record_time >= RECORD_PERIOD_S:
            self.last_record_time = self.sim_time
            self._commit_ledger_record()

        # 5. NGO card-tap state machine.
        if self.tap_stage in ("HANDSHAKE", "SYNCING"):
            self.tap_elapsed += dt
            if self.tap_stage == "HANDSHAKE" and self.tap_elapsed >= 0.35:
                self.tap_stage = "SYNCING"
                self._add_event("[BLE TAP 1/3] Simulated officer mutual-auth handshake passed.")
            if self.tap_stage == "SYNCING" and self.tap_elapsed >= 0.85:
                if self.ble_connected:
                    self._finish_card_sync()
                elif not any("Waiting for BLE" in x for x in self.event_log):
                    self._add_event("Waiting for BLE before queued ledger sync can complete.")

        # 6. Trends for the single dashboard.
        self.history_t.append(self.sim_time)
        self.history_p.append(self.p_active_w)
        self.history_i.append(self.i_rms)
        self.history_cap.append(self.cap_voltage)


# =============================================================================
# RESPONSIVE SCROLLABLE CONTROL PANEL
# =============================================================================
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, width=320):
        super().__init__(parent, bg=NAVY_PANEL, highlightbackground=YELLOW,
                         highlightthickness=1, width=width)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(self, bg=NAVY_PANEL, highlightthickness=0, width=width-18)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=NAVY_PANEL)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._configure_scroll)
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.bind_all("<MouseWheel>", self._mousewheel)

    def _configure_scroll(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_inner(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _mousewheel(self, event):
        # Multiple scroll panes share the Tk toplevel; only the pane under the
        # pointer should react to the global mouse-wheel event.
        widget = self.winfo_containing(event.x_root, event.y_root)
        inside = False
        while widget is not None:
            if widget is self:
                inside = True
                break
            widget = getattr(widget, "master", None)
        if inside:
            units = int(-1 * (event.delta / 120))
            if units == 0:
                units = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(units, "units")


# =============================================================================
# UNIFIED DASHBOARD
# =============================================================================
class WattCreditUnifiedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WattCredit — Unified Appliance, Metering & NGO Digital Twin")
        # Fit the actual desktop work area instead of opening taller than the
        # available screen (the old 1580x980 geometry clipped the right panel).
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(1450, max(1120, screen_w - 70))
        win_h = min(690, max(620, screen_h - 110))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(1050, 600)
        self.root.configure(bg=NAVY_BG)

        self.engine = WattCreditUnifiedEngine()
        self.running = True
        self._after_id = None
        self._last_explanation = None
        self._last_log_snapshot = None
        self._last_credit_snapshot = None
        self._last_plot_draw = 0.0
        self._plot_interval = 0.22  # cap expensive Matplotlib redraws at ~4.5 FPS
        self._last_ngo_refresh = 0.0

        self._configure_styles()
        self._build_dashboard()
        self._schedule_tick()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Watt.Horizontal.TScale",
            background=NAVY_PANEL, troughcolor=NAVY_WELL,
            bordercolor=YELLOW, lightcolor=YELLOW, darkcolor=AMBER
        )
        style.configure(
            "Watt.TCombobox", fieldbackground=NAVY_WELL,
            background=NAVY_PANEL, foreground=YELLOW,
            arrowcolor=YELLOW
        )
        style.configure(
            "Watt.TScrollbar", background=NAVY_PANEL,
            troughcolor=NAVY_WELL, arrowcolor=YELLOW
        )

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, bg=NAVY_PANEL, fg=YELLOW,
                 font=FONT_SECTION).pack(anchor="w", padx=10, pady=(9, 4))
        tk.Frame(parent, bg=YELLOW, height=1).pack(fill="x", padx=10, pady=(0, 6))

    def _button(self, parent, text, command, primary=False):
        return tk.Button(
            parent, text=text, command=command,
            bg=YELLOW if primary else NAVY_WELL,
            fg=NAVY_BG if primary else YELLOW,
            activebackground=AMBER, activeforeground=NAVY_BG,
            font=("Georgia", 9, "bold"), relief="ridge", bd=2,
            padx=5, pady=5, cursor="hand2"
        )

    def _make_slider(self, parent, label, var, lo, hi, fmt, callback):
        label_widget = tk.Label(parent, text=fmt(var.get()), bg=NAVY_PANEL,
                                fg=CREAM, font=FONT_BODY, anchor="w")
        label_widget.pack(fill="x", padx=10, pady=(5, 0))
        scale = ttk.Scale(
            parent, from_=lo, to=hi, variable=var,
            style="Watt.Horizontal.TScale",
            command=lambda value: self._slider_changed(value, label_widget, fmt, callback)
        )
        scale.pack(fill="x", padx=10, pady=(0, 4))
        return label_widget, scale

    def _slider_changed(self, value, label_widget, formatter, callback):
        number = float(value)
        label_widget.config(text=formatter(number))
        callback(number)

    def _build_dashboard(self):
        header = tk.Frame(self.root, bg=NAVY_PANEL,
                          highlightbackground=YELLOW, highlightthickness=2)
        header.pack(fill="x", padx=10, pady=(9, 7))
        tk.Label(
            header,
            text="WATTCREDIT — UNIFIED DIGITAL TWIN",
            bg=NAVY_PANEL, fg=YELLOW, font=FONT_TITLE
        ).pack(anchor="w", padx=13, pady=(7, 1))
        tk.Label(
            header,
            text="Appliance behavior  →  Rev B0 isolated metrology  →  offline cryptographic ledger  →  NGO field underwriting",
            bg=NAVY_PANEL, fg=CREAM, font=("Georgia", 9, "italic")
        ).pack(anchor="w", padx=13, pady=(0, 7))

        self.mode_tabs = ttk.Notebook(self.root)
        self.mode_tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        main = tk.Frame(self.mode_tabs, bg=NAVY_BG)
        self.mode_tabs.add(main, text="⚡  ELECTRICAL TWIN")

        # LEFT: electrical controls only; NGO controls move to their own workspace.
        self.left = ScrollableFrame(main, width=315)
        self.left.pack(side="left", fill="y", padx=(0, 8))
        c = self.left.inner

        self._section_label(c, "I. APPLIANCE CONNECTED TO MODULE")
        tk.Label(c, text="Appliance profile", bg=NAVY_PANEL, fg=CREAM,
                 font=FONT_BODY).pack(anchor="w", padx=10)
        self.profile_var = tk.StringVar(value=self.engine.appliance.profile_name)
        self.profile_combo = ttk.Combobox(
            c, textvariable=self.profile_var, values=list(APPLIANCE_PROFILES),
            state="readonly", style="Watt.TCombobox"
        )
        self.profile_combo.pack(fill="x", padx=10, pady=(2, 4))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_change)

        self.profile_desc = tk.Label(
            c, text=self.engine.appliance.profile["description"],
            bg=NAVY_PANEL, fg=MUTED, font=("Times New Roman", 9),
            wraplength=275, justify="left"
        )
        self.profile_desc.pack(anchor="w", padx=10, pady=(0, 5))

        self.machine_state_label = tk.Label(
            c, text="MACHINE: STOPPED", bg=NAVY_WELL, fg=CYAN,
            font=FONT_MONO_BOLD, padx=6, pady=6
        )
        self.machine_state_label.pack(fill="x", padx=9, pady=4)
        row = tk.Frame(c, bg=NAVY_PANEL)
        row.pack(fill="x", padx=9, pady=3)
        self._button(row, "START", self._start_machine, True).pack(
            side="left", fill="x", expand=True, padx=(0, 3)
        )
        self._button(row, "STOP", self._stop_machine).pack(
            side="left", fill="x", expand=True, padx=(3, 0)
        )

        self.load_var = tk.DoubleVar(value=65.0)
        self._make_slider(
            c, "Mechanical load", self.load_var, 10, 125,
            lambda v: f"Mechanical load: {v:.0f}%",
            self._set_mechanical_load
        )
        self.grid_var = tk.DoubleVar(value=230.0)
        self._make_slider(
            c, "Grid voltage", self.grid_var, 160, 280,
            lambda v: f"Grid voltage: {v:.0f} V RMS",
            self._set_grid_voltage
        )

        self._section_label(c, "II. GRID, PROTECTION & CONNECTIVITY")
        self.grid_button = self._button(c, "INJECT GRID BLACKOUT", self._toggle_grid)
        self.grid_button.pack(fill="x", padx=9, pady=3)
        self.ble_button = self._button(c, "BLE: DISCONNECT", self._toggle_ble)
        self.ble_button.pack(fill="x", padx=9, pady=3)
        self._button(c, "INJECT 12.5 A OVERLOAD", self._inject_overload).pack(
            fill="x", padx=9, pady=3
        )
        self._button(c, "TRIGGER SW1 TAMPER", self._trigger_tamper).pack(
            fill="x", padx=9, pady=3
        )
        self._button(c, "RESET FAULT LATCH", self._reset_faults).pack(
            fill="x", padx=9, pady=3
        )

        self._section_label(c, "III. CSV SHIFT LOG & CALIBRATION")
        csv_row = tk.Frame(c, bg=NAVY_PANEL)
        csv_row.pack(fill="x", padx=9, pady=2)
        self._button(csv_row, "LOAD CSV", self._load_csv).pack(
            side="left", fill="x", expand=True, padx=(0, 3)
        )
        self._button(csv_row, "GENERATE SAMPLE", self._generate_csv).pack(
            side="left", fill="x", expand=True, padx=(3, 0)
        )
        self.csv_status = tk.Label(
            c, text="No shift CSV loaded", bg=NAVY_PANEL, fg=CYAN,
            font=("Courier New", 8), wraplength=275, justify="left"
        )
        self.csv_status.pack(anchor="w", padx=10, pady=3)
        self.replay_button = self._button(c, "START CSV REPLAY", self._toggle_csv_replay)
        self.replay_button.pack(fill="x", padx=9, pady=3)

        self.threshold_var = tk.DoubleVar(value=300.0)
        self._make_slider(
            c, "Productive wattage cutoff", self.threshold_var, 100, 800,
            lambda v: f"Productive cutoff: {v:.0f} W",
            self._set_threshold
        )
        self.rate_var = tk.DoubleVar(value=185.0)
        self._make_slider(
            c, "Credit multiplier", self.rate_var, 100, 350,
            lambda v: f"Credit multiplier: ₹{v:.0f} / kWh",
            self._set_credit_rate
        )
        self.days_var = tk.DoubleVar(value=self.engine.active_days_30d)
        self._make_slider(
            c, "Active operating days", self.days_var, 1, 30,
            lambda v: f"Active days (30d): {v:.0f}",
            self._set_active_days
        )
        self.hours_var = tk.DoubleVar(value=self.engine.daily_prod_hours)
        self._make_slider(
            c, "Daily productive hours", self.hours_var, 0, 14,
            lambda v: f"Productive hours/day: {v:.1f}",
            self._set_daily_hours
        )

        self._section_label(c, "IV. NGO OFFICER FIELD ACTION")
        self._button(c, "TAP NGO OFFICER BLE CARD", self._tap_officer, True).pack(
            fill="x", padx=9, pady=4
        )
        self.tap_status = tk.Label(
            c, text="CARD STATE: IDLE", bg=NAVY_WELL, fg=CYAN,
            font=FONT_MONO_BOLD, padx=6, pady=6
        )
        self.tap_status.pack(fill="x", padx=9, pady=3)

        self._section_label(c, "V. SIMULATION PERFORMANCE")
        self.fps_var = tk.DoubleVar(value=20)
        self.fps_label = tk.Label(
            c, text="Dashboard FPS: 20", bg=NAVY_PANEL, fg=CREAM,
            font=FONT_BODY
        )
        self.fps_label.pack(anchor="w", padx=10)
        ttk.Scale(
            c, from_=10, to=60, variable=self.fps_var,
            style="Watt.Horizontal.TScale", command=self._set_fps
        ).pack(fill="x", padx=10, pady=(0, 8))

        tk.Label(
            c,
            text="FPS changes the UI/simulation update interval. The modeled ADC sampling rate remains 4 kSPS.",
            bg=NAVY_PANEL, fg=MUTED, font=("Times New Roman", 9),
            wraplength=275, justify="left"
        ).pack(anchor="w", padx=10, pady=(0, 12))

        # CENTER: exactly three plots; each axis and Line2D is created once.
        center = tk.Frame(main, bg=NAVY_PANEL,
                          highlightbackground=YELLOW, highlightthickness=1)
        center.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._section_label(center, "VI. LIVE ELECTRICAL SIGNATURE — PERSISTENT PLOTS")

        self.fig = Figure(figsize=(7.0, 5.15), dpi=85, facecolor=NAVY_PANEL)
        self.ax_wave = self.fig.add_subplot(311)
        self.ax_power = self.fig.add_subplot(312)
        self.ax_current = self.ax_power.twinx()
        self.ax_cap = self.fig.add_subplot(313)
        self.fig.subplots_adjust(
            hspace=0.62, left=0.105, right=0.90, top=0.95, bottom=0.09
        )

        for ax in (self.ax_wave, self.ax_power, self.ax_current, self.ax_cap):
            ax.set_facecolor(NAVY_WELL)
            ax.tick_params(colors=MUTED, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(YELLOW)
                spine.set_linewidth(0.8)
            ax.grid(True, color=GRID, linestyle="--", linewidth=0.55)

        # Waveform: one voltage trace and one current trace, scaled for visibility.
        self.line_voltage, = self.ax_wave.plot(
            [], [], color=YELLOW, lw=1.35, label="Voltage (V)"
        )
        self.line_current, = self.ax_wave.plot(
            [], [], color=CYAN, lw=1.25, label="Current (scaled)"
        )
        self.ax_wave.set_title(
            "50 Hz AC waveform — 4 kSPS simultaneous sample model",
            color=YELLOW, fontname="DejaVu Serif", fontsize=9, fontweight="bold"
        )
        self.ax_wave.set_ylabel("Waveform amplitude", color=CREAM)
        self.ax_wave.set_xlim(0, 20)
        self.ax_wave.set_ylim(-450, 450)
        self.ax_wave.legend(
            loc="upper right", fontsize=7, facecolor=NAVY_PANEL,
            edgecolor=YELLOW, labelcolor=CREAM
        )

        # Trend: active power and current share one time axis with separate y scales.
        self.line_power, = self.ax_power.plot(
            [], [], color=YELLOW, lw=1.5, label="Active power (W)"
        )
        self.line_current_trend, = self.ax_current.plot(
            [], [], color=CYAN, lw=1.1, alpha=0.95, label="Current (A)"
        )
        self.ax_power.set_title(
            "Measured load trend — active power and RMS current",
            color=YELLOW, fontname="DejaVu Serif", fontsize=9, fontweight="bold"
        )
        self.ax_power.set_ylabel("Power (W)", color=YELLOW)
        self.ax_current.set_ylabel("Current (A)", color=CYAN)
        self.ax_power.tick_params(axis="y", colors=YELLOW, labelsize=8)
        self.ax_current.tick_params(axis="y", colors=CYAN, labelsize=8)
        self.ax_power.set_xlim(0, 8)
        self.ax_power.set_ylim(0, 3000)
        self.ax_current.set_ylim(0, 15)
        lines = [self.line_power, self.line_current_trend]
        self.ax_power.legend(
            lines, [ln.get_label() for ln in lines],
            loc="upper right", fontsize=7, facecolor=NAVY_PANEL,
            edgecolor=YELLOW, labelcolor=CREAM
        )

        self.line_cap, = self.ax_cap.plot(
            [], [], color=CYAN, lw=1.5, label="5V_LOGIC / CS1"
        )
        self.ax_cap.axhline(
            PWR_FAIL_V, color=YELLOW, ls="--", lw=0.9, label="PWR_FAIL 4.55 V"
        )
        self.ax_cap.axhline(
            LDO_MIN_INPUT_V, color=CORAL, ls=":", lw=0.9, label="LDO input 3.60 V"
        )
        self.ax_cap.set_title(
            "Supercapacitor / logic rail hold-up",
            color=YELLOW, fontname="DejaVu Serif", fontsize=9, fontweight="bold"
        )
        self.ax_cap.set_ylabel("Voltage (V)", color=CREAM)
        self.ax_cap.set_xlabel("Simulation time (s)", color=CREAM)
        self.ax_cap.set_xlim(0, 8)
        self.ax_cap.set_ylim(3.2, 5.1)
        self.ax_cap.legend(
            loc="upper right", fontsize=7, facecolor=NAVY_PANEL,
            edgecolor=YELLOW, labelcolor=CREAM
        )

        self.canvas = FigureCanvasTkAgg(self.fig, master=center)
        self.canvas.get_tk_widget().pack(
            fill="both", expand=True, padx=6, pady=(0, 7)
        )

        # RIGHT: compact unified live telemetry, explanation, credit and event log.
        self.right_scroll = ScrollableFrame(main, width=370)
        self.right_scroll.pack(side="right", fill="y", padx=(0, 0))
        right = self.right_scroll.inner

        self._section_label(right, "VII. LIVE MODULE REGISTERS")
        self.metrics = tk.Label(
            right, text="", bg=NAVY_WELL, fg=YELLOW,
            font=FONT_MONO_BOLD, justify="left", anchor="w",
            padx=9, pady=8
        )
        self.metrics.pack(fill="x", padx=8, pady=(0, 7))

        self._section_label(right, "VIII. INTERNAL SIGNAL PATH")
        self.signal_path = tk.Text(
            right, height=10, bg=NAVY_WELL, fg=CREAM,
            font=("Courier New", 8), wrap="word", relief="solid", bd=1,
            padx=7, pady=6
        )
        self.signal_path.pack(fill="x", padx=8, pady=(0, 6))
        self.signal_path.insert(
            "1.0",
            "230 V AC / 50 Hz\n"
            "   ├─ K1 relay / protection\n"
            "   ├─ Voltage: R2–R6 divider\n"
            "   │       → AMC1301 U1\n"
            "   │       → ADS131M02 U3 CH1\n"
            "   └─ Current: R1 5 mΩ Kelvin shunt\n"
            "           → AMC1301 U2\n"
            "           → ADS131M02 U3 CH2\n"
            "                 ↓ SPI / DMA model\n"
            "             ESP32-S3 U4\n"
            "             RMS / P / Wh / fault logic\n"
            "                 ↓\n"
            "             ATECC608 U5 (crypto concept)\n"
            "             W25Q64 U6 (offline ledger)\n"
            "             BLE GATT 0xFF01 / 0xFF02\n"
            "\n"
            "CS1 + U9 + U8: last-gasp logic hold-up\n"
            "SW1: enclosure tamper interlock"
        )
        self.signal_path.configure(state="disabled")

        self._section_label(right, "IX. LIVE EXPLANATION")
        self.explanation = tk.Text(
            right, height=7, bg=NAVY_WELL, fg=CREAM,
            font=("Times New Roman", 9), wrap="word", relief="solid", bd=1,
            padx=7, pady=6
        )
        self.explanation.pack(fill="x", padx=8, pady=(0, 6))

        # NGO underwriting lives exclusively in its own tab. The electrical
        # event log remains here because it reports meter/protection activity.
        self._section_label(right, "X. ELECTRICAL LEDGER / BLE EVENTS")
        self.event_box = tk.Text(
            right, height=8, bg=NAVY_WELL, fg=CYAN,
            font=("Courier New", 8), wrap="word", relief="solid", bd=1,
            padx=7, pady=6
        )
        self.event_box.pack(fill="x", padx=8, pady=(0, 8))
        self.event_box.configure(state="disabled")

        self._refresh_explanation(force=True)

        # Hide the legacy NGO controls from the electrical sidebar. Their
        # dedicated counterparts are built on the NGO tab below. Keep the FPS
        # section visible at the end of the electrical sidebar.
        sidebar_children = list(c.winfo_children())
        for child in sidebar_children[18:35]:
            child.pack_forget()

        self._build_ngo_workspace()
        self.mode_tabs.bind("<<NotebookTabChanged>>", self._on_mode_changed)

    def _build_ngo_workspace(self):
        page = tk.Frame(self.mode_tabs, bg=NAVY_BG)
        self.mode_tabs.add(page, text="NGO  CREDIT TWIN")
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=2)
        page.grid_rowconfigure(0, weight=1)

        controls = tk.Frame(page, bg=NAVY_PANEL, highlightbackground=YELLOW,
                            highlightthickness=1, width=360)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        controls.grid_propagate(False)
        self._section_label(controls, "NGO FIELD DATA & CALIBRATION")
        tk.Label(controls, text="Import a productive-use shift log or generate a demonstration dataset.",
                 bg=NAVY_PANEL, fg=CREAM, font=FONT_BODY, wraplength=320,
                 justify="left").pack(anchor="w", padx=12, pady=(2, 8))
        self._button(controls, "LOAD SHIFT CSV", self._load_csv, True).pack(fill="x", padx=10, pady=3)
        self._button(controls, "GENERATE 30-DAY SAMPLE", self._generate_csv).pack(fill="x", padx=10, pady=3)
        self.ngo_csv_status = tk.Label(controls, text="No shift CSV loaded", bg=NAVY_WELL,
                                       fg=CYAN, font=FONT_MONO, wraplength=320,
                                       justify="left", padx=7, pady=7)
        self.ngo_csv_status.pack(fill="x", padx=10, pady=5)
        self._button(controls, "START / STOP CSV REPLAY", self._toggle_csv_replay).pack(fill="x", padx=10, pady=3)

        self._section_label(controls, "UNDERWRITING CALIBRATION")
        self.threshold_var = getattr(self, "threshold_var", tk.DoubleVar(value=300.0))
        self.rate_var = getattr(self, "rate_var", tk.DoubleVar(value=185.0))
        self.days_var = getattr(self, "days_var", tk.DoubleVar(value=self.engine.active_days_30d))
        self.hours_var = getattr(self, "hours_var", tk.DoubleVar(value=self.engine.daily_prod_hours))
        self._make_slider(controls, "Productive wattage cutoff", self.threshold_var, 100, 800,
                          lambda v: f"Productive cutoff: {v:.0f} W", self._set_threshold)
        self._make_slider(controls, "Credit multiplier", self.rate_var, 100, 350,
                          lambda v: f"Credit multiplier: ₹{v:.0f} / kWh", self._set_credit_rate)
        self._make_slider(controls, "Active operating days", self.days_var, 1, 30,
                          lambda v: f"Active days (30d): {v:.0f}", self._set_active_days)
        self._make_slider(controls, "Daily productive hours", self.hours_var, 0, 14,
                          lambda v: f"Productive hours/day: {v:.1f}", self._set_daily_hours)
        self._section_label(controls, "NGO OFFICER VERIFICATION")
        self._button(controls, "TAP NGO OFFICER BLE CARD", self._tap_officer, True).pack(fill="x", padx=10, pady=4)
        self.ngo_tap_status = tk.Label(controls, text="CARD STATE: IDLE", bg=NAVY_WELL,
                                       fg=CYAN, font=FONT_MONO_BOLD, padx=7, pady=7)
        self.ngo_tap_status.pack(fill="x", padx=10, pady=4)
        tk.Label(controls, text="Indicative underwriting only — not a lending decision.",
                 bg=NAVY_PANEL, fg=MUTED, font=("Times New Roman", 9),
                 wraplength=320, justify="left").pack(anchor="w", padx=12, pady=10)

        result = tk.Frame(page, bg=NAVY_PANEL, highlightbackground=YELLOW,
                          highlightthickness=1)
        result.grid(row=0, column=1, sticky="nsew")
        self._section_label(result, "PRODUCTIVE-USE CREDIT ASSESSMENT")
        self.ngo_credit_view = tk.Text(result, bg=NAVY_WELL, fg=YELLOW,
                                       font=("Courier New", 11), wrap="word",
                                       relief="flat", padx=18, pady=16)
        self.ngo_credit_view.pack(fill="both", expand=True, padx=12, pady=8)
        self.ngo_credit_view.configure(state="disabled")
        self._section_label(result, "FIELD SYNC / LEDGER EVENTS")
        self.ngo_event_view = tk.Text(result, height=10, bg=NAVY_WELL, fg=CYAN,
                                      font=("Courier New", 9), wrap="word",
                                      relief="flat", padx=12, pady=10)
        self.ngo_event_view.pack(fill="x", padx=12, pady=(0, 12))
        self._refresh_ngo_workspace()

    def _on_mode_changed(self, _event=None):
        # A tab switch updates only the selected workspace; no forced redraw.
        if self.mode_tabs.index("current") == 1:
            self._refresh_ngo_workspace()
            self._last_ngo_refresh = float(self.root.tk.call("clock", "milliseconds")) / 1000.0
        else:
            self._refresh_metrics()

    def _refresh_ngo_workspace(self):
        if not hasattr(self, "ngo_credit_view"):
            return
        credit = self._credit_text()
        self.ngo_credit_view.configure(state="normal")
        if self.ngo_credit_view.get("1.0", "end-1c") != credit:
            self.ngo_credit_view.delete("1.0", "end")
            self.ngo_credit_view.insert("1.0", credit)
        self.ngo_credit_view.configure(state="disabled")
        self.ngo_csv_status.configure(text=getattr(self, "csv_status", None).cget("text")
                                      if hasattr(self, "csv_status") else "No shift CSV loaded")
        self.ngo_tap_status.configure(text=f"CARD STATE: {self.engine.tap_stage}")
        events = "\n".join(list(self.engine.event_log)[:30])
        if self.ngo_event_view.get("1.0", "end-1c") != events:
            self.ngo_event_view.delete("1.0", "end")
            self.ngo_event_view.insert("1.0", events)

    # -------------------------------------------------------------------------
    # UI callbacks
    # -------------------------------------------------------------------------
    def _on_profile_change(self, _=None):
        self.engine.select_appliance(self.profile_var.get())
        self.profile_desc.config(text=self.engine.appliance.profile["description"])
        prof = self.engine.appliance.profile
        if self.engine.csv_records:
            self.days_var.set(self.engine.active_days_30d)
            self.hours_var.set(self.engine.daily_prod_hours)
        else:
            self.days_var.set(prof["active_days"])
            self.hours_var.set(prof["daily_hours"])
            self._set_active_days(prof["active_days"])
            self._set_daily_hours(prof["daily_hours"])
        self._refresh_credit_box(force=True)

    def _start_machine(self):
        if not self.engine.start_appliance():
            messagebox.showwarning(
                "Cannot start appliance",
                "Check that grid power is available, the relay is closed and no fault is latched."
            )

    def _stop_machine(self):
        self.engine.stop_appliance()

    def _set_mechanical_load(self, value):
        self.engine.mechanical_load_pct = value
        self.engine.appliance.mechanical_load_pct = value

    def _set_grid_voltage(self, value):
        self.engine.grid_voltage_set = value

    def _toggle_grid(self):
        self.engine.set_grid(not self.engine.grid_connected)
        self.grid_button.config(
            text="RESTORE GRID" if not self.engine.grid_connected
            else "INJECT GRID BLACKOUT"
        )

    def _toggle_ble(self):
        self.engine.set_ble(not self.engine.ble_connected)
        self.ble_button.config(
            text="BLE: DISCONNECT" if self.engine.ble_connected
            else "BLE: RECONNECT"
        )

    def _inject_overload(self):
        self.engine.inject_overload()

    def _trigger_tamper(self):
        self.engine.trigger_tamper()

    def _reset_faults(self):
        self.engine.reset_faults()
        self.grid_var.set(230.0)
        self.engine.grid_voltage_set = 230.0
        self.grid_button.config(text="INJECT GRID BLACKOUT")

    def _load_csv(self):
        path = filedialog.askopenfilename(
            title="Load WattCredit 30-day shift CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            self.engine.import_csv(path)
            stats = self.engine.csv_underwriting_stats
            self.csv_status.config(
                text=f"{self.engine.csv_name}: {stats['rows']} rows | "
                     f"{stats['productive_rows']} productive | "
                     f"{stats['days']} days"
            )
            self.days_var.set(self.engine.active_days_30d)
            self.hours_var.set(self.engine.daily_prod_hours)
            self._refresh_credit_box(force=True)
            self._refresh_ngo_workspace()
        except Exception as exc:
            messagebox.showerror("CSV import failed", str(exc))

    def _generate_csv(self):
        path = filedialog.asksaveasfilename(
            title="Save sample 30-day shift CSV",
            defaultextension=".csv",
            initialfile="wattcredit_sample_30d.csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return
        try:
            generate_sample_record_csv(path)
            self.engine.import_csv(path)
            stats = self.engine.csv_underwriting_stats
            self.csv_status.config(
                text=f"Generated {self.engine.csv_name}: {stats['rows']} rows"
            )
            self.days_var.set(self.engine.active_days_30d)
            self.hours_var.set(self.engine.daily_prod_hours)
            self._refresh_credit_box(force=True)
            self._refresh_ngo_workspace()
            messagebox.showinfo("Sample CSV generated", f"Created:\n{path}")
        except Exception as exc:
            messagebox.showerror("Sample generation failed", str(exc))

    def _toggle_csv_replay(self):
        active = self.engine.toggle_csv_replay()
        if active is False and not self.engine.csv_records:
            messagebox.showinfo("No CSV loaded", "Load a shift CSV before starting replay.")
        self.replay_button.config(
            text="STOP CSV REPLAY" if active else "START CSV REPLAY"
        )

    def _set_threshold(self, value):
        self.engine.set_credit_calibration(threshold=value)
        if self.engine.csv_records:
            self.days_var.set(self.engine.active_days_30d)
            self.hours_var.set(self.engine.daily_prod_hours)
        self._refresh_credit_box()

    def _set_credit_rate(self, value):
        self.engine.set_credit_calibration(rate=value)
        self._refresh_credit_box()

    def _set_active_days(self, value):
        self.engine.set_credit_calibration(days=value)
        self._refresh_credit_box()

    def _set_daily_hours(self, value):
        self.engine.set_credit_calibration(hours=value)
        self._refresh_credit_box()

    def _tap_officer(self):
        self.engine.start_card_tap()
        self.tap_status.config(text="CARD STATE: HANDSHAKE")

    def _set_fps(self, value):
        fps = int(round(float(value)))
        self.engine.fps = int(clamp(fps, 10, 60))
        self.engine.dt = 1.0 / self.engine.fps
        self.fps_label.config(text=f"Dashboard FPS: {self.engine.fps}")

    # -------------------------------------------------------------------------
    # Efficient UI refresh: no axes clearing/recreation and no needless text I/O.
    # -------------------------------------------------------------------------
    def _set_text_if_changed(self, widget, content, cache_name):
        if getattr(self, cache_name) == content:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")
        setattr(self, cache_name, content)

    def _refresh_explanation(self, force=False):
        e = self.engine
        if e.fault_latched:
            text = (
                f"PROTECTION LATCHED — {e.fault_reason}\n\n"
                "• The modeled fault/tamper condition has opened K1.\n"
                "• Appliance current is forced to zero after relay opening.\n"
                "• Fault status is included in the hash-chained local record.\n"
                "• Inspect the simulated condition, then use RESET FAULT LATCH."
            )
        elif not e.grid_connected:
            text = (
                f"GRID BLACKOUT — backup rail {e.cap_voltage:.2f} V\n\n"
                "• AC supply is absent; the appliance is de-energized.\n"
                "• CS1 supports the logic rail temporarily.\n"
                "• U9 asserts PWR_FAIL at 4.55 V and K1 is shed.\n"
                "• A final ledger record is committed before the modeled LDO dropout."
            )
        elif e.csv_replay_active:
            text = (
                "CSV TELEMETRY REPLAY\n\n"
                f"• Source: {e.csv_name}\n"
                f"• Record: {e.csv_replay_index + 1}/{len(e.csv_records)}\n"
                "• Imported voltage/current/PF observations are driving the meter display.\n"
                "• The CSV is also used for productive-hour and credit-score calibration."
            )
        elif e.i_rms > 0:
            text = (
                f"NORMAL METERING — {e.appliance.state}\n\n"
                "• Voltage path: divider → AMC1301 U1 → ADS131M02 CH1.\n"
                "• Current path: Kelvin shunt → AMC1301 U2 → ADS131M02 CH2.\n"
                "• Both channels are sampled simultaneously at the modeled 4 kSPS.\n"
                "• ESP32-S3 calculates RMS, active power and accumulated Wh.\n"
                "• Ledger records are hash-chained and sent by BLE or queued locally."
            )
        else:
            text = (
                "STANDBY — NO APPLIANCE CURRENT\n\n"
                "• Grid is available and K1 is closed.\n"
                "• Appliance is stopped; current and active power are near zero.\n"
                "• Press START to observe motor startup and operating load behavior."
            )
        self._set_text_if_changed(self.explanation, text, "_last_explanation")

    def _credit_text(self):
        e = self.engine
        if not e.underwriting_ready:
            return (
                "STATUS: WAITING FOR NGO CARD TAP\n"
                "Import a 30-day CSV or use the preset profile, then tap the officer card.\n"
                f"Cutoff: {e.productive_threshold_w:.0f} W | Rate: ₹{e.credit_rate_inr_kwh:.0f}/kWh"
            )
        b = e.score_parts
        if e.tap_stage == "HANDSHAKE":
            status = "CARD AUTHENTICATION IN PROGRESS"
        elif e.tap_stage == "SYNCING":
            status = "FLASH LEDGER SYNC IN PROGRESS"
        elif e.tap_stage == "VERIFIED":
            status = "UNDERWRITING VERIFIED (SIMULATED)"
        else:
            status = "CALIBRATION READY — TAP OFFICER CARD"
        return (
            f"{status}\n"
            f"Score: {e.credit_score}/100 | Indicative limit: ₹{e.loan_limit_inr:,}\n"
            f"Tier: {e.credit_tier}\n"
            f"Women-SHG rebate: +{e.rebate_pct:.1f}% p.a. (model setting)\n"
            f"30d estimated productive energy: {b['estimated_kwh']:.1f} kWh\n"
            f"Productive power: {b['productive_power_w']:.0f} W | "
            f"Days: {b['active_days']} | Hours/day: {b['daily_hours']:.1f}\n"
            f"Consistency {b['consistency']:.0f}% | Utilization {b['utilization']:.0f}%\n"
            f"Integrity {b['integrity']:.0f}% | Power quality {b['power_quality']:.0f}%\n"
            "Weights: 35% / 35% / 20% / 10%"
        )

    def _refresh_credit_box(self, force=False):
        # Compatibility hook for existing calibration callbacks. The credit
        # result is rendered only in the NGO workspace.
        if hasattr(self, "ngo_credit_view"):
            credit = self._credit_text()
            if self.ngo_credit_view.get("1.0", "end-1c") != credit:
                self.ngo_credit_view.configure(state="normal")
                self.ngo_credit_view.delete("1.0", "end")
                self.ngo_credit_view.insert("1.0", credit)
                self.ngo_credit_view.configure(state="disabled")

    def _refresh_metrics(self):
        e = self.engine
        relay = "CLOSED" if e.relay_closed else "OPEN"
        ble = "CONNECTED" if e.ble_connected else f"OFFLINE ({len(e.flash_queue)} queued)"
        adc_warning = " CLIP!" if (e.v_adc_clip or e.i_adc_clip) else ""
        text = (
            f"V_RMS       {e.v_rms:7.2f} V\n"
            f"I_RMS       {e.i_rms:7.3f} A\n"
            f"ACTIVE P    {e.p_active_w:7.1f} W\n"
            f"APPARENT S  {e.s_apparent_va:7.1f} VA\n"
            f"POWER FACT  {e.pf:7.3f}\n"
            f"ENERGY      {e.energy_wh:7.4f} Wh\n"
            f"ADC V/I PK  {e.v_adc_peak:5.3f}/{e.i_adc_peak:5.3f} V{adc_warning}\n"
            f"CS1 RAIL    {e.cap_voltage:5.2f} V\n"
            f"K1 RELAY    {relay}\n"
            f"BLE         {ble}\n"
            f"LEDGER      {e.sequence} records | TX {e.ble_packets_sent}"
        )
        self.metrics.config(text=text, fg=CORAL if (e.v_adc_clip or e.i_adc_clip or e.fault_latched) else YELLOW)

    def _refresh_plots(self):
        e = self.engine
        # Update the pre-created traces only. No axes are cleared or recreated.
        self.line_voltage.set_data(e.wave_t_ms, e.sample_v)
        current_scale = (
            max(1.0, np.max(np.abs(e.sample_v)) / max(1e-9, np.max(np.abs(e.sample_i))))
            if np.max(np.abs(e.sample_i)) > 1e-9 else 1.0
        )
        self.line_current.set_data(e.wave_t_ms, e.sample_i * current_scale)
        if e.history_t:
            t = np.asarray(e.history_t, dtype=float)
            # Fixed 0–8 s viewport: shift data coordinates, not axis limits.
            t0 = max(0.0, float(t[-1]) - 8.0)
            tx = t - t0
            self.line_power.set_data(tx, list(e.history_p))
            self.line_current_trend.set_data(tx, list(e.history_i))
            self.line_cap.set_data(tx, list(e.history_cap))
        # draw_idle coalesces requests if the UI event loop is busy.
        self.canvas.draw_idle()

    def _refresh_event_log(self):
        snapshot = "\n".join(list(self.engine.event_log)[:24])
        if snapshot != self._last_log_snapshot:
            self.event_box.configure(state="normal")
            self.event_box.delete("1.0", "end")
            self.event_box.insert("1.0", snapshot)
            self.event_box.configure(state="disabled")
            self._last_log_snapshot = snapshot

    def _update_dashboard(self):
        if self.mode_tabs.index("current") == 1:
            now = float(self.root.tk.call("clock", "milliseconds")) / 1000.0
            if now - self._last_ngo_refresh >= 0.40:
                self._refresh_ngo_workspace()
                self._last_ngo_refresh = now
            return
        e = self.engine
        self.machine_state_label.config(
            text=f"MACHINE: {e.appliance.state}",
            fg=CORAL if e.fault_latched else CYAN
        )
        self.tap_status.config(text=f"CARD STATE: {e.tap_stage}")
        self._refresh_metrics()
        self._refresh_explanation()
        self._refresh_event_log()
        now = self.root.tk.call("clock", "milliseconds")
        now = float(now) / 1000.0
        if now - self._last_plot_draw >= self._plot_interval:
            self._refresh_plots()
            self._last_plot_draw = now

    def _schedule_tick(self):
        if not self.running:
            return
        self.engine.step()
        self._update_dashboard()
        interval_ms = max(10, int(round(1000.0 / self.engine.fps)))
        self._after_id = self.root.after(interval_ms, self._schedule_tick)

    def _on_close(self):
        self.running = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = WattCreditUnifiedApp(root)
    root.mainloop()
