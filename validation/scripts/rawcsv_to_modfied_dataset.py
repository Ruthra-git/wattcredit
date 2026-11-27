import csv
from datetime import datetime

INPUT_FILE = "raw_esp32_nilm.csv"          # Your downloaded dataset
OUTPUT_FILE = "wattcredit_validated.csv"   # Output ready for the Digital Twin
PRODUCTIVE_CUTOFF_W = 300.0
CREDIT_RATE_INR_KWH = 185.0

rows_out = []
productive_powers = []
productive_pfs = []
active_days = set()
tamper_count = 0

with open(INPUT_FILE, mode="r", newline="", encoding="utf-8-sig") as f_in:
    reader = csv.DictReader(f_in)
    for row in reader:
        # 1. Map external column names to WattCredit schema
        # Adjust keys on the right if your source CSV uses 'Time', 'V', 'I', etc.
        raw_ts = row.get("time") or row.get("timestamp") or "2026-10-01T09:00:00"
        v = float(row.get("vrms") or row.get("voltage_v") or 230.0)
        i = float(row.get("irms") or row.get("current_a") or 0.0)
        pf = max(0.0, min(1.0, float(row.get("power_factor") or row.get("pf") or 0.0)))
        tamper = int(float(row.get("tamper") or 0))

        # 2. Ensure ISO timestamp format (YYYY-MM-DDTHH:MM:SS)
        ts_clean = raw_ts.strip().replace(" ", "T")[:19]

        rows_out.append([ts_clean, round(v, 2), round(i, 3), round(pf, 3), tamper])

        # 3. Compute ground-truth validation metrics (matches load_shift_csv & compute_credit_underwriting)
        active_p = v * i * pf
        tamper_count += tamper
        if active_p >= PRODUCTIVE_CUTOFF_W:
            productive_powers.append(active_p)
            productive_pfs.append(pf)
            if len(ts_clean) >= 10:
                active_days.add(ts_clean[:10])

# Write formatted CSV for WattCredit Digital Twin
with open(OUTPUT_FILE, mode="w", newline="", encoding="utf-8") as f_out:
    writer = csv.writer(f_out)
    writer.writerow(["timestamp", "voltage_v", "current_a", "power_factor", "tamper"])
    writer.writerows(rows_out)

# Print exact reference values to match against the NGO Credit Twin tab
days_30d = max(1, min(30, len(active_days))) if productive_powers else 1
hours_per_day = min(14.0, len(productive_powers) / days_30d) if productive_powers else 0.0
avg_prod_w = sum(productive_powers) / len(productive_powers) if productive_powers else 0.0
est_30d_kwh = (avg_prod_w / 1000.0) * hours_per_day * days_30d

print(f"Saved {len(rows_out)} rows to '{OUTPUT_FILE}'")
print("-" * 52)
print(f"Expected Productive Rows (>= {PRODUCTIVE_CUTOFF_W:.0f} W) : {len(productive_powers)}")
print(f"Expected Active Days (30d)           : {days_30d}")
print(f"Expected Productive Hours/Day        : {hours_per_day:.1f}")
print(f"Expected Mean Productive Power       : {avg_prod_w:.0f} W")
print(f"Expected 30d Productive Energy       : {est_30d_kwh:.1f} kWh")
print(f"Expected Tamper Events               : {tamper_count}")