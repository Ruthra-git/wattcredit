function [en, stateCode] = wc_fcn_scenario(t, codes, segT, fRip)

idx = min(floor(t/segT) + 1, numel(codes));
c = codes(idx);
tog = double(mod(floor(t*fRip*2), 2) == 0);
en = [double(c == 1 || c == 5), double(c == 2), double(c == 2)*tog, double(c == 3), double(c == 5), double(c == 4)]';   
stateCode = c;
end
