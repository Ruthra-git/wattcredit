here = fileparts(mfilename('fullpath'));
wc_params;  wc_hw_params;
fast = 'wattcredit_hw_fast';  slow = 'wattcredit_hw_slow';
if ~exist(fullfile(here, [fast '.slx']), 'file') || ~exist(fullfile(here, [slow '.slx']), 'file'), build_wattcredit_hw; end
load_system(fullfile(here, fast));  load_system(fullfile(here, slow));
R = {};
W0 = 2*pi*f0;


assignin('base', 'hw', hw);
so = sim(fast, 'ReturnWorkspaceOutputs', 'on');
for ch = 'IV'
    A = so.get(['o_cm' ch]);                          % columns: OUTP OUTN AINP AINN
    rawHi = max(max(A(:,1:2)));   rawLo = min(min(A(:,1:2)));
    cHi = max(max(A(:,3:4)));     cLo = min(min(A(:,3:4)));
    dif = max(abs(A(:,3) - A(:,4)));
    inside = cHi <= hw.cm.pinHi && cLo >= hw.cm.pinLo && dif <= hw.cm.adcFS;
    R = addRow(R, sprintf('1  %s channel, with level interface (att %.1f)', ch, hw.att), ternary(inside, 'PASS', 'FAIL'), ...
        sprintf('pins %.3f..%.3f V (window %.1f..%.1f), differential %.3f V (FS %.1f)', cLo, cHi, hw.cm.pinLo, hw.cm.pinHi, dif, hw.cm.adcFS));
    inRaw = rawHi <= hw.cm.pinHi && rawLo >= hw.cm.pinLo && max(abs(A(:,1)-A(:,2))) <= hw.cm.adcFS;
    R = addRow(R, sprintf('1  %s channel, amplifier straight into the ADC', ch), ternary(inRaw, 'INFO', 'FINDING'), ...
        sprintf('pins %.3f..%.3f V, differential %.3f V: %s', rawLo, rawHi, max(abs(A(:,1)-A(:,2))), ternary(inRaw, 'inside', 'OUTSIDE the ADC range, needs the RA attenuation')));
end


rng(5);
N = hw.mc.N;  tolv = @(nom, pct) nom .* (1 + (2*rand(N,1) - 1)*pct);
[aI, pI] = rcChannel(hw, tolv);   [aV, pV] = rcChannel(hw, tolv);
att0 = hw.att;
shunt = tolv(1, hw.mc.tolR);
dv = tolv(330e3, hw.mc.tolR) + tolv(330e3, hw.mc.tolR) + tolv(330e3, hw.mc.tolR) + tolv(330e3, hw.mc.tolR);
divr = tolv(698, hw.mc.tolRdiv) ./ (dv + tolv(698, hw.mc.tolRdiv));
gI = tolv(1, hw.mc.tolAmp) .* shunt .* aI / att0;
gV = tolv(1, hw.mc.tolAmp) .* divr / hw.div .* aV / att0;
dphi = pV - pI;
pfT = 0.5;  phi = acos(pfT);
ePh = (cos(phi + dphi) - cos(phi)) / cos(phi);
gp  = gI .* gV - 1;
eTot = (1 + gp) .* cos(phi + dphi) / cos(phi) - 1;
tcrErr = hw.mc.tcr * 25;                              % 25 degC rise, the limit in the review
R = addRow(R, '2  phase skew V vs I at 50 Hz', 'INFO', sprintf('95th pct %.4f deg -> power error at PF 0.5: %.4f %%', rad2degLocal(prctileLocal(abs(dphi), 95)), 100*prctileLocal(abs(ePh), 95)));
R = addRow(R, '2  uncalibrated power error, PF 0.5', 'FINDING', sprintf('95th pct %.2f %%; %.0f %% of units inside +-1 %% before calibration', 100*prctileLocal(abs(eTot), 95), 100*mean(abs(eTot) < 0.01)));
resid = prctileLocal(abs(ePh), 95) + tcrErr;
R = addRow(R, '2  after gain calibration (phase term + 25 C shunt rise)', ternary(resid < 0.01, 'PASS', 'FAIL'), sprintf('%.3f %% (< 1 %%)', 100*resid));
R = addRow(R, '2  shunt thermal limit', 'FINDING', sprintf('0.5 W at 10 A: a 25 C rise needs thermal resistance <= %.0f C/W (R change %.3f %%)', 25/0.5, 100*tcrErr));
D = so.get('o_fd');   n0 = 15*128;   tt = (0:n0-1)' * Ts;
dft = @(x) sum(x(1:n0) .* exp(-1j*W0*tt));
shiftDeg = rad2degLocal(angle(dft(D(:,1))) - angle(dft(D(:,2))));
wantDeg = 360*f0*hw.fd.d/fs;
R = addRow(R, '2  fractional-sample delay block', ternary(abs(shiftDeg - wantDeg) < 0.005, 'PASS', 'FAIL'), sprintf('phase shift %.4f deg, expected %.4f deg (d = %.4f sample)', shiftDeg, wantDeg, hw.fd.d));


