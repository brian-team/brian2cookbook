'''
Simple model explorer example
-----------------------------

A very simple example of using the model explorer, shows that it can be used with Brian 1 or Brian 2 (or neither).
Use this as a template for your own model explorers.
'''
# Works with either Brian 1 or Brian 2, try it
#from brian import *
from brian2 import *

from model_explorer import *
import time

class SampleModel(ExplorableModel):
    explorer_type = 'sample_model_explorer'
    plot_styles = ['b', 'g', 'r']
    param_specs = [Parameter('n', 1, 1, 10, 1),
                   Parameter('freq', 2*Hz, 1*Hz, 10*Hz, 1*Hz, unit=kHz),
                   Parameter('phase', 0, 0, 360, 15),
                   Parameter('fake', 0, 0, 100, 1),
                   BooleanParameter('slow_mode', False),
                   ]

    def get_data(self, freq, phase, n, slow_mode, fake=None):
        freq = float(freq)
        t = linspace(0, 1, 10000)
        if not slow_mode:
            y = sin(2*pi*freq*t+phase*pi/180.)**n
        else:
            y = zeros_like(t)
            for i in xrange(len(t)):
                self.update(float(i)/len(t))
                y[i] = sin(2*pi*freq*t[i]+phase*pi/180.)**n
        return t, y
    
    def plot_data(self, fig, style, (t, y)):
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(t, y, c=style)

if __name__=='__main__':
    SampleModel().launch_gui()
    
