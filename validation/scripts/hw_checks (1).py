"""
Numerical checks of the seven hardware-layer review items for the WattCredit plug.
Independent Python implementation (no Simulink). The MATLAB/Simulink add-on repeats the same checks;
use this printout as the expected result.

Values come from PCB_and_Evidence_Spec.md / BOM.csv (shunt 5 mR, divider 4x330k over 698 R, amp gain 8.2 V/V,
+-250 mV input) and from the review text (VCM 1.44 V, ADC pin window -1.3..+1.8 V). Items marked ASSUMED are
not in either source and are NOT verified against a datasheet.
"""
import math
import sys
import numpy as np

rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
W = 2 * math.pi * 50
print('=' * 78)

# ------------------------------------------------------------------ 1. common mode window
print('1. COMMON-MODE OFFSET AND ADC PIN WINDOW')
Gamp, Rsh = 8.2, 5e-3
Rtop, Rbot = 4 * 330e3, 698.0
div = Rbot / (Rtop + Rbot)
ADC_LO, ADC_HI, ADC_FS = -1.3, 1.8, 1.2       # pin window from the review; FS +-1.2 V at gain 1 ASSUMED
cases = {'current, 10 A rms (14.1 A pk)': 10 * math.sqrt(2) * Rsh,
         'current, 15 A pk (model full scale)': 15 * Rsh,
         'voltage, 230 V rms': 230 * math.sqrt(2) * div,
         'voltage, 265 V rms': 265 * math.sqrt(2) * div}
print('   divider ratio %.4e  -> 230 V rms peak %.1f mV, 265 V rms peak %.1f mV' % (div, 1e3 * 230 * math.sqrt(2) * div, 1e3 * 265 * math.sqrt(2) * div))
for att in (1.0, 0.4):
    for vcm in (1.39, 1.44):
        print('   differential attenuation %.1f, VCM %.2f V' % (att, vcm))
        for k, vin in cases.items():
            vd = Gamp * vin * att
            pmax, pmin = vcm + vd / 2, vcm - vd / 2
            ok = (pmax <= ADC_HI) and (pmin >= ADC_LO) and (vd <= ADC_FS)
            print('      %-36s diff %.3f V, pins %.3f..%.3f V, margin to +1.8 V %+.3f V, vs FS %.2f  %s' %
                  (k, vd, pmin, pmax, ADC_HI - pmax, vd / ADC_FS, 'OK' if ok else 'OUTSIDE'))
print('   max differential for pins <= 1.8 V with VCM 1.44: %.3f V  (input %.1f mV pk at gain 8.2)' % (2 * (ADC_HI - 1.44), 1e3 * 2 * (ADC_HI - 1.44) / Gamp))

# ------------------------------------------------------------------ 2. phase matching, tolerance sweep, shunt heating
print('=' * 78)
print('2. ANTI-ALIAS PHASE MATCHING, MONTE CARLO, SHUNT SELF-HEATING')
RA1 = RA2 = 1.5e3; RA3 = 2.0e3; CD = 4.7e-9; CCM = 470e-12       # ASSUMED level-interface values chosen for att = 0.4
att0 = RA3 / (RA3 + RA1 + RA2)
Rth = (RA1 + RA2) * RA3 / (RA1 + RA2 + RA3)
fc = 1 / (2 * math.pi * Rth * (CD + CCM / 2))
print('   nominal: attenuation %.3f, differential corner %.1f kHz, CCM/Cdiff = %.3f (rule: <= 0.1)' % (att0, fc / 1e3, CCM / CD))
N = 20000


def tol(nom, pct, n=N, dist='uniform'):
    if dist == 'uniform':
        return nom * (1 + rng.uniform(-pct, pct, n))
    return nom * (1 + rng.normal(0, pct / 3, n))


def channel(n=N):
    r1, r2, r3 = tol(RA1, .01, n), tol(RA2, .01, n), tol(RA3, .01, n)
    cd, c1, c2 = tol(CD, .05, n), tol(CCM, .05, n), tol(CCM, .05, n)
    att = r3 / (r3 + r1 + r2)
    rth = (r1 + r2) * r3 / (r1 + r2 + r3)
    ceff = cd + c1 * c2 / (c1 + c2)
    tau = rth * ceff
    return att, np.arctan(-W * tau)                 # gain, phase (rad)


