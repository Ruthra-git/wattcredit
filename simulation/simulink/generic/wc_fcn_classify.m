function [label, loadedWh, counted] = wc_fcn_classify(feat, strobe, E)

persistent lab wh
if isempty(lab), lab = 0; wh = 0; end
f  = feat(:);                                    
Ev = E(:);
counted = 0;
if strobe
    x  = f(1:4);
    dI = sqrt(mean(((x - Ev(1:4)) ./ Ev(5:8)).^2));
    dW = sqrt(mean(((x - Ev(9:12)) ./ Ev(13:16)).^2));
    if f(6) < Ev(22)
        lab = 0;                                 
    elseif min(dI, dW) > Ev(19)
        lab = 3;                                  
    elseif dW < dI && f(5) >= Ev(20) && f(4) >= Ev(21)
        lab = 2;                                 
        wh = wh + max(f(5) - Ev(17), 0)/3600;  
        counted = 1;
    else
        lab = 1;                                  
    end
end
label = lab;
loadedWh = wh;
end
