function y = wc_fcn_fracdelay(x, d)
%WC_FCN_FRACDELAY  Fractional-sample delay by linear interpolation (paste into a MATLAB Function block).
%  y[n] = (1-d)*x[n] + d*x[n-1],  0 <= d < 1.  Delays the stream by d samples: a phase lag of 2*pi*f0*d/fs at f0.
%  Put it in the path of the channel that LEADS (usually voltage, because the current channel has the slower filter
%  or  inductive shunt), with d set at calibration from the measured phase error. Gain error is below 0.03 % at 50 Hz for d <= 0.36.
persistent xp
if isempty(xp), xp = 0; end
y = (1 - d)*x + d*xp;
xp = x;
end
