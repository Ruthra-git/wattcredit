

wc_params;
mdl = 'wattcredit_plug_sim';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);  open_system(mdl);
load_system('sps_lib');

Tp = Ts/4;                                  % power-solver step: 4 sub-steps per control sample
set_param(mdl, 'SolverType','Fixed-step', 'Solver','FixedStepDiscrete', 'FixedStep','Tp', 'StopTime','StopTime');

P  = @(name) [mdl '/' name];
ab = @(src, name, pos, varargin) addBlk(src, P(name), pos, varargin{:});
cn = @(a, b) add_line(mdl, a, b, 'autorouting', 'on');


ab('sps_lib/powergui', 'powergui', [20 20 100 60]);
set_param(P('powergui'), 'SimulationMode', 'Discrete', 'SampleTime', 'Tp');


ab('sps_lib/Sources/AC Voltage Source', 'Vsrc', [60 300 110 350], ...
   'PeakAmplitude', 'Vpk', 'Frequency', 'f0', 'Phase', '0', 'Measurements', 'None');


rowY = 100 + 90*(0:5);
sw   = @(r) sprintf('SW%d', r);
for r = 1:6
    ab('sps_lib/Power Electronics/Ideal Switch', sw(r), [250 rowY(r) 290 rowY(r)+40], ...
       'Ron', '1e-3', 'Lon', '0', 'Rs', '1e6', 'Cs', 'inf', 'Measurements', 'off');
end

RLC = 'sps_lib/Passives/Series RLC Branch';
ab(RLC, 'MotorIdle',  [350 rowY(1) 410 rowY(1)+40], 'BranchType','RL', 'Resistance','motorIdle.R', 'Inductance','motorIdle.L', 'Measurements','None');
ab(RLC, 'MotorWork',  [350 rowY(2) 410 rowY(2)+40], 'BranchType','RL', 'Resistance','motorWork.R', 'Inductance','motorWork.L', 'Measurements','None');
ab(RLC, 'Ripple',     [350 rowY(3) 410 rowY(3)+40], 'BranchType','R',  'Resistance','Rrip', 'Measurements','None');
ab(RLC, 'Heater',     [350 rowY(4) 410 rowY(4)+40], 'BranchType','R',  'Resistance','Rheater', 'Measurements','None');
ab(RLC, 'SpoofHeater',[350 rowY(5) 410 rowY(5)+40], 'BranchType','R',  'Resistance','Rspoof', 'Measurements','None');

% LED / charger stand-in: series R -> diode bridge -> C || R
ab(RLC, 'LedRs', [350 rowY(6) 410 rowY(6)+40], 'BranchType','R', 'Resistance','ledRs', 'Measurements','None');
DIO = 'sps_lib/Power Electronics/Diode';
dx = 480;
ab(DIO, 'LedD1', [dx   rowY(6)-30 dx+40 rowY(6)-10], 'Ron','1e-3', 'Vf','0.8', 'Measurements','off');   % X -> P
ab(DIO, 'LedD2', [dx   rowY(6)+50 dx+40 rowY(6)+70], 'Ron','1e-3', 'Vf','0.8', 'Measurements','off');   % Y -> P
ab(DIO, 'LedD3', [dx+80 rowY(6)-30 dx+120 rowY(6)-10], 'Ron','1e-3', 'Vf','0.8', 'Measurements','off'); % Q -> X
ab(DIO, 'LedD4', [dx+80 rowY(6)+50 dx+120 rowY(6)+70], 'Ron','1e-3', 'Vf','0.8', 'Measurements','off'); % Q -> Y
ab(RLC, 'LedC',  [dx+160 rowY(6)-30 dx+220 rowY(6)+10], 'BranchType','C', 'Capacitance','ledC', 'Measurements','None');
ab(RLC, 'LedR',  [dx+160 rowY(6)+50 dx+220 rowY(6)+90], 'BranchType','R', 'Resistance','ledR', 'Measurements','None');


ab(RLC, 'Shunt', [900 300 960 340], 'BranchType','R', 'Resistance','Rsh', 'Measurements','None');
VM = 'sps_lib/Sensors and Measurements/Voltage Measurement';
ab(VM, 'VmLine',  [140 200 165 230]);          % across L-N : line voltage
ab(VM, 'VmShunt', [900 400 925 430]);          % across the shunt : v_shunt = i*Rsh