aI, pI = channel()
aV, pV = channel()
# full chain gain spread: shunt 1 %, divider 4x330k 1 % + 698R 0.1 %, amp gain +-0.3 % each (ASSUMED), RA network
shunt = tol(1.0, .01)
dv = tol(330e3, .01) + tol(330e3, .01) + tol(330e3, .01) + tol(330e3, .01)
divr = tol(698.0, .001) / (dv + tol(698.0, .001))
gI = tol(1.0, .003) * shunt * aI / att0
gV = tol(1.0, .003) * divr / (Rbot / (Rtop + Rbot)) * aV / att0
dphi = pV - pI
print('   phase skew V vs I at 50 Hz: mean %.4f deg, 95th pct |.| %.4f deg' % (np.degrees(dphi.mean()), np.degrees(np.percentile(np.abs(dphi), 95))))
print('   active power error from phase skew alone (P = VI cos(phi)): 95th pct')
for pf in (0.28, 0.5, 0.8):
    phi = math.acos(pf)
    e = (np.cos(phi + dphi) - np.cos(phi)) / np.cos(phi)
    print('      PF %.2f: %.4f %%' % (pf, 100 * np.percentile(np.abs(e), 95)))
gp = gI * gV - 1
print('   UNCALIBRATED gain error of power (shunt, divider, amp, RA tolerances): 95th pct |.| = %.2f %%, 99th %.2f %%' % (100 * np.percentile(np.abs(gp), 95), 100 * np.percentile(np.abs(gp), 99)))
pf = 0.5; phi = math.acos(pf)
e_tot = (1 + gp) * np.cos(phi + dphi) / np.cos(phi) - 1
print('   PF 0.5 total (uncalibrated): 95th pct %.2f %%  -> within +-1 %%: %.1f %% of units' % (100 * np.percentile(np.abs(e_tot), 95), 100 * np.mean(np.abs(e_tot) < 0.01)))
print('   after gain calibration at one point the gain term is removed; residual = phase term + drift (above, and below)')
# common-mode to differential conversion from CCM / R / C mismatch: worst case over frequency, 95th percentile of units
fr = np.logspace(3, 8, 200); wv = 2 * np.pi * fr


def cm2dm(ccm):
    r1, r2 = tol(RA1, .01, 4000), tol(RA2, .01, 4000); c1, c2 = tol(ccm, .05, 4000), tol(ccm, .05, 4000)
    hp = 1 / (1 + 1j * np.outer(wv, r1 * c1)); hn = 1 / (1 + 1j * np.outer(wv, r2 * c2))
    d = np.abs(hp - hn)                                   # frequency x units
    p95 = np.percentile(d, 95, axis=1)
    return 20 * math.log10(p95.max()), fr[p95.argmax()]


for ccm in (470e-12, 4.7e-9):
    db, fpk = cm2dm(ccm)
    print('   CM->DM conversion, CCM = %s: worst %.1f dB at %.0f kHz (95th pct of units)' % ('470 pF' if ccm < 1e-9 else '4.7 nF', db, fpk / 1e3))
print('   (CCM/Cdiff = 0.1 keeps the common-mode capacitor from eating the differential bandwidth; conversion is set by RC mismatch.)')
# shunt self-heating
tcr = 50e-6
print('   shunt dissipation at 10 A: %.2f W' % (100 * Rsh))
for theta in (20, 40, 50, 80):
    dT = 0.5 * theta
    print('      thermal resistance %2d C/W -> rise %.0f C -> R change %.3f %% (power-gain error %.3f %%)  %s' %
          (theta, dT, 100 * tcr * dT, 100 * tcr * dT, 'rise < 25 C' if dT < 25 else 'rise >= 25 C'))
print('   so the 25 C limit is a thermal-resistance limit of 50 C/W; at that limit TCR costs 0.125 %.')

# fractional-sample delay (linear interpolation) used for the phase calibration
fs = 6400.0
for dphi_deg in (0.01, 0.1, 1.0):
    d = math.radians(dphi_deg) / (W / fs)
    n = np.arange(20 * 128)
    x = np.sin(W * n / fs)
    y = (1 - d) * x[1:] + d * x[:-1]
    xs = x[1:]
    ph = np.angle(np.sum(y * np.exp(-1j * W * n[1:] / fs))) - np.angle(np.sum(xs * np.exp(-1j * W * n[1:] / fs)))
    g = np.abs(np.sum(y * np.exp(-1j * W * n[1:] / fs))) / np.abs(np.sum(xs * np.exp(-1j * W * n[1:] / fs)))
    print('   fractional delay for %.2f deg: d = %.4f sample -> measured phase shift %.4f deg, gain %.6f' % (dphi_deg, d, -np.degrees(ph), g))
