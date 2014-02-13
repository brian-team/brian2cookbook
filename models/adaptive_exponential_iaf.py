#!/usr/bin/env python
'''
Adaptive exponential integrate and fire model
---------------------------------------------

The figure shows the chaotic region from Fig 8B of:

    Touboul, J. and Brette, R. (2008). Dynamics and bifurcations of the adaptive
    exponential integrate-and-fire model. Biological Cybernetics 99(4-5):319-34.
'''
from brian2 import *

C = 281*pF
gL = 30*nS
EL = -70.6*mV
VT = -50.4*mV
DeltaT = 2*mV
tauw = 40*ms
a = 4*nS
b = 0.08*nA
I = .8*nA
Vcut = VT+5*DeltaT # practical threshold condition
N = 500

eqs='''
dvm/dt = (gL*(EL-vm)+gL*DeltaT*exp((vm-VT)/DeltaT)+I-w)/C : volt
dw/dt  = (a*(vm-EL)-w)/tauw                               : amp
Vr                                                        : volt
'''

neuron = NeuronGroup(N, eqs, threshold='vm>Vcut', reset='vm = Vr; w += b')
neuron.vm = EL
neuron.w = a*(neuron.vm-EL)
neuron.Vr = linspace(-48.3*mV, -47.7*mV, N) # bifurcation parameter

M = SpikeMonitor(neuron)

run(500*ms)

i, t = M.it
plot(t/ms, neuron.Vr[i]/mV, ',k')
xlabel('Time (ms)')
ylabel('Vr (mV)')
axis('tight')
show()