% L node fan-out: each switch LConn1 is tied to Vsrc/RConn1 (one add_line per load; Simscape ports branch)
for r = 1:6
    cn('Vsrc/RConn1', [sw(r) '/LConn1']);
end
cn([sw(1) '/RConn1'], 'MotorIdle/LConn1');
cn([sw(2) '/RConn1'], 'MotorWork/LConn1');
cn([sw(3) '/RConn1'], 'Ripple/LConn1');
cn([sw(4) '/RConn1'], 'Heater/LConn1');
cn([sw(5) '/RConn1'], 'SpoofHeater/LConn1');
cn([sw(6) '/RConn1'], 'LedRs/LConn1');
% N node = Shunt/LConn1
cn('MotorIdle/RConn1',   'Shunt/LConn1');
cn('MotorWork/RConn1',   'Shunt/LConn1');
cn('Ripple/RConn1',      'Shunt/LConn1');
cn('Heater/RConn1',      'Shunt/LConn1');
cn('SpoofHeater/RConn1', 'Shunt/LConn1');
cn('Shunt/RConn1',       'Vsrc/LConn1');
% LED bridge: LedRs -> X ; Y = N ; P/Q = DC rail
cn('LedRs/RConn1', 'LedD1/LConn1');      % X
cn('LedRs/RConn1', 'LedD3/RConn1');      % X
cn('Shunt/LConn1', 'LedD2/LConn1');      % Y = N
cn('Shunt/LConn1', 'LedD4/RConn1');      % Y = N
cn('LedD1/RConn1', 'LedD2/RConn1');      % P
cn('LedD1/RConn1', 'LedC/LConn1');
cn('LedD1/RConn1', 'LedR/LConn1');
cn('LedD3/LConn1', 'LedD4/LConn1');      % Q
cn('LedD3/LConn1', 'LedC/RConn1');
cn('LedD3/LConn1', 'LedR/RConn1');
% measurements: + terminal = LConn1, - terminal = LConn2
cn('VmLine/LConn1',  'Vsrc/RConn1');
cn('VmLine/LConn2',  'Shunt/LConn1');
cn('VmShunt/LConn1', 'Shunt/LConn1');
cn('VmShunt/LConn2', 'Shunt/RConn1');


ab('simulink/Discrete/Zero-Order Hold',     'ZohV',  [260 195 300 235], 'SampleTime','Ts');
ab('simulink/Math Operations/Gain',          'GainI', [960 395 1010 435], 'Gain','Gi');
ab('simulink/Discrete/Zero-Order Hold',     'ZohI',  [1040 395 1080 435], 'SampleTime','Ts');
ab('simulink/Sources/Random Number',         'NoiseV', [260 140 300 170], 'Mean','0', 'Variance','noiseV^2', 'SampleTime','Ts', 'Seed','11');
ab('simulink/Sources/Random Number',         'NoiseI', [1040 340 1080 370], 'Mean','0', 'Variance','noiseI^2', 'SampleTime','Ts', 'Seed','12');
ab('simulink/Math Operations/Sum',           'SumV',  [340 190 365 240], 'Inputs','++');
ab('simulink/Math Operations/Sum',           'SumI',  [1120 390 1145 440], 'Inputs','++');
ab('simulink/Discontinuities/Saturation',    'SatV',  [390 195 430 235], 'UpperLimit','VfsPk', 'LowerLimit','-VfsPk');
ab('simulink/Discontinuities/Saturation',    'SatI',  [1170 395 1210 435], 'UpperLimit','IfsPk', 'LowerLimit','-IfsPk');
ab('simulink/Discontinuities/Quantizer',     'AdcV',  [450 195 490 235], 'QuantizationInterval','lsbV');
ab('simulink/Discontinuities/Quantizer',     'AdcI',  [1230 395 1270 435], 'QuantizationInterval','lsbI');
cn('VmLine/1',  'ZohV/1');
cn('ZohV/1',    'SumV/1');   cn('NoiseV/1', 'SumV/2');
cn('SumV/1',    'SatV/1');   cn('SatV/1',  'AdcV/1');
cn('VmShunt/1', 'GainI/1');  cn('GainI/1', 'ZohI/1');
cn('ZohI/1',    'SumI/1');   cn('NoiseI/1','SumI/2');
cn('SumI/1',    'SatI/1');   cn('SatI/1',  'AdcI/1');


