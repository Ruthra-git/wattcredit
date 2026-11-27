function [coil, weld, st] = wc_fcn_relay(i, cmd, p)


persistent state prev cmdPrev nWait nSince win k coilS weldS
spc = round(p(1)/p(2));
if isempty(state)
    state = 0; prev = 0; cmdPrev = 1; nWait = 0; nSince = 0; win = zeros(1, 256); k = 0; coilS = 1; weldS = 0;
end
k = mod(k, spc) + 1;
win(k) = i*i;
irms = sqrt(sum(win(1:spc))/spc);                 % one-cycle sliding RMS
zc = (prev <= 0 && i > 0) || (prev >= 0 && i < 0);
prev = i;
if cmd == 0 && cmdPrev == 1 && state == 0
    state = 1; nSince = 0;                        % open command received: wait for a current zero
end
if cmd == 1 && state == 1
    state = 0;                                    % command withdrawn before the coil was released
end
if cmd == 1 && cmdPrev == 0 && state >= 3 && weldS == 0
    coilS = 1; state = 0;                         % re-close (only if no weld is latched)
end
cmdPrev = cmd;
if state >= 1
    nSince = nSince + 1;
end
th = 0.5/p(2);
if state == 1 && zc
    nWait = round(mod(th - mod(p(3), th), th)*p(1));
    state = 2;
end
if state == 2
    if nWait <= 0
        coilS = 0; state = 3;
    else
        nWait = nWait - 1;
    end
end
if state == 3 && nSince >= round(p(4)*p(1))
    if irms >= p(5), weldS = 1; end
    state = 4;
end
coil = coilS;
weld = weldS;
st = state;
end
