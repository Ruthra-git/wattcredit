
hw.cm.Vcm     = 1.44;                
hw.cm.ampGain = 8.2;                  
hw.cm.pinLo   = -1.3;  hw.cm.pinHi = 1.8;    
hw.cm.adcFS   = 1.2;                  
Rtop = 4*330e3;  Rbot = 698;       
hw.div = Rbot/(Rtop + Rbot);
hw.cm.vdI = hw.cm.ampGain * Rsh * 15;                       % differential at amp output, current channel, 15 A pk
hw.cm.vdV = hw.cm.ampGain * 265*sqrt(2) * hw.div;           % voltage channel at 265 V rms

hw.RA1 = 1.5e3;  hw.RA2 = 1.5e3;  hw.RA3 = 2e3;  hw.Cd = 4.7e-9;  hw.Ccm = 470e-12;
hw.att = hw.RA3/(hw.RA3 + hw.RA1 + hw.RA2);

hw.mc.N = 20000;  hw.mc.tolR = 0.01;  hw.mc.tolC = 0.05;  hw.mc.tolRdiv = 0.001;  hw.mc.tolAmp = 0.003;   % amp gain error ASSUMED
hw.mc.tcr = 50e-6;                    % 1/degC, manganin shunt
hw.fd.d   = 0.0356;                   % fractional delay, samples (= 0.1 deg at 50 Hz, 6.4 kS/s)


hw.clamp.vsurge = 710;                % V pk, MOV clamp level 
hw.clamp.Is = 1e-4*exp(-0.24/0.0347); hw.clamp.nVt = 0.0347;   
hw.clamp.Rs = 10;


hw.inrush.Vpk = 325;  hw.inrush.Rwire = 0.5;  hw.inrush.Rser = 10;  hw.inrush.Cin = 4.7e-6;  hw.inrush.Rld = 24e3;   % Cin ASSUMED


hw.ps2.v0 = [5.8 6.0 6.2];  hw.ps2.Rout = 5;  hw.ps2.Rz = 60;  hw.ps2.Rpi = 2.2;  hw.ps2.IL = 0.020;     % Rout and Rz ASSUMED


hw.sc.Vps = 5.0;  hw.sc.Vf = 0.3;  hw.sc.Ron = 0.05;  hw.sc.Rchg = 22;  hw.sc.C = 0.1;
hw.sc.Rload = 31;                     % ohm, about 150 mA at 4.7 V
hw.sc.tblack = 30;  hw.sc.Vmin = 3.8; % s, V (3.3 V + 0.2 V LDO drop-out + 0.3 V SS14)
hw.sc.stop = 40;


hw.relay.tmech = 8e-3;  hw.relay.tweld = 50e-3;  hw.relay.iweld = 0.05;
hw.relay.tmechActual = 8e-3;          % what the plant really does (swept by the check)
hw.relay.tcmd = 0.1033;               % s, command to open
hw.relay.weld = 0;                    % 1 = contacts welded
hw.relay.pvec = [fs f0 hw.relay.tmech hw.relay.tweld hw.relay.iweld];
Zr = Vnom/10;  hw.relay.R = Zr*0.5;  hw.relay.L = Zr*sin(acos(0.5))/(2*pi*f0);    % 10 A rms at PF 0.5

hw.dcFlip = 0;                        
