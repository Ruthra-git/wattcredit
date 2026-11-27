
wc_params;  wc_hw_params;
here = fileparts(mfilename('fullpath'));
load_system('sps_lib');
RLC = 'sps_lib/Passives/Series RLC Branch';
DIO = 'sps_lib/Power Electronics/Diode';
ISW = 'sps_lib/Power Electronics/Ideal Switch';
IM  = 'sps_lib/Sensors and Measurements/Current Measurement';
VM  = 'sps_lib/Sensors and Measurements/Voltage Measurement';
MF  = 'simulink/User-Defined Functions/MATLAB Function';
TW  = 'simulink/Sinks/To Workspace';


mdl = 'wattcredit_hw_fast';
newModel(mdl, 'Tp', '0.3');
[ab, cn] = handles(mdl);
ab('sps_lib/powergui', 'powergui', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', 'Tp');


chan = {'I', 'hw.cm.vdI'; 'V', 'hw.cm.vdV'};
for c = 1:2
    y = 40 + 180*(c-1);   n = chan{c,1};
    ab('simulink/Sources/Sine Wave', ['B1_Sin' n], [20 y 60 y+30], 'Amplitude', chan{c,2}, 'Frequency', '2*pi*f0', 'SampleTime', 'Ts');
    ab('simulink/Math Operations/Gain', ['B1_Half' n], [90 y 130 y+30], 'Gain', '0.5');
    ab('simulink/Math Operations/Gain', ['B1_Att' n],  [90 y+50 130 y+80], 'Gain', 'hw.att');
    ab('simulink/Sources/Constant', ['B1_Vcm' n], [90 y+100 130 y+120], 'Value', 'hw.cm.Vcm');
    ab('simulink/Math Operations/Sum', ['B1_OutP' n], [170 y 200 y+30],    'Inputs', '++');
    ab('simulink/Math Operations/Sum', ['B1_OutN' n], [170 y+40 200 y+70],  'Inputs', '+-');
    ab('simulink/Math Operations/Sum', ['B1_AinP' n], [170 y+80 200 y+110], 'Inputs', '++');
    ab('simulink/Math Operations/Sum', ['B1_AinN' n], [170 y+120 200 y+150],'Inputs', '+-');
    ab('simulink/Signal Routing/Mux', ['B1_Mux' n], [240 y 245 y+100], 'Inputs', '4');
    ab(TW, ['B1_Log' n], [280 y 340 y+30], 'VariableName', ['o_cm' n], 'SaveFormat', 'Array', 'SampleTime', '-1');
    cn(['B1_Sin' n '/1'], ['B1_Half' n '/1']);
    cn(['B1_Half' n '/1'], ['B1_OutP' n '/2']);  cn(['B1_Vcm' n '/1'], ['B1_OutP' n '/1']);
    cn(['B1_Half' n '/1'], ['B1_OutN' n '/2']);  cn(['B1_Vcm' n '/1'], ['B1_OutN' n '/1']);
    cn(['B1_Att' n '/1'], ['B1_AinP' n '/2']);   cn(['B1_Vcm' n '/1'], ['B1_AinP' n '/1']);
    cn(['B1_Att' n '/1'], ['B1_AinN' n '/2']);   cn(['B1_Vcm' n '/1'], ['B1_AinN' n '/1']);
    cn(['B1_Half' n '/1'], ['B1_Att' n '/1']);       % level interface scales the differential: pin swing = att*vd/2
    cn(['B1_OutP' n '/1'], ['B1_Mux' n '/1']);   cn(['B1_OutN' n '/1'], ['B1_Mux' n '/2']);
    cn(['B1_AinP' n '/1'], ['B1_Mux' n '/3']);   cn(['B1_AinN' n '/1'], ['B1_Mux' n '/4']);
    cn(['B1_Mux' n '/1'], ['B1_Log' n '/1']);
end


ab('simulink/Sources/Sine Wave', 'B2_V', [20 420 60 450], 'Amplitude', '325', 'Frequency', '2*pi*f0', 'SampleTime', 'Ts');
ab('simulink/Sources/Sine Wave', 'B2_I', [20 480 60 510], 'Amplitude', '14.14', 'Frequency', '2*pi*f0', 'Phase', '-pi/3', 'SampleTime', 'Ts');
ab(MF, 'B2_FracDelay', [110 410 200 460]);   setMFScript([mdl '/B2_FracDelay'], fullfile(here, 'wc_fcn_fracdelay.m'));
ab('simulink/Sources/Constant', 'B2_d', [20 360 60 380], 'Value', 'hw.fd.d');
ab('simulink/Signal Routing/Mux', 'B2_Mux', [250 420 255 500], 'Inputs', '3');
ab(TW, 'B2_Log', [290 450 350 480], 'VariableName', 'o_fd', 'SaveFormat', 'Array', 'SampleTime', '-1');
cn('B2_V/1', 'B2_FracDelay/1');  cn('B2_d/1', 'B2_FracDelay/2');
cn('B2_V/1', 'B2_Mux/1');  cn('B2_FracDelay/1', 'B2_Mux/2');  cn('B2_I/1', 'B2_Mux/3');  cn('B2_Mux/1', 'B2_Log/1');


ab('sps_lib/Sources/AC Voltage Source', 'B4_Vsrc', [20 600 70 650], 'PeakAmplitude', 'hw.inrush.Vpk', 'Frequency', 'f0', 'Phase', '90', 'Measurements', 'None');
ab(RLC, 'B4_Rwire', [120 600 180 640], 'BranchType', 'R', 'Resistance', 'hw.inrush.Rwire', 'Measurements', 'None');
ab(RLC, 'B4_Rser',  [210 600 270 640], 'BranchType', 'R', 'Resistance', 'max(hw.inrush.Rser,1e-3)', 'Measurements', 'None');
ab(IM,  'B4_Im',    [300 600 340 640]);
ab(DIO, 'B4_D1', [400 580 440 600], 'Ron', '0.05', 'Vf', '0.8', 'Measurements', 'off');
ab(DIO, 'B4_D2', [400 660 440 680], 'Ron', '0.05', 'Vf', '0.8', 'Measurements', 'off');
ab(DIO, 'B4_D3', [480 580 520 600], 'Ron', '0.05', 'Vf', '0.8', 'Measurements', 'off');
ab(DIO, 'B4_D4', [480 660 520 680], 'Ron', '0.05', 'Vf', '0.8', 'Measurements', 'off');
ab(RLC, 'B4_Cin', [560 570 620 610], 'BranchType', 'C', 'Capacitance', 'hw.inrush.Cin', 'Measurements', 'None');
ab(RLC, 'B4_Rld', [560 650 620 690], 'BranchType', 'R', 'Resistance', 'hw.inrush.Rld', 'Measurements', 'None');
ab(TW,  'B4_Log', [380 700 440 730], 'VariableName', 'o_inrush', 'SaveFormat', 'Array', 'SampleTime', '-1');
cn('B4_Vsrc/RConn1', 'B4_Rwire/LConn1');  cn('B4_Rwire/RConn1', 'B4_Rser/LConn1');  cn('B4_Rser/RConn1', 'B4_Im/LConn1');
cn('B4_Im/RConn1', 'B4_D1/LConn1');  cn('B4_Im/RConn1', 'B4_D3/RConn1');                 % X
cn('B4_Vsrc/LConn1', 'B4_D2/LConn1'); cn('B4_Vsrc/LConn1', 'B4_D4/RConn1');                % Y
cn('B4_D1/RConn1', 'B4_D2/RConn1');  cn('B4_D1/RConn1', 'B4_Cin/LConn1');  cn('B4_D1/RConn1', 'B4_Rld/LConn1');   % P
cn('B4_D3/LConn1', 'B4_D4/LConn1');  cn('B4_D3/LConn1', 'B4_Cin/RConn1');  cn('B4_D3/LConn1', 'B4_Rld/RConn1');   % Q
cn('B4_Im/1', 'B4_Log/1');


ab('sps_lib/Sources/AC Voltage Source', 'B7_Vsrc', [20 800 70 850], 'PeakAmplitude', 'Vnom*sqrt(2)', 'Frequency', 'f0', 'Phase', '0', 'Measurements', 'None');
ab(ISW, 'B7_K1', [120 800 160 840], 'Ron', '1e-3', 'Lon', '0', 'Rs', '1e6', 'Cs', 'inf', 'Measurements', 'off');
ab(RLC, 'B7_Load', [200 800 260 840], 'BranchType', 'RL', 'Resistance', 'hw.relay.R', 'Inductance', 'hw.relay.L', 'Measurements', 'None');
ab(IM,  'B7_Im', [300 800 340 840]);
cn('B7_Vsrc/RConn1', 'B7_K1/LConn1');  cn('B7_K1/RConn1', 'B7_Load/LConn1');
cn('B7_Load/RConn1', 'B7_Im/LConn1');  cn('B7_Im/RConn1', 'B7_Vsrc/LConn1');
ab('simulink/Discrete/Zero-Order Hold', 'B7_ZohI', [380 850 420 880], 'SampleTime', 'Ts');
ab('simulink/Sources/Step', 'B7_Cmd', [380 900 420 930], 'Time', 'hw.relay.tcmd', 'Before', '1', 'After', '0', 'SampleTime', 'Ts');
ab('simulink/Sources/Constant', 'B7_P', [380 950 420 970], 'Value', 'hw.relay.pvec');
ab(MF, 'B7_Relay', [470 850 560 940]);   setMFScript([mdl '/B7_Relay'], fullfile(here, 'wc_fcn_relay.m'));
ab('simulink/Discrete/Delay', 'B7_Mech', [610 850 650 880], 'DelayLength', 'round(hw.relay.tmechActual/Ts)', 'InitialCondition', '1', 'SampleTime', 'Ts');
ab('simulink/Sources/Constant', 'B7_Weld', [610 900 650 920], 'Value', 'hw.relay.weld');
ab('simulink/Math Operations/Sum', 'B7_Or', [690 860 715 900], 'Inputs', '++');
ab('simulink/Discontinuities/Saturation', 'B7_Sat', [740 860 780 890], 'UpperLimit', '1', 'LowerLimit', '0');
ab('simulink/Discrete/Zero-Order Hold', 'B7_ZohG', [810 860 850 890], 'SampleTime', 'Tp');
ab('simulink/Signal Routing/Mux', 'B7_Mux', [900 850 905 950], 'Inputs', '5');
ab(TW,  'B7_Log', [940 880 1000 910], 'VariableName', 'o_relay', 'SaveFormat', 'Array', 'SampleTime', '-1');
cn('B7_Im/1', 'B7_ZohI/1');  cn('B7_ZohI/1', 'B7_Relay/1');  cn('B7_Cmd/1', 'B7_Relay/2');  cn('B7_P/1', 'B7_Relay/3');
cn('B7_Relay/1', 'B7_Mech/1');  cn('B7_Mech/1', 'B7_Or/1');  cn('B7_Weld/1', 'B7_Or/2');
cn('B7_Or/1', 'B7_Sat/1');  cn('B7_Sat/1', 'B7_ZohG/1');  cn('B7_ZohG/1', 'B7_K1/1');
cn('B7_ZohI/1', 'B7_Mux/1');  cn('B7_Sat/1', 'B7_Mux/2');  cn('B7_Relay/1', 'B7_Mux/3');  cn('B7_Relay/2', 'B7_Mux/4');  cn('B7_Relay/3', 'B7_Mux/5');
cn('B7_Mux/1', 'B7_Log/1');

save_system(mdl, fullfile(here, mdl));
fprintf('built %s (%d blocks)\n', mdl, numel(find_system(mdl, 'SearchDepth', 1, 'Type', 'Block')));


mdl = 'wattcredit_hw_slow';
newModel(mdl, 'Tp', 'hw.sc.stop');
[ab, cn] = handles(mdl);
ab('sps_lib/powergui', 'powergui', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', 'Tp');
% PS1 5 V -> blackout switch -> current sense -> SS14 (D1) -> RAIL;  RAIL -> logic load;  RAIL -> 22 R -> CS1;  reverse SS14 (D2) CS1 -> RAIL
ab('sps_lib/Sources/DC Voltage Source', 'B6_Ps1', [20 100 60 150], 'Amplitude', 'hw.sc.Vps', 'Measurements', 'None');
ab(ISW, 'B6_Sw', [110 100 150 140], 'Ron', '1e-3', 'Lon', '0', 'Rs', '1e6', 'Cs', 'inf', 'Measurements', 'off');
ab(IM,  'B6_Im', [190 100 230 140]);
ab(DIO, 'B6_D1', [270 100 330 140], 'Ron', 'hw.sc.Ron', 'Vf', 'hw.sc.Vf', 'Measurements', 'off');
ab(RLC, 'B6_Rload', [420 200 480 240], 'BranchType', 'R', 'Resistance', 'hw.sc.Rload', 'Measurements', 'None');
ab(RLC, 'B6_R22',   [420 100 480 140], 'BranchType', 'R', 'Resistance', 'hw.sc.Rchg', 'Measurements', 'None');
ab(DIO, 'B6_D2',    [420 20 480 60], 'Ron', 'hw.sc.Ron', 'Vf', 'hw.sc.Vf', 'Measurements', 'off');
ab(RLC, 'B6_Cs1',   [560 100 620 140], 'BranchType', 'C', 'Capacitance', 'hw.sc.C', 'Setx0', 'on', 'InitialVoltage', '0', 'Measurements', 'None');
ab(VM,  'B6_VmRail', [360 300 385 330]);
ab(VM,  'B6_VmCap',  [520 300 545 330]);
ab('simulink/Sources/Step', 'B6_Black', [60 220 100 250], 'Time', 'hw.sc.tblack', 'Before', '1', 'After', '0', 'SampleTime', '0');
ab('simulink/Discrete/Zero-Order Hold', 'B6_Zoh', [120 220 160 250], 'SampleTime', 'Tp');
ab('simulink/Signal Routing/Mux', 'B6_Mux', [700 300 705 380], 'Inputs', '3');
ab(TW, 'B6_Log', [740 320 800 350], 'VariableName', 'o_sc', 'SaveFormat', 'Array', 'SampleTime', '-1', 'Decimation', '100');
if hw.dcFlip, plusP = 'LConn1'; minusP = 'RConn1'; else, plusP = 'RConn1'; minusP = 'LConn1'; end
cn(['B6_Ps1/' plusP], 'B6_Sw/LConn1');  cn('B6_Sw/RConn1', 'B6_Im/LConn1');  cn('B6_Im/RConn1', 'B6_D1/LConn1');
% RAIL = D1 cathode
cn('B6_D1/RConn1', 'B6_Rload/LConn1');  cn('B6_D1/RConn1', 'B6_R22/LConn1');  cn('B6_D1/RConn1', 'B6_D2/RConn1');  cn('B6_D1/RConn1', 'B6_VmRail/LConn1');
% CAP node = R22 right = D2 anode = CS1 +
cn('B6_R22/RConn1', 'B6_Cs1/LConn1');  cn('B6_R22/RConn1', 'B6_D2/LConn1');  cn('B6_R22/RConn1', 'B6_VmCap/LConn1');
% ground node = PS1 minus
gn = ['B6_Ps1/' minusP];
cn(gn, 'B6_Rload/RConn1');  cn(gn, 'B6_Cs1/RConn1');  cn(gn, 'B6_VmRail/LConn2');  cn(gn, 'B6_VmCap/LConn2');
cn('B6_Black/1', 'B6_Zoh/1');  cn('B6_Zoh/1', 'B6_Sw/1');
cn('B6_VmRail/1', 'B6_Mux/1');  cn('B6_VmCap/1', 'B6_Mux/2');  cn('B6_Im/1', 'B6_Mux/3');  cn('B6_Mux/1', 'B6_Log/1');
save_system(mdl, fullfile(here, mdl));
fprintf('built %s (%d blocks)\n', mdl, numel(find_system(mdl, 'SearchDepth', 1, 'Type', 'Block')));

function newModel(mdl, ~, stopExpr)
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);  open_system(mdl);
set_param(mdl, 'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', 'FixedStep', 'Tp', 'StopTime', stopExpr);
end

function [ab, cn] = handles(mdl)
ab = @(src, name, pos, varargin) addBlk(src, [mdl '/' name], pos, varargin{:});
cn = @(a, b) add_line(mdl, a, b, 'autorouting', 'on');
end

function addBlk(src, dst, pos, varargin)

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

function setMFScript(blk, file)
rt = sfroot;
ch = find(rt, '-isa', 'Stateflow.EMChart', 'Path', blk);
if isempty(ch), error('MATLAB Function block %s not found', blk); end
ch.Script = fileread(file);
end