t = (0:1/128000:0.04 - 1/128000)';
RthV = Rbot*Rtop/(Rtop + Rbot) + hw.clamp.Rs;
for nser = [1 3]
    for vr = [230 265]
        vs = vr*sqrt(2)*hw.div*sin(W0*t);
        lo = -ones(size(vs));  hi = ones(size(vs));
        for it = 1:60
            mid = 0.5*(lo + hi);
            ic = hw.clamp.Is*(exp(min(mid/(nser*hw.clamp.nVt), 40)) - exp(min(-mid/(nser*hw.clamp.nVt), 40)));
            up = (mid - (vs - RthV*ic)) > 0;
            hi(up) = mid(up);  lo(~up) = mid(~up);
        end
        vo = 0.5*(lo + hi);
        M = abs(fft(vo));  k1 = 3;                       % 0.04 s = 2 cycles: fundamental in bin 3 (index = cycles + 1)
        harm = sqrt(sum(M(2*(2:9) + 1).^2));
        gain = (max(vo) - min(vo))/(max(vs) - min(vs));
        st = 'FINDING';  if nser == 3, st = ternary(abs(gain - 1) < 0.005, 'PASS', 'FAIL'); end
        R = addRow(R, sprintf('3  %d Schottky in series each way, %d V rms', nser, vr), st, sprintf('gain %.4f (%.2f %%), THD to 9th %.3f %%', gain, 100*(gain - 1), 100*harm/M(k1)));
    end
end
R = addRow(R, '3  710 V MOV clamp through the BOM divider', 'FINDING', sprintf('%.0f mV at the amplifier (the review assumed 499 R: 268 mV); input absolute maximum NOT verified', 1e3*hw.clamp.vsurge*hw.div));


pk = zeros(1, 2);
for k = 1:2
    hw.inrush.Rser = [0 10]; hw.inrush.Rser = hw.inrush.Rser(k);
    assignin('base', 'hw', hw);
    so4 = sim(fast, 'ReturnWorkspaceOutputs', 'on');
    pk(k) = max(abs(so4.get('o_inrush')));
end
hw.inrush.Rser = 10;  assignin('base', 'hw', hw);
R = addRow(R, '4  inrush, no series R / 10 R', ternary(pk(2) < 40 && pk(1) > 10*pk(2), 'PASS', 'FAIL'), sprintf('peak %.0f A / %.1f A', pk(1), pk(2)));


for v0 = hw.ps2.v0
    out = '';
    for variant = 1:3
        Rpre = [Inf 1e3 1e3];   zen = [0 0 1];   Rser = hw.ps2.Rout + zen(variant)*hw.ps2.Rpi;
        V = 5;
        for it = 1:300
            Ipre = V/Rpre(variant);
            Iz = 0;  if zen(variant) && V > 5.1, Iz = (V - 5.1)/hw.ps2.Rz + 0.005; end
            V = 0.5*V + 0.5*(v0 - Rser*(hw.ps2.IL + Ipre + Iz));
        end
        labels = {'bare', '1k preload', 'preload+zener+pi'};
        out = [out sprintf('%s %.2f V; ', labels{variant}, V)]; 
    end
    R = addRow(R, sprintf('5  no-load source %.1f V -> VDD1', v0), 'FINDING', [out '(limit 5.5 V; Rout and zener rz assumed)']);
end


so6 = sim(slow, 'ReturnWorkspaceOutputs', 'on');
S = so6.get('o_sc');   ts = (0:size(S,1)-1)' * 100*Tp;      % decimation 100, fixed step Tp
vr = S(:,1);  ips = S(:,3);
i29 = find(ts >= hw.sc.tblack - 1, 1);
if vr(i29) < 3
    error('rail only %.2f V before the blackout: the DC source polarity is probably reversed, set hw.dcFlip = 1 in wc_hw_params and rebuild', vr(i29));
