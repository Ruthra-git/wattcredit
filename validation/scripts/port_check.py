"""
Line-for-line Python port of wc_fcn_features.m and wc_fcn_classify.m, driven by waveforms derived from the
CIRCUIT values in wc_params.m (R-L motor phasors, diode-bridge ODE, ripple toggle), not by the earlier
synthetic generators. This tests the control LOGIC; it does not run Simulink and cannot test the .slx.
"""
import math, sys
import numpy as np

rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
fs, f0, NC = 6400, 50.0, 50
Ts = 1 / fs
spc = round(fs / f0)
N = spc * NC
VNOM = 230.0
W = 2 * math.pi * f0


def derive(P, PF):
    I = P / (VNOM * PF)
    Z = VNOM / I
    return Z * PF, Z * math.sqrt(1 - PF ** 2) / W      # R, L


R_I, L_I = derive(38, 0.28)
R_W, L_W = derive(220, 0.80)
R_HEAT = VNOM ** 2 / 1000
R_SPOOF = VNOM ** 2 / (190 - 38)
R_RIP = 1800.0
F_RIP = 1.8
LED_C, LED_R, LED_RS = 220e-6, 2000.0, 20.0
T = np.arange(N) * Ts


def rl_current(vrms, R, L, ph=0.0):
    Z = complex(R, W * L)
    return math.sqrt(2) * vrms / abs(Z) * np.sin(W * T - np.angle(Z) + ph)


_vc = [0.0]


def led_current(v):
    vc = _vc[0]
    sub = 4
    dt = Ts / sub
    out = np.empty(N)
    for k in range(N):
        a = v[k]
        ia = 0.0
        for s in range(sub):
            vv = a                      # source held over the sub-step (v is dense enough at fs*4 for a check)
            iin = max(abs(vv) - vc, 0.0) / LED_RS
            vc += (iin - vc / LED_R) / LED_C * dt
            ia = iin * (1 if vv >= 0 else -1)
        out[k] = ia
    _vc[0] = vc
    return out


def make_frame(kind, vrms, t0):
    v = math.sqrt(2) * vrms * np.sin(W * T)
    tt = t0 + T
    tog = (np.floor(tt * F_RIP * 2) % 2 == 0).astype(float)          # square wave at F_RIP
    if kind == 'OFF':
        i = np.zeros(N)
    elif kind == 'IDLE':
        i = rl_current(vrms, R_I, L_I)
    elif kind == 'WORK':
        i = rl_current(vrms, R_W, L_W) + tog * v / R_RIP
    elif kind == 'HEATER':
        i = v / R_HEAT
    elif kind == 'LED':
        i = led_current(v)
    elif kind == 'SPOOF':
        i = rl_current(vrms, R_I, L_I) + v / R_SPOOF                  # idle motor + steady heater
    elif kind == 'SPOOFMOD':
        i = rl_current(vrms, R_I, L_I) + (1 + 0.5 * tog) * v / R_SPOOF * 0.7   # slowly modulated heater
    else:
        raise ValueError(kind)
    return v, i


def adc(v, i):
    lsb_i = 2 * 15 / 2 ** 18
    lsb_v = 2 * 400 / 2 ** 18
    return (np.round((v + rng.normal(0, 0.05, N)) / lsb_v) * lsb_v,
            np.round((i + rng.normal(0, 1e-3, N)) / lsb_i) * lsb_i)


class Features:                      # port of wc_fcn_features.m
    def __init__(self, p):
        self.p = p
        self.reset_all()

    def reset_all(self):
        self.n = 0; self.cyc = 0
        self.sv2 = self.si2 = self.svi = 0.0
        self.c = np.zeros(6); self.cs2 = 0.0
        self.cycR = np.zeros(200); self.bad = 0; self.trip = 0
        self.last = np.zeros(7)

    def step(self, v, i):
        p = self.p
        th = 2 * math.pi * (self.n % spc) / spc
        self.sv2 += v * v; self.si2 += i * i; self.svi += v * i; self.cs2 += i * i
        self.c += i * np.array([math.cos(th), math.sin(th), math.cos(3 * th), math.sin(3 * th), math.cos(5 * th), math.sin(5 * th)])
        self.n += 1
        strobe = 0
        if self.n % spc == 0:
            self.cyc += 1
            self.cycR[self.cyc - 1] = math.sqrt(self.cs2 / spc); self.cs2 = 0.0
        if self.n >= N:
            vrms = math.sqrt(self.sv2 / N); irms = math.sqrt(self.si2 / N); P = self.svi / N
            pf = P / (vrms * irms) if vrms * irms > 1e-9 else 0.0
            a1 = 2 / N * math.hypot(self.c[0], self.c[1]); a3 = 2 / N * math.hypot(self.c[2], self.c[3]); a5 = 2 / N * math.hypot(self.c[4], self.c[5])
            h3, h5 = (a3 / a1, a5 / a1) if a1 > 1e-4 else (0.0, 0.0)
            r = self.cycR[:self.cyc]; mr = r.mean()
            rip = math.sqrt(np.mean((r - mr) ** 2)) / mr if mr > 1e-4 else 0.0
            pn = P * (p['Vnom'] / max(vrms, 1)) ** 2
            self.last = np.array([pf, h3, h5, rip, pn, irms, vrms])
            badf = vrms < p['Vlo'] or vrms > p['Vhi'] or irms > p['Imax']
            if badf: self.bad += 1
            else: self.bad = 0; self.trip = 0
            if self.bad >= p['deb']: self.trip = 1
            strobe = 1
            self.n = 0; self.cyc = 0; self.sv2 = self.si2 = self.svi = 0.0; self.c[:] = 0; self.cs2 = 0.0
        return self.last.copy(), strobe, self.trip


