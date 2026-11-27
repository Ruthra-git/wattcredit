

here = fileparts(mfilename('fullpath'));
wc_params;
mdl = 'wattcredit_plug_sim';
slx = fullfile(here, [mdl '.slx']);
if ~bdIsLoaded(mdl)
    if exist(slx, 'file'), load_system(slx); else, build_wattcredit_sim; end
end


codesEn = [ones(1,20) 2*ones(1,20) ones(1,10) 2*ones(1,10)];       % idle, work, held idle, held work (1 s each)
Ren = runScenario(mdl, codesEn, 1, E, Vpk);
assert(Ren.nfr == numel(codesEn), 'enrolment run gave %d frames, expected %d', Ren.nfr, numel(codesEn));
fi = Ren.feat(2:20, :);   fw = Ren.feat(22:40, :);
hi = Ren.feat(42:50, :);  hw = Ren.feat(52:60, :);
[muI, sdI, pnI] = enrolStats(fi);
[muW, sdW, pnW] = enrolStats(fw);
held = [hi; hw];
d = sort(min(distTo(held, muI, sdI), distTo(held, muW, sdW)));
tau = rule.tauMult * d(min(numel(d), ceil(0.99*numel(d))));
Enrol = [muI sdI muW sdW pnI pnW tau (pnI + rule.pGateFrac*(pnW - pnI)) (rule.ripGateFrac*muW(4)) rule.iOffA];
assert(numel(Enrol) == 22);
fprintf('enrolment  idle: PF=%.3f H3=%.3f rip=%.2f%% Pn=%.1f W | work: PF=%.3f H3=%.3f rip=%.2f%% Pn=%.1f W\n', ...
    muI(1), muI(2), 100*muI(4), pnI, muW(1), muW(2), 100*muW(4), pnW);
fprintf('           tau=%.2f  power gate=%.1f W  ripple gate=%.2f%%\n', tau, Enrol(20), 100*Enrol(21));


Rs = runScenario(mdl, scenario.codes, scenario.segT, Enrol, Vpk);
nseg = numel(scenario.codes);
assert(Rs.nfr == nseg*scenario.segT, 'scenario run gave %d frames, expected %d', Rs.nfr, nseg*scenario.segT);
lblName = {'OFF','IDLE','WORK','OTHER'};
allowed = {0, 1, 2, 3, 3, [0 1 3], 2};                               % per segment; SPOOF may be anything but WORK
ok = true;
fprintf('\n%-8s %-22s %s\n', 'state', 'labels (9 frames)', 'result');
for s = 1:nseg
    f = (s-1)*scenario.segT + (2:scenario.segT);                     % skip first frame of the segment
    labs = Rs.label(f);
    pass = all(ismember(labs, allowed{s}));
    ok = ok && pass;
    fprintf('%-8s %-22s %s\n', scenario.names{s}, strjoin(unique(lblName(labs+1)), ','), ternary(pass, 'PASS', 'FAIL'));
end


cf = find(Rs.counted > 0.5);
segOfFrame = ceil(cf / scenario.segT);
credOnlyWork = all(scenario.codes(segOfFrame) == 2);
whCheck = sum(max(Rs.feat(cf,5) - pnI, 0)) / 3600;
whModel = Rs.wh(end);
creditOk = credOnlyWork && abs(whModel - whCheck) < 1e-6*max(1, whCheck);
ok = ok && creditOk;
fprintf('\ncredited frames: %d (all inside WORK segments: %d)   model Wh=%.5f  recomputed Wh=%.5f  %s\n', ...
    numel(cf), credOnlyWork, whModel, whCheck, ternary(creditOk, 'PASS', 'FAIL'));


assert(~any(Rs.trip), 'protection flag raised at nominal voltage');
fprintf('protection at nominal: no trips   PASS\n');
for tst = {'sag 150 V', 150; 'swell 275 V', 275}'
    Rp = runScenario(mdl, [3 3 3 3], 1, Enrol, tst{2}*sqrt(2));
    pass = isequal(Rp.trip(:)', [0 0 1 1]);
    ok = ok && pass;
    fprintf('protection %-12s trip per frame = [%s]   %s\n', tst{1}, num2str(Rp.trip(:)'), ternary(pass, 'PASS', 'FAIL'));
end


fg = figure('Visible', 'off', 'Position', [100 100 900 600]);
subplot(2,1,1);  stairs(1:Rs.nfr, Rs.label, 'LineWidth', 1.5);  ylim([-0.5 3.5]);
set(gca, 'YTick', 0:3, 'YTickLabel', lblName);  ylabel('label');  grid on;
title('WattCredit plug: evidence label per 1 s frame (segments: OFF IDLE WORK HEATER LED SPOOF WORK)');
subplot(2,1,2);  yyaxis left;  plot(1:Rs.nfr, Rs.feat(:,5), '-o');  ylabel('normalised power (W)');
yyaxis right;  plot(1:Rs.nfr, 100*Rs.feat(:,4), '-s');  ylabel('cycle ripple (%)');  xlabel('frame (s)');  grid on;
saveas(fg, fullfile(here, 'wc_check_result.png'));
fprintf('\nOVERALL %s\n', ternary(ok, 'PASS', 'FAIL'));


function R = runScenario(mdl, codes, segT, E, Vpk)

assignin('base', 'codes', codes);   assignin('base', 'segT', segT);
assignin('base', 'E', E);           assignin('base', 'Vpk', Vpk);
T  = numel(codes) * segT;
so = sim(mdl, 'StopTime', num2str(T), 'ReturnWorkspaceOutputs', 'on');
strobe = so.get('o_strobe');   strobe = strobe(:);
feat   = so.get('o_feat');

nS = numel(strobe);
if ndims(feat) == 3,  feat = reshape(feat, [], size(feat, 3)).';
elseif size(feat, 1) ~= nS && size(feat, 2) == nS,  feat = feat.';  end
assert(size(feat, 1) == nS && size(feat, 2) == 7, 'o_feat has size %s, expected %d x 7', mat2str(size(feat)), nS);
lab = so.get('o_label');    lab = lab(:);
wh  = so.get('o_wh');       wh  = wh(:);
cnt = so.get('o_counted');  cnt = cnt(:);
tr  = so.get('o_trip');     tr  = tr(:);
tt  = so.get('tout');       tt  = tt(:);
idx = find(strobe > 0.5);
R.idx = idx;   R.nfr = numel(idx);   R.t = tt(idx);
R.feat = feat(idx, :);   R.label = lab(idx);   R.wh = wh(idx);   R.counted = cnt(idx);   R.trip = tr(idx);
end

function [mu, sd, pn] = enrolStats(F)

X  = F(:, 1:4);
mu = mean(X, 1);
sd = max(std(X, 0, 1), 0.025*abs(mu) + 1e-4);
pn = mean(F(:, 5));
end

function d = distTo(F, mu, sd)

d = sqrt(mean(((F(:, 1:4) - mu) ./ sd).^2, 2));
end

function s = ternary(c, a, b)
if c, s = a; else, s = b; end
end
