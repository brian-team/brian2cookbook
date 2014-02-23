'''
Adaptive exponential integrate and fire model explorer
------------------------------------------------------

In this example, you can modify the parameters of the (reduced) adaptive exponential
integrate and fire model.
'''
from brian2 import *
from model_explorer import *

# Switch this on to run it a bit faster if you have gcc installed
#brian_prefs.codegen.target = 'weave'

G = None
spikemon = None
statemon = None
cur_Nr = None

def get_adex_data(model,
                  taum, tauw,
                  a, b,
                  DeltaT, EL, VT, Vr,
                  duration, silent, Imin, Imax, N, repeats,
                  ):
    global G, spikemon, statemon, cur_Nr, cur_eqs
    
    Vcut = VT + 5 * DeltaT
    Nr = N*repeats
    
    if DeltaT>0:
        DeltaT_min = DeltaT
    else:
        DeltaT_min = 1*volt
        
    eqs = '''
    dvm/dt = ((EL-vm)+DeltaT*exp((vm-VT)/DeltaT_min)+I-w)/taum : volt
    dw/dt = (a*(vm-EL)-w)/tauw : volt
    I : volt
    '''
        
    if cur_Nr!=Nr:
        G = NeuronGroup(Nr, eqs, threshold='vm>Vcut', reset='vm = Vr; w += b')
        model.update() # maintain responsiveness of gui
        spikemon = SpikeMonitor(G)
        model.update() # maintain responsiveness of gui
        statemon = StateMonitor(G, variables=['vm', 'w'], record=[0, Nr/3, 2*Nr/3, Nr-1])
        model.update() # maintain responsiveness of gui
        cur_Nr = Nr

    spikemon.resize(0)
    statemon.resize(0)
    G.vm = EL
    G.I = repeat(linspace(Imin, Imax, N), repeats)
    G.w = 0
    @network_operation
    def up():
        model.update(defaultclock.t/duration)
    net = Network(G, spikemon, statemon, up)
    net.run(duration)
    net.remove(spikemon)
    G.I = 0
    net.run(silent)
    return spikemon.it, statemon.t, statemon.vm, statemon.w
    
    
class AdExModel(ExplorableModel):
    explorer_type = 'adex'
    plot_styles = ['standard']
    param_specs = [
        'Time constants',
        Parameter('taum', 1*ms, 0.1*ms, 100*ms, 1*ms, unit=ms),
        Parameter('tauw', 10*ms, 0.1*ms, 100*ms, 1*ms, unit=ms),
        'Adaptation',
        Parameter('a', 1.0, 0.0, 100.0, 0.1),
        Parameter('b', 20*mV, 0*mV, 1000*mV, 10*mV, unit=mV),
        'Electrical',
        Parameter('EL', -70*mV, -100*mV, 0*mV, 5*mV, unit=mV),
        Parameter('VT', -50*mV, -100*mV, 0*mV, 5*mV, unit=mV),
        Parameter('Vr', -70*mV, -100*mV, 0*mV, 5*mV, unit=mV),
        Parameter('DeltaT', 0*mV, 0*mV, 10*mV, 0.5*mV, unit=mV),
        'Simulation',
        Parameter('duration', 500*ms, 0*ms, 10*second, 100*ms, unit=ms),
        Parameter('silent', 100*ms, 0*ms, 10*second, 100*ms, unit=ms),
        Parameter('Imin', 0*mV, 0*mV, 1000*mV, 10*mV, unit=mV),
        Parameter('Imax', 100*mV, 0*mV, 1000*mV, 10*mV, unit=mV),
        Parameter('N', 100, 1, 1000, 10),
        Parameter('repeats', 1, 1, 100, 5),
        ]
    
    def get_data(self, **params):
        return get_adex_data(self, **params), params

    def plot_data(self, fig, style, data):
        ((i, t), times, vm, w), params = data
        fig.clear()
        
        # raster
        ax_raster = ax = fig.add_subplot(221)
        ax.plot(t/ms, i, ',k')
        ax.set_xlabel('Time (ms)')
        ax.set_ylabel('Neuron index')
        
        # f-I
        ax = fig.add_subplot(222)
        counts = bincount(i/params['repeats'], minlength=params['N'])
        rates = counts*1.0/params['repeats']/params['duration']
        I = linspace(params['Imin'], params['Imax'], params['N'])
        ax.plot(I/mV, rates)
        ax.set_xlabel('Input (mV)')
        ax.set_ylabel('Firing rate (sp/s)')

        # vm
        ax = fig.add_subplot(223, sharex=ax_raster)
        ax.plot(times/ms, vm.T/mV)
        ax.set_xlabel('Time (ms)')
        ax.set_ylabel('vm (mV)')
        
        # w
        ax = fig.add_subplot(224, sharex=ax_raster)
        ax.plot(times/ms, w.T/mV)
        ax.set_xlabel('Time (ms)')
        ax.set_ylabel('w (mV)')

if __name__=='__main__':
    model = AdExModel()
    model.launch_gui()