print('   one whole sample at 6.4 kS/s = %.3f deg at 50 Hz' % np.degrees(W / fs))

# ------------------------------------------------------------------ 3. surge and input clamp
print('=' * 78)
print('3. SURGE AND CLAMP ON THE AMPLIFIER INPUTS')
vsurge = 710.0
print('   MOV clamp 710 V pk through the REAL divider (698 R bottom): %.0f mV  (the review used 499 R: 268 mV)' % (1e3 * vsurge * div))
print('   amplifier input range +-250 mV; the clamp question is how much a BAT54S pair distorts NORMAL 230/265 V signals')
nVt = 0.0347; Is = 1e-4 * math.exp(-0.24 / nVt)         # BAT54-class fit: 0.24 V at 0.1 mA, 0.32 V at 1 mA (ASSUMED from memory)
print('   diode model: Is = %.2e A, n*Vt = %.4f V  (Vf 0.24 V @ 0.1 mA, 0.32 V @ 1 mA)' % (Is, nVt))
t = np.arange(0, 0.04, 1 / 128000.0)
Rs_in = 10.0
for nser in (0, 1, 2, 3):
    for vrms in (230, 265):
        vs = vrms * math.sqrt(2) * div * np.sin(W * t)
        Rth_v = Rbot * (Rtop) / (Rtop + Rbot) + Rs_in
        vo = np.empty_like(vs)
        for k, v in enumerate(vs):
            lo, hi = -1.0, 1.0
            for _ in range(60):                       # solve vo = v - Rth_v * Iclamp(vo)
                mid = 0.5 * (lo + hi)
                ic = 0.0 if nser == 0 else Is * (math.exp(min(mid / (nser * nVt), 40)) - math.exp(min(-mid / (nser * nVt), 40)))
                if mid - (v - Rth_v * ic) > 0: hi = mid
                else: lo = mid
            vo[k] = 0.5 * (lo + hi)
        n = len(t); mags = np.abs(np.fft.rfft(vo)); k1 = 2          # 0.04 s = exactly 2 cycles of 50 Hz
        fund = mags[k1]
        harm = math.sqrt(sum(mags[h * k1] ** 2 for h in range(2, 10)))
        gain = (np.max(vo) - np.min(vo)) / (np.max(vs) - np.min(vs))
        print('   %d diode(s) in series each way, %d V rms: gain %.4f (%.2f %% error), THD to 9th %.3f %%' % (nser, vrms, gain, 100 * (gain - 1), 100 * harm / fund))
print('   -> a single Schottky pair conducts well below the +-250 mV range; it costs gain and adds distortion on the voltage channel.')
print('   The divider already limits a 710 V surge to %.0f mV; whether that is safe is a datasheet question (input absolute maximum),' % (1e3 * vsurge * div))
print('   NOT verified here.')

# ------------------------------------------------------------------ 4. inrush with series resistor
print('=' * 78)
print('4. INRUSH INTO PS1 WITH AND WITHOUT 10 R SERIES RESISTOR')
Cin = 4.7e-6                                             # ASSUMED: PS1 front-end bulk capacitor
Rload = 24e3
for Rser, Rwire in ((0.0, 0.5), (10.0, 0.5)):
    dt = 1e-7; v = 0.0; ipk = 0.0; e_r = 0.0
    for k in range(int(0.02 / dt)):
        tt = k * dt; vin = 325 * math.sin(W * tt + math.pi / 2)         # switch on at the voltage peak
        R = Rser + Rwire + 2 * 0.05
        i = max(abs(vin) - 1.6 - v, 0) / R
        v += (i - v / Rload) / Cin * dt
        ipk = max(ipk, i); e_r += i * i * Rser * dt
    print('   series R = %4.1f ohm (mains/wiring 0.5 ohm): peak inrush %.1f A, energy in series R %.3f J (cap: 0.5CV^2 = %.3f J)' % (Rser, ipk, e_r, 0.5 * Cin * 325 ** 2))
print('   steady state: 10 R dissipates %.1f mW at 15 mA rms; X2 100 nF draws %.1f mA reactive' % (1e3 * 0.015 ** 2 * 10, 1e3 * 230 * W * 100e-9))

