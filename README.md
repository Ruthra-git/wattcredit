# WattCredit — Isolated Mains Energy Monitor & Offline Credit Underwriting System

**Converting Verified Commercial Appliance Utilization into Collateral-Free Working Capital for Rural Women-Led MSMEs**



---

## Overview

**WattCredit** bridges the working-capital credit gap for rural women-led micro-enterprises (tailoring/overlock units, commercial wet-grinders, and mini-bakeries) that lack formal GST filings, bank cash-flow histories, or continuous workshop internet connectivity.

The system operates as an end-to-end deterministic trust pipeline:
1. **Isolated Edge Metrology (`Rev B0`):** An inline 230 V / 50 Hz pass-through smart plug samples line voltage and load current simultaneously at **4 kSPS** through reinforced galvanic isolation, isolating productive machinery (`≥ 300 W`, inductive PF `0.75–1.00`) from domestic appliances (`< 300 W`).
2. **Blackout & Tamper Persistence:** Every shift record is chained via `SHA-256` and signed by an `ATECC608B` hardware secure element into `W25Q64JV` SPI NOR flash, protected during sudden grid blackouts by a `0.1 F` supercapacitor hold-up network (`1,187.5 ms` persistence past `4.55 V` `PWR_FAIL`).
3. **Zero-Internet BLE Tap Sync:** A visiting Bank Sakhi or NGO field officer taps their Android device to execute an offline mutual-auth handshake (`0xFF02`) and burst-sync signed shift blocks (`0xFF01`) in `< 2.0 seconds` without rural cellular connectivity.
4. **Deterministic Underwriting:** Verified 30-day productive energy (`kWh`) is mapped through a weighted 100-point scoring model to generate an RBI-compliant working-capital credit limit (`₹5,000–₹50,000`) with zero fees charged to the borrower.

> **Engineering Scope Notice:** The Rev B0 PCB layout is DRC-clean (`0` errors) in KiCad 9 and ready for fabrication. All electrical metrology, fault trip timing, brownout survival, BLE burst state machines, and underwriting equations in this repository have been validated via **MATLAB/Simulink** and **Python Digital Twins** against empirical ESP32 NILM datasets and 30-day synthetic benchmarks.

---

## Ecosystem Repositories

