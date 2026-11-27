

% ---- grid and sampling
Vnom   = 230;            % V rms
f0     = 50;             % Hz
fs     = 6400;           % Hz, 128 samples per cycle (spec)
Ts     = 1/fs;           % control sample time
Tp     = Ts/4;           % power-solver step (4 sub-steps per control sample)
NC     = 50;             % cycles per 1 s frame

% ---- measurement chain (plug front end)
Rsh    = 5e-3;           % ohm shunt in neutral leg
Gi     = 1/Rsh;          % V->A scaling after the isolated amplifier
adcBits = 18;  IfsPk = 15;  VfsPk = 400;      % full-scale, as in wattcredit_verify
noiseI = 1e-3;  noiseV = 0.05;                % rms, assumed

% ---- motor equivalent circuit (series R-L at 230 V), derived from P and PF
derive = @(P,PF) struct('P',P,'PF',PF,'I',P/(Vnom*PF), ...
    'R',(Vnom/(P/(Vnom*PF)))*PF, ...
    'L',(Vnom/(P/(Vnom*PF)))*sqrt(1-PF^2)/(2*pi*f0));
motorIdle = derive(38, 0.28);
motorWork = derive(220, 0.80);
% work-state load fluctuation: a small parallel resistor is toggled at fRip
fRip   = 1.8;                         % Hz, grinding-load fluctuation
Rrip   = 1800;                        % ohm, toggled in parallel with the work motor to give ~4 % per-cycle RMS ripple (tune in V2)

% ---- non-motor loads
heaterP = 1000;   Rheater = Vnom^2/heaterP;
spoofHeaterP = 190 - motorIdle.P;     % resistive add-on that makes idle motor + heater look loaded
Rspoof  = Vnom^2/spoofHeaterP;
ledC = 220e-6;    ledR = 2000;  ledRs = 20;   % diode-bridge + series R + C || R stand-in for an LED driver / charger (same values as pycheck)

% ---- evidence rule (enrolment is computed by run_wattcredit_check from the model itself)
rule.pGateFrac   = 0.6;               % power gate, 60 % of the way idle -> work
rule.ripGateFrac = 0.4;               % ripple gate, 40 % of enrolled loaded ripple
rule.tauMult     = 1.3;               % distance threshold multiplier on enrolment spread
rule.iOffA       = 0.03;              % below this Irms the plug says OFF

% ---- protection (detect-only in v1: raises a flag, never cuts the load)
prot.Vlo = 180;  prot.Vhi = 260;      % V rms
prot.Imax = 10;                       % A rms, prototype rating
prot.debounceFrames = 3;

% ---- scenario: one state per 10 s segment (1 s frames, settles after first frame of each)
scenario.names = {'OFF','IDLE','WORK','HEATER','LED','SPOOF','WORK'};
scenario.expect = {'OFF','IDLE','WORK','OTHER','OTHER','NOTWORK','WORK'};   % SPOOF must never be credited as WORK
scenario.codes = [0 1 2 3 4 5 2];     % 0 OFF, 1 IDLE, 2 WORK, 3 HEATER, 4 LED, 5 SPOOF
scenario.segT  = 10;
StopTime = scenario.segT*numel(scenario.names);

% ---- values the model reads from the base workspace
Vpk   = Vnom*sqrt(2);                 % source peak; run_wattcredit_check overrides it for the sag/swell runs
lsbI  = 2*IfsPk/2^adcBits;            % ADC step, A
lsbV  = 2*VfsPk/2^adcBits;            % ADC step, V
pvec  = [fs f0 NC Vnom prot.Vlo prot.Vhi prot.Imax prot.debounceFrames];   % input p of wc_fcn_features
codes = scenario.codes;               % input of wc_fcn_scenario (run_wattcredit_check swaps these per run)
segT  = scenario.segT;
E     = [zeros(1,4) ones(1,4) zeros(1,4) ones(1,4) 0 0 1 0 0 rule.iOffA];   % placeholder enrolment; replaced after the enrolment run
fprintf('motor idle: R=%.1f ohm L=%.3f H (I=%.2f A);  motor work: R=%.1f ohm L=%.3f H (I=%.2f A)\n', ...
    motorIdle.R, motorIdle.L, motorIdle.I, motorWork.R, motorWork.L, motorWork.I);
