function [feat, strobe, trip] = wc_fcn_features(v, i, p)

spc = round(p(1)/p(2));  NC = round(p(3));  N = spc*NC;
persistent n cyc sv2 si2 svi c1 s1 c3 s3 c5 s5 cs2 cycR badCnt tripState lastFeat
if isempty(n)
    n = 0; cyc = 0; sv2 = 0; si2 = 0; svi = 0;
    c1 = 0; s1 = 0; c3 = 0; s3 = 0; c5 = 0; s5 = 0; cs2 = 0;
    cycR = zeros(1, 200);  badCnt = 0; tripState = 0; lastFeat = zeros(1, 7);
end
th = 2*pi*mod(n, spc)/spc;
sv2 = sv2 + v*v;   si2 = si2 + i*i;   svi = svi + v*i;
cs2 = cs2 + i*i;                                  % current energy inside the present cycle
c1 = c1 + i*cos(th);    s1 = s1 + i*sin(th);
c3 = c3 + i*cos(3*th);  s3 = s3 + i*sin(3*th);
c5 = c5 + i*cos(5*th);  s5 = s5 + i*sin(5*th);
n = n + 1;
strobe = 0;
if mod(n, spc) == 0                               % end of a cycle
    cyc = cyc + 1;
    cycR(cyc) = sqrt(cs2/spc);   cs2 = 0;
end
if n >= N                                         % end of a frame
    vrms = sqrt(sv2/N);   irms = sqrt(si2/N);   P = svi/N;
    if vrms*irms > 1e-9, pf = P/(vrms*irms); else, pf = 0; end
    a1 = 2/N*sqrt(c1^2 + s1^2);  a3 = 2/N*sqrt(c3^2 + s3^2);  a5 = 2/N*sqrt(c5^2 + s5^2);
    if a1 > 1e-4, h3 = a3/a1; h5 = a5/a1; else, h3 = 0; h5 = 0; end
    r = cycR(1:cyc);   mr = mean(r);
    if mr > 1e-4, rip = sqrt(mean((r - mr).^2))/mr; else, rip = 0; end
    pn = P*(p(4)/max(vrms, 1))^2;
    lastFeat = [pf h3 h5 rip pn irms vrms];
    bad = (vrms < p(5)) || (vrms > p(6)) || (irms > p(7));
    if bad, badCnt = badCnt + 1; else, badCnt = 0; tripState = 0; end
    if badCnt >= p(8), tripState = 1; end
    strobe = 1;
    n = 0; cyc = 0; sv2 = 0; si2 = 0; svi = 0; c1 = 0; s1 = 0; c3 = 0; s3 = 0; c5 = 0; s5 = 0; cs2 = 0;
end
feat = lastFeat(:);                                % 7x1 column: a 1-D vector signal in Simulink
trip = tripState;
end