| Repository | Scope & Contents | Role |
| :--- | :--- | :--- |
| **`wattcredit-hardware-and-twin`** *(This Repo)* | KiCad 9 4-layer PCB files, MATLAB/Simulink front-end model, Python digital twins, empirical NILM datasets, and validation reports. | Lead Hardware, Simulation & Validation Author |
| **[`wattcredit-field-app`](https://github.com/<teammate-username>/<field-app-repo>)** *(Separate Repo)* | Offline-first Flutter Android app (`SQLCipher` outbox, BLE GATT `0xFF01`/`0xFF02` client, Tamil voice sales logging) & FastAPI/PostgreSQL backend. | Collaborator (Hardware/BLE Protocol & Underwriting Integration) |

---

## 1. Repository Architecture

```text
wattcredit-hardware-and-twin/
├── README.md                                      # Master documentation and validation summary
├── LICENSE                                        # MIT License
│
├── hardware/                                      # KiCad 9 PCB & manufacturing package( with ERC and DRC files compresses as ZIP
)
│  
├── simulation/                                    # MATLAB/Simulink & Python digital twins
│   ├── simulink/
│   │   └── build_wattcredit_full_pcb.m  # Programmatic Simulink Rev B0 front-end & brownout model
         |____hw and sw models serving fast run and slow run modelled in simulink 
    |____ generic
        |____ electronic switching model in simulink with run notes          
│   └── python_twins/
│       ├
│       ├── wattcredit_unified_twin.py             # Unified Appliance + Rev B0 Meter + NGO Underwriting twin
│       └── wattcredit_machine_animation_twin.py   # Electromechanical load animation & telemetry replay twin
│
├── validation/                                    # Empirical NILM datasets, converter scripts & benchmarks
│   ├── datasets/
│   │   ├── raw_esp32_nilm.csv                     # 14,811-row empirical capture (ESP32 + ATM90E36A NILM)
│   │   ├── wattcredit_validated.csv               # 5-column transformed telemetry stream (14,811 rows)
│   │   └── wattcredit_sample_30d.csv              # 360-row 30-day hourly underwriting benchmark
│   └── scripts/
│       └── convert_and_validate_csv.py            # Schema transformer & ground-truth parity calculator
         |____power measurement and port correction python files for validation of electrical design
│
└── docs/                                          # Formal engineering reports & protocol specifications
    ├── WattCredit_Consolidated_Twin_Validation_Report.pdf
    ├── WattCredit_Simulink_Technical_Documentation.pdf
    └── market study of wattcredit

---

## 2. Quick Start: Running the Digital Twins

### A. Python Digital Twins (`Unified Twin` & `Machine Animation Twin`)

1. **Clone the repository and install dependencies:**
   ```bash
   git clone https://github.com/<your-username>/wattcredit-hardware-and-twin.git
   cd wattcredit-hardware-and-twin/simulation/python_twins
   pip install -r requirements.txt
   ```

2. **Launch the Unified Digital Twin:**
   ```bash
   python wattcredit_unified_twin.py
   ```
   * **Electrical Twin Tab:** Start/stop simulated appliances (*Tailoring & Overlock Machine*, *Commercial Wet-Grinder*, *Mini Bakery Oven*), inject `265 V` swells, `12.5 A` overloads, grid blackouts, or `SW1` tamper events, and inspect real-time `4 kSPS` waveforms and `0.1 F` supercapacitor hold-up curves.
   * **NGO Credit Twin Tab:** Click **LOAD SHIFT CSV** and select `../../validation/datasets/wattcredit_sample_30d.csv` (or `wattcredit_validated.csv`), then click **TAP NGO OFFICER BLE CARD** to simulate the `0xFF02` mutual-auth handshake, `0xFF01` flash burst sync, and weighted credit score computation.

3. **Re-verify Dataset Transformation & Parity:**
   ```bash
   cd ../../validation/scripts
   python convert_and_validate_csv.py
   ```

### B. MATLAB / Simulink Behavioral Model

1. Open MATLAB (R2022b or later with Simulink installed).
2. Navigate to `simulation/simulink/` and run:
   ```matlab
   build_wattcredit_full_pcb
   ```
3. The script programmatically constructs and executes the Rev B0 signal chain (`230 V` mains $\rightarrow$ `499 Ω` divider / `5 mΩ` Kelvin shunt $\rightarrow$ dual `AMC1301` $\rightarrow$ `ADS131M02` `4 kSPS` ADC $\rightarrow$ `10 A` relay trip & `0.1 F` supercapacitor brownout hold-up).

---

## 3. Empirical Validation Summary

We validated the ingestion pipeline, active-power integration, safe operating boundaries (`175 V–265 V`, `≤ 10.0 A`), and underwriting logic across three datasets documented in [`docs/WattCredit_Consolidated_Twin_Validation_Report.pdf`](docs/WattCredit_Consolidated_Twin_Validation_Report.pdf):

| Parameter | `raw_esp32_nilm.csv` | `wattcredit_validated.csv` | `wattcredit_sample_30d.csv` |
| :--- | :--- | :--- | :--- |
| **Target Twin** | `wattcredit_unified_twin` (Baseline) | `wattcredit_machine_animation_twin` | `wattcredit_unified_twin` (Benchmark) |
| **Data Source** | ESP32 + ATM90E36A NILM Repo | Transformed ESP32 NILM Capture | Unified Twin 30-Day Generator |
| **Dimensions** | `14,811 rows × 38 columns` | `14,811 rows × 5 columns` | `360 rows × 5 columns` |
| **Duration** | `8.00 hours` (`124 s` to `28,923 s`) | `8.00 hours` (`124 s` to `28,923 s`) | `30 days` (`Oct 1–30, 2026`, excl. Sundays) |
| **Voltage Range** | `224.90 V – 244.46 V` (live) | `224.90 V – 244.46 V` (live) | `221.51 V – 241.17 V` |
| **Peak Current** | `3.520 A` (mean: `0.274 A`) | `3.520 A` (mean: `0.274 A`) | `3.909 A` (mean: `1.983 A`) |
| **Productive Rows (`≥300 W`)** | `1,192 rows` (`p_active`) | `1,190 rows` (`V × I × PF ≥ 300 W`) | `208 rows` (`V × I × PF ≥ 300 W`) |
| **Mean Productive Power** | `798.25 W` | `798.01 W` (`0.35 W` mean diff) | `660.99 W` (mean PF: `0.870`) |
| **Underwriting Output** | Source reference | Score `66/100` (`₹5,000` limit, `+1.0%` rebate) | Score `100/100` (`₹25,500` limit, `+2.0%` rebate) |

---

## 4. Hardware & Underwriting Specifications

* **Hardware & Protection (`Rev B0`):**
  * **Sensing Front-End:** `5 mΩ` 4-wire Kelvin shunt (`R1`) + `1.32 MΩ : 499 Ω` resistive divider (`R2–R6`) feeding dual reinforced isolated amplifiers (`7,070 Vpk`) and a `4 kSPS` simultaneous-sampling ADC (`±1.20 V` ref; `1.161 V` peak at `265 V` swell).
  * **Brownout Hold-Up:** `0.1 F`, `5.5 V` supercapacitor (`CS1`) monitored by `U9` (`4.55 V` `PWR_FAIL`) sheds the `16 A` safety relay (`K1`) at `180 ms`, providing **1,187.5 ms** of logic survival down to the `3.60 V` LDO dropout threshold to commit the final signed flash block.
  * **PCB Layout:** 4-layer `125 × 100 mm` FR-4 board in KiCad 9 with `≥ 6 mm` HV-to-LV creepage/clearance, `2.5 mm` traces on `2 oz` outer copper for the `10 A` path, split ground/3V3 planes, and `0` DRC errors.
* **Underwriting & RBI Alignment:**
  * **100-Point Weighted Score:** `35%` Operational Consistency (`26-day` norm) + `35%` Productive Utilization (`6 hr/day` norm at `≥ 300 W`) + `20%` Hardware Tamper Integrity (`-45 pts` per `SW1` breach) + `10%` Electrical Power Quality (`0.75–1.00 PF`).
  * **Regulatory Guardrails:** Designed around RBI Digital Lending Directions 2025 (RE-paid LSP model with `₹0` borrower fee, India data residency, revocable digital consent, and automated Key Facts Statements) and RBI Priority Sector Lending / Microfinance norms (`50%` household FOIR cap).

---

## License

This project is released under the *APACHE LICENSE** 