def classify(feat, E):               # port of wc_fcn_classify.m (strobe assumed 1)
    x = feat[:4]
    dI = math.sqrt(np.mean(((x - E['muI']) / E['sdI']) ** 2))
    dW = math.sqrt(np.mean(((x - E['muW']) / E['sdW']) ** 2))
    if feat[5] < E['iOff']: return 0
    if min(dI, dW) > E['tau']: return 3
    if dW < dI and feat[4] >= E['pgate'] and feat[3] >= E['ripgate']: return 2
    return 1


PRM = dict(Vnom=230.0, Vlo=180.0, Vhi=260.0, Imax=10.0, deb=3)
fe = Features(PRM)
clock = [0.0]


def run_frames(kind, nfr, vr=None):
    out = []
    for _ in range(nfr):
        vrms = vr if vr else float(np.clip(rng.normal(228, 6), 205, 245))
        v, i = make_frame(kind, vrms, clock[0]); clock[0] += 1.0
        vm, im = adc(v, i)
        for k in range(N):
            f, s, tr = fe.step(vm[k], im[k])
        out.append((f, tr))
    return out


# ---- enrolment from the model itself (same recipe as run_wattcredit_check.m)
def stats(fr):
    X = np.array([f[:4] for f, _ in fr]); pn = np.mean([f[4] for f, _ in fr])
    mu = X.mean(0); sd = np.maximum(X.std(0, ddof=1), 0.025 * np.abs(mu) + 1e-4)
    return mu, sd, pn


print('enrolment: 20 idle + 20 work frames')
fi = run_frames('IDLE', 20); fw = run_frames('WORK', 20)
muI, sdI, pnI = stats(fi); muW, sdW, pnW = stats(fw)
E = dict(muI=muI, sdI=sdI, muW=muW, sdW=sdW, pnI=pnI, pnW=pnW, iOff=0.03)
held = run_frames('IDLE', 10) + run_frames('WORK', 10)
d = sorted(min(math.sqrt(np.mean(((f[:4] - muI) / sdI) ** 2)), math.sqrt(np.mean(((f[:4] - muW) / sdW) ** 2))) for f, _ in held)
E['tau'] = 1.3 * d[min(len(d) - 1, math.ceil(0.99 * len(d)) - 1)]
E['pgate'] = pnI + 0.6 * (pnW - pnI)
E['ripgate'] = 0.4 * muW[3]
print(f"  idle  PF={muI[0]:.3f} H3={muI[1]:.3f} rip={muI[3]*100:.2f}% Pn={pnI:.1f} W")
print(f"  work  PF={muW[0]:.3f} H3={muW[1]:.3f} rip={muW[3]*100:.2f}% Pn={pnW:.1f} W")
print(f"  tau={E['tau']:.2f}  pgate={E['pgate']:.1f} W  ripgate={E['ripgate']*100:.2f}%")

NAMES = {0: 'OFF', 1: 'IDLE', 2: 'WORK', 3: 'OTHER'}
EXPECT = [('OFF', {'OFF'}), ('IDLE', {'IDLE'}), ('WORK', {'WORK'}), ('HEATER', {'OTHER'}), ('LED', {'OTHER'}),
          ('SPOOF', {'OFF', 'IDLE', 'OTHER'}), ('WORK', {'WORK'})]
print('\nscenario, 8 frames per state, first frame of each state skipped (settling)')
ok_all = True
for kind, allowed in EXPECT:
    fr = run_frames(kind, 8)[1:]
    labs = [NAMES[classify(f, E)] for f, _ in fr]
    ok = all(l in allowed for l in labs)
    ok_all &= ok
    print(f"  {kind:7s} -> {sorted(set(labs))}  expected in {sorted(allowed)}  {'PASS' if ok else 'FAIL'}")
fr = run_frames('SPOOFMOD', 8)[1:]
labs = [NAMES[classify(f, E)] for f, _ in fr]
print(f"  SPOOFMOD (known weak spot, reported not asserted) -> {labs}")

print('\nprotection (debounce 3 frames)')
for vr, name in ((150.0, 'sag 150 V'), (275.0, 'swell 275 V')):
    fe.reset_all()
    tr = [t for _, t in run_frames('HEATER', 4, vr=vr)]
    print(f"  {name}: trip per frame = {tr}  {'PASS' if tr == [0, 0, 1, 1] else 'CHECK'}")
fe.reset_all()
tr = [t for _, t in run_frames('IDLE', 3, vr=230.0)]
print(f"  nominal: trip per frame = {tr}  {'PASS' if sum(tr) == 0 else 'FAIL'}")
print('\nOVERALL', 'PASS' if ok_all else 'FAIL')