end
ipk = max(abs(ips));
j = find(ts > hw.sc.tblack & vr < hw.sc.Vmin, 1);
if isempty(j), tHold = ts(end) - hw.sc.tblack; else, tHold = ts(j) - hw.sc.tblack; end
R = addRow(R, '6  PS1 peak current while CS1 charges through 22 R', ternary(ipk < 0.6, 'PASS', 'FAIL'), sprintf('%.2f A peak (PS1 limit 0.6 A), rail %.2f V before blackout', ipk, vr(i29)));
R = addRow(R, '6  hold-up after blackout (rail > 3.8 V)', ternary(tHold >= 0.2, 'PASS', 'FAIL'), sprintf('%.2f s (needed for a 200 ms flush)', tHold));


Ipkl = 10*sqrt(2);  meanRandom = 2/pi*Ipkl;
tcmds = 0.1033 + (0:5)*0.0017;
for tm = [7e-3 8e-3 9e-3]
    ia = zeros(size(tcmds));  tpart = zeros(size(tcmds));
    for k = 1:numel(tcmds)
        hw.relay.tcmd = tcmds(k);  hw.relay.tmechActual = tm;  hw.relay.weld = 0;
        assignin('base', 'hw', hw);
        so7 = sim(fast, 'ReturnWorkspaceOutputs', 'on');
        Q = so7.get('o_relay');                          % i gate coil weld state
        idx = find(diff(Q(:,2)) < 0, 1);
        ia(k) = abs(Q(idx, 1));   tpart(k) = (idx - 1)*Ts - tcmds(k);
    end
    st = 'INFO';  if tm == 8e-3, st = ternary(mean(ia) < 0.25*meanRandom && max(tpart) < hw.relay.tweld, 'PASS', 'FAIL'); end
    R = addRow(R, sprintf('7  contacts part, actual %.0f ms (controller assumes 8 ms)', 1e3*tm), st, ...
        sprintf('mean current %.2f A of %.1f A peak (random-instant opening: %.1f A); command to part <= %.1f ms', mean(ia), Ipkl, meanRandom, 1e3*max(tpart)));
end
hw.relay.tmechActual = 8e-3;  hw.relay.tcmd = 0.1033;
for wl = [0 1]
    hw.relay.weld = wl;  assignin('base', 'hw', hw);
    so7 = sim(fast, 'ReturnWorkspaceOutputs', 'on');
    Q = so7.get('o_relay');
    R = addRow(R, sprintf('7  weld flag, contacts %s', ternary(wl, 'welded', 'healthy')), ternary(Q(end,4) == wl, 'PASS', 'FAIL'), sprintf('flag = %d', Q(end,4)));
end

%% report
fprintf('\n%-62s %-8s %s\n', 'check', 'result', 'detail');
for k = 1:size(R,1), fprintf('%-62s %-8s %s\n', R{k,1}, R{k,2}, R{k,3}); end
nf = sum(strcmp(R(:,2), 'FAIL'));
fprintf('\n%d FAIL, %d FINDING (numbers the design must act on), %d PASS\n', nf, sum(strcmp(R(:,2), 'FINDING')), sum(strcmp(R(:,2), 'PASS')));
fprintf('Item 8 (creepage 6.4 mm slot, Kelvin routing of R1, single-point star ground) is a PCB layout rule: see the checklist in the note.\n');
fprintf('OVERALL %s\n', ternary(nf == 0, 'PASS', 'FAIL'));

%% ---------------------------------------------------------------------------------------------------
function R = addRow(R, a, b, c)
R(end+1, :) = {a, b, c};
end

function s = ternary(c, a, b)
if c, s = a; else, s = b; end
end

function [att, ph] = rcChannel(hw, tolv)

r1 = tolv(hw.RA1, hw.mc.tolR);  r2 = tolv(hw.RA2, hw.mc.tolR);  r3 = tolv(hw.RA3, hw.mc.tolR);
cd = tolv(hw.Cd, hw.mc.tolC);   c1 = tolv(hw.Ccm, hw.mc.tolC);  c2 = tolv(hw.Ccm, hw.mc.tolC);
att = r3 ./ (r3 + r1 + r2);
rth = (r1 + r2) .* r3 ./ (r1 + r2 + r3);
tau = rth .* (cd + c1 .* c2 ./ (c1 + c2));
ph = atan(-2*pi*50*tau);
end

function d = rad2degLocal(x)
d = x*180/pi;
end

function p = prctileLocal(x, pc)
x = sort(x(:));
p = x(min(numel(x), max(1, ceil(pc/100*numel(x)))));
end