# ------------------------------------------------------------------ 5. PS2 minimum load
print('=' * 78)
print('5. ISOLATED DC-DC LIGHT-LOAD VOLTAGE, PRELOAD, ZENER')
Rz = 60.0                                                  # BZX84C5V1 dynamic resistance, ~60 ohm @ 5 mA max (ASSUMED from memory)
for v0 in (5.8, 6.0, 6.2):
    for label, Rout, Rpre, zen in (('no protection', 5.0, None, False), ('1k preload only', 5.0, 1e3, False), ('preload + zener + pi (2.2 R)', 5.0, 1e3, True)):
        # node voltage V: v0 - Rout*(IL+Ipre+Iz) - 2.2*(...)  (pi-filter series R is between source and the node)
        Rser = Rout + (2.2 if zen else 0.0)
        IL = 0.020
        V = 5.0
        for _ in range(200):
            Ipre = V / Rpre if Rpre else 0.0
            Iz = max((V - 5.1) / Rz + 0.005, 0.0) if (zen and V > 5.1 - 0.3) else 0.0
            if zen and V <= 5.1: Iz = 0.0
            V = 0.5 * V + 0.5 * (v0 - Rser * (IL + Ipre + Iz))
        Iz = max((V - 5.1) / Rz + 0.005, 0.0) if (zen and V > 5.1) else 0.0
        print('   no-load source %.1f V, %-28s: VDD1 = %.3f V  %s%s' % (v0, label, V, 'OK (<5.5)' if V < 5.5 else 'ABOVE 5.5 V', ('  zener %.0f mA, %.0f mW' % (1e3 * Iz, 1e3 * Iz * V)) if zen else ''))

for v0 in (5.8, 6.0, 6.2):
    need = (v0 - 5.45) / 5.0 - 0.020
    print('   no-load source %.1f V: preload alone needs %.0f mA (%.2f W at 5.4 V) to bring VDD1 to 5.45 V with Rout = 5 ohm' % (v0, 1e3 * need, need * 5.4))
print('   Rout = 5 ohm is ASSUMED (6 V at no load falling to 5 V at the 200 mA rating). It is not from a datasheet. The conclusion that a 1 k preload does')
print('   nothing depends on it; get the real load-regulation curve of the chosen module before sizing anything.')

# ------------------------------------------------------------------ 6. supercap
print('=' * 78)
print('6. SUPERCAP CS1 INRUSH LIMITER AND DIODE OR-ING')
for C in (0.1, 0.22):
    for lim in (False, True):
        dt = 1e-3; vc = 0.0; ipk = 0.0
        Rpath = 22.0 if lim else 0.5                       # 0.5 ohm = ESR + wiring when connected straight across the rail
        for k in range(int(40 / dt)):
            i = max(4.7 - vc, 0) / Rpath
            vc += i / C * dt; ipk = max(ipk, i)
        print('   CS1 = %.2f F, %s: peak charge current %.2f A %s' % (C, 'with 22 R' if lim else 'straight across', ipk, ('(PS1 limit 0.6 A: %s)' % ('ok' if ipk + 0.15 < 0.6 else 'exceeded'))))
    tau = 22 * C
    print('      charge time constant with 22 R: %.1f s  -> 99 %% in %.1f s' % (tau, 4.6 * tau))
Vstart, Vmin, Iload = 4.7, 3.3 + 0.2 + 0.3, 0.15
for C in (0.1, 0.22):
    th = C * (Vstart - Vmin) / Iload
    print('   hold-up, CS1 = %.2f F, load %.0f mA from %.1f V to %.1f V (LDO drop-out 0.2 V + SS14 0.3 V): %.2f s' % (C, 1e3 * Iload, Vstart, Vmin, th))
print('   needed for a 200 ms flush at %.0f mA: %.0f mF' % (1e3 * Iload, 1e3 * Iload * 0.2 / (Vstart - Vmin)))
print('   steady-state PS1 load: logic 150..350 mA + charging <= %.0f mA' % (1e3 * (4.7 / 22)))

# ------------------------------------------------------------------ 7. relay
print('=' * 78)
print('7. RELAY ZERO-CROSSING OPENING AND WELD DETECTION')
Ts = 1 / 6400.0
TMECH = 8e-3