here = fileparts(mfilename('fullpath'));
mf   = 'simulink/User-Defined Functions/MATLAB Function';
ab(mf, 'Features', [1320 380 1440 470]);   setMFScript(P('Features'), fullfile(here, 'wc_fcn_features.m'));
ab(mf, 'Classify', [1560 380 1680 470]);   setMFScript(P('Classify'), fullfile(here, 'wc_fcn_classify.m'));
ab(mf, 'Scenario', [60 520 200 580]);      setMFScript(P('Scenario'), fullfile(here, 'wc_fcn_scenario.m'));

ab('simulink/Sources/Constant', 'PVec',   [1230 470 1290 490], 'Value','pvec');
ab('simulink/Sources/Constant', 'EVec',   [1450 500 1510 520], 'Value','E');
ab('simulink/Sources/Constant', 'Codes',  [-60 520 -10 540],   'Value','codes');
ab('simulink/Sources/Constant', 'SegT',   [-60 550 -10 570],   'Value','segT');
ab('simulink/Sources/Constant', 'FRip',   [-60 580 -10 600],   'Value','fRip');
ab('simulink/Sources/Digital Clock', 'Clk', [-60 480 -10 510], 'SampleTime','Ts');

% Features inputs: v, i, p     outputs: feat, strobe, trip
cn('AdcV/1', 'Features/1');  cn('AdcI/1', 'Features/2');  cn('PVec/1', 'Features/3');
% Classify inputs: feat, strobe, E      outputs: label, loadedWh, counted
cn('Features/1', 'Classify/1');  cn('Features/2', 'Classify/2');  cn('EVec/1', 'Classify/3');
% Scenario inputs: t, codes, segT, fRip     outputs: en(1x6), stateCode
cn('Clk/1', 'Scenario/1');  cn('Codes/1', 'Scenario/2');  cn('SegT/1', 'Scenario/3');  cn('FRip/1', 'Scenario/4');


ab('simulink/Signal Routing/Demux', 'Demux6', [230 520 235 640], 'Outputs','6');
cn('Scenario/1', 'Demux6/1');
for r = 1:6
    ab('simulink/Discrete/Zero-Order Hold', sprintf('ZohG%d', r), [240 520+22*r 270 540+22*r], 'SampleTime','Tp');
    cn(sprintf('Demux6/%d', r), sprintf('ZohG%d/1', r));
    cn(sprintf('ZohG%d/1', r), [sw(r) '/1']);
end

names = {'feat','Features',1; 'strobe','Features',2; 'trip','Features',3; ...
         'label','Classify',1; 'wh','Classify',2; 'counted','Classify',3; 'state','Scenario',2};
for k = 1:size(names,1)
    blk = ['Log_' names{k,1}];
    ab('simulink/Sinks/To Workspace', blk, [1760 360+40*k 1830 380+40*k], ...
       'VariableName', ['o_' names{k,1}], 'SaveFormat', 'Array', 'SampleTime', '-1');
    cn(sprintf('%s/%d', names{k,2}, names{k,3}), [blk '/1']);
end

save_system(mdl, fullfile(here, mdl));
fprintf('built and saved %s.slx  (blocks: %d)\n', mdl, numel(find_system(mdl, 'SearchDepth', 1, 'Type', 'Block')));


function setMFScript(blk, file)
%SETMFSCRIPT  Put the text of an .m function into a MATLAB Function block.
rt = sfroot;
ch = find(rt, '-isa', 'Stateflow.EMChart', 'Path', blk);
if isempty(ch), error('MATLAB Function block %s not found', blk); end
ch.Script = fileread(file);
end

function addBlk(src, dst, pos, varargin)
%ADDBLK  add_block, then set mask parameters one by one. A wrong parameter name is replaced by a known alias if
%  one exists; otherwise the error lists every parameter this block really has, so the name can be fixed in one pass.
add_block(src, dst, 'Position', pos);
alias = struct('PeakAmplitude', {{'Amplitude', 'Peak_amplitude'}}, 'Amplitude', {{'PeakAmplitude'}});
dp = fieldnames(get_param(dst, 'DialogParameters'));
for k = 1:2:numel(varargin)
    nm = varargin{k};
    if ~ismember(nm, dp) && isfield(alias, nm)
        hit = intersect(alias.(nm), dp);
        if ~isempty(hit), nm = hit{1}; end
    end
    if ~ismember(nm, dp)
        error('Block %s has no parameter "%s". Its parameters are: %s', dst, varargin{k}, strjoin(dp', ', '));
    end
    set_param(dst, nm, varargin{k+1});
end
end