class Relay:
    """line-for-line port of wc_fcn_relay.m (sample counters, current-zero-crossing state machine)"""
    def __init__(self, tmech=8e-3, tweld=50e-3, iweld=0.05):
        self.p = (6400.0, 50.0, tmech, tweld, iweld)
        self.state = 0; self.prev = 0.0; self.cmd_prev = 1; self.nwait = 0; self.nsince = 0
        self.win = np.zeros(256); self.k = 0; self.coil = 1; self.weld = 0; self.t_cmd = None; self.n = 0

    def step(self, i, cmd):
        fs_, f0_, tm, tw, iw = self.p
        spc = round(fs_ / f0_)
        self.n += 1
        self.k = self.k % spc + 1
        self.win[self.k - 1] = i * i
        irms = math.sqrt(self.win[:spc].sum() / spc)
        zc = (self.prev <= 0 < i) or (self.prev >= 0 > i)
        self.prev = i
        if cmd == 0 and self.cmd_prev == 1 and self.state == 0:
            self.state = 1; self.nsince = 0; self.t_cmd = self.n * Ts
        if cmd == 1 and self.state == 1:
            self.state = 0
        if cmd == 1 and self.cmd_prev == 0 and self.state >= 3 and self.weld == 0:
            self.coil = 1; self.state = 0
        self.cmd_prev = cmd
        if self.state >= 1:
            self.nsince += 1
        th = 0.5 / f0_
        if self.state == 1 and zc:
            self.nwait = round(((th - (tm % th)) % th) * fs_)
            self.state = 2
        if self.state == 2:
            if self.nwait <= 0:
                self.coil = 0; self.state = 3
            else:
                self.nwait -= 1
        if self.state == 3 and self.nsince >= round(tw * fs_):
            if irms >= iw: self.weld = 1
            self.state = 4
        return self.coil, self.weld


def run_relay(phi_deg, ipk, tmech_actual, t_cmd, welded=False, noise=1e-3):
    r = Relay()
    n = int(0.3 / Ts); contact = 1; t_part = None; i_part = None; open_at = None
    for k in range(n):
        t = k * Ts
        v = math.sin(W * t)
        i_true = ipk * math.sin(W * t - math.radians(phi_deg)) if contact else 0.0
        cmd = 0 if t >= t_cmd else 1
        coil, weld = r.step(i_true + rng.normal(0, noise), cmd)
        if coil == 0 and open_at is None: open_at = t + tmech_actual
        if open_at is not None and t >= open_at and contact and not welded:
            contact = 0; t_part = t; i_part = i_true
    return t_part, i_part, r.weld, r.t_cmd, open_at


res = []
for tm in (7e-3, 8e-3, 9e-3):
    ip = []
    for _ in range(40):
        t_cmd = 0.05 + rng.uniform(0, 0.02)
        tp, ia, wf, tc, oa = run_relay(60.0, 14.14, tm, t_cmd)
        ip.append(abs(ia))
    res.append((tm, np.mean(ip), np.max(ip)))
    print('   actual mech time %.0f ms (controller assumes 8 ms), PF 0.5, 10 A rms: current at contact part: mean %.2f A, max %.2f A (peak 14.1 A)' % (tm * 1e3, np.mean(ip), np.max(ip)))
rand = []
for _ in range(2000):
    ph = rng.uniform(0, 2 * math.pi)
    rand.append(abs(14.14 * math.sin(ph)))
print('   uncontrolled opening at a random instant: mean %.2f A (the improvement is the ratio)' % np.mean(rand))
ok_cmds = [run_relay(60.0, 14.14, 8e-3, 0.05 + rng.uniform(0, .02)) for _ in range(20)]
print('   command-to-part time: max %.1f ms (weld check window is 50 ms)' % (1e3 * max(tp - 0 for tp, *_ in [(a[0] - a[3],) for a in ok_cmds])))
print('   weld flag, healthy relay: %s' % sorted(set(a[2] for a in ok_cmds)))
wl = [run_relay(60.0, 14.14, 8e-3, 0.05 + rng.uniform(0, .02), welded=True) for _ in range(10)]
print('   weld flag, welded contacts (current keeps flowing): %s' % sorted(set(a[2] for a in wl)))
print('   note on the review text: it times the coil off 12 ms after a GRID zero crossing. For an inductive load the CURRENT zero lags the')
print('   voltage zero by phi/w = %.1f ms at PF 0.5, so the controller above keys on the current zero crossing instead.' % (1e3 * math.radians(60) / W))
print('=' * 78)
print('Items not simulable: creepage/clearance slot, Kelvin routing, star ground, copper-pour area for R1 (PCB-layout rules, see checklist).')
