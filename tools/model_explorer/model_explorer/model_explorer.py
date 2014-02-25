from numpy import *
from scipy import *

# we want it to work with both Brian and Brian 2
try:
    import brian
except ImportError:
    brian = None

try:
    import brian2
except ImportError:
    brian2 = None

import os
import sys
import re
import multiprocessing
import pickle
import glob

import matplotlib
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbar
from matplotlib.figure import Figure

from copy import copy

from PyQt4 import QtCore, QtGui
from model_explorer_ui import Ui_ModelExplorer

__all__ = ['ExplorableModel', 'ModelExplorerInterruptError', 'Parameter', 'BooleanParameter']

def _get_best_unit(u):
    '''
    Gets the best unit in both Brian 1 and Brian 2
    '''
    if brian is not None:
        if isinstance(u, brian.Quantity):
            return brian.fundamentalunits._get_best_unit(u)
    if brian2 is not None:
        if isinstance(u, brian2.Quantity):
            return u._get_best_unit()
    return 1.0


def have_same_dimensions(x, y):
    '''
    Works with Brian 1 and 2
    '''
    if brian is not None:
        if isinstance(x, brian.Quantity) or isinstance(y, brian.Quantity):
            return brian.have_same_dimensions(x, y)
    if brian2 is not None:
        if isinstance(x, brian2.Quantity) or isinstance(y, brian2.Quantity):
            return brian2.have_same_dimensions(x, y)
    return True


def ensure_directory(d):
    '''
    Ensures that a given directory exists (creates it if necessary)
    '''
    if not os.path.exists(d):
        os.makedirs(d)
    return d


class Parameter(object):
    '''
    Used to specify parameter ranges
    
    The unit and dtype parameters are guessed. Changing the unit parameter is only useful for ensuring that the
    display unit is specific, as the dimensions will be guessed automatically. 
    '''
    def __init__(self, name, start, min, max, step, unit=None, dtype=None, description=None):
        if dtype is None:
            if isinstance(start, int) and isinstance(min, int) and isinstance(max, int) and isinstance(step, int):
                dtype = int
                unit = 1
            else:
                dtype = float
                if unit is None:
                    unit = _get_best_unit(start)
        self.name = name
        self.start = start
        self.min = min
        self.max = max
        self.step = step
        self.unit = unit
        self.dtype = dtype
        if description is None:
            description = name
        self.description = description
        

class BooleanParameter(object):
    '''
    Used to specify a boolean parameter
    '''
    def __init__(self, name, start, description=None):
        self.name = name
        self.start = start
        if description is None:
            description = name
        self.description = description


class ModelExplorerInterruptError(RuntimeError):
    pass

def try_tight_layout(fig):
    try:
        fig.tight_layout()
    except ValueError:
        pass    


class SpinboxChanger(object):
    def __init__(self, model_explorer, param_name):
        self.model_explorer = model_explorer
        self.param_name = param_name
        
    def __call__(self, val):
        self.model_explorer.param_changed(self.param_name, val)

        
class CheckboxChanger(SpinboxChanger):
    def __call__(self, val):
        self.model_explorer.param_changed(self.param_name, bool(val))


class ModelExplorer(QtGui.QMainWindow):
    def __init__(self, parent=None, model=None, auto_compute=True):
        # Do basic setup from Qt Designer
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_ModelExplorer()
        self.ui.setupUi(self)
        #
        self.auto_compute = auto_compute
        self.model = model
        self.model.set_model_explorer(self)
        self.curdata = None
        self.int_percent_complete = 0
        self.modifying_form_data = True
        # create plot region
        self.mpl_toolbar = NavigationToolbar(self.ui.mplwidget.figure.canvas, self)
        self.ui.centralwidget.layout().addWidget(self.mpl_toolbar)
        self.figure = self.ui.mplwidget.figure
        self.figure.clear()
        # update plot styles
        for style in self.model.plot_styles:
            self.ui.combobox_plot_style.addItem(style)
        self.cur_plot_style = self.model.plot_styles[0]
        # insert parameter controls
        pc = self.ui.scroll_area_params_contents.layout()
        pc.setAlignment(QtCore.Qt.AlignTop)
        self.spinbox_changers = []
        self.spinboxes = {}
        self.checkboxes = {}
        self.cur_params = {}
        self.param_units = {}
        self.default_values = {}
        for spec in self.model.param_specs:
            if isinstance(spec, Parameter):
                self.cur_params[spec.name] = spec.start
                self.default_values[spec.name] = spec.start
                if spec.dtype==int:
                    spinbox = QtGui.QSpinBox(self)
                    signal = 'valueChanged(int)'
                else:
                    spinbox = QtGui.QDoubleSpinBox(self)
                    unit = spec.unit
                    if not have_same_dimensions(unit, 1):
                        spinbox.setSuffix(' '+str(unit))
                    spinbox.setDecimals(6)
                    signal = 'valueChanged(double)'
                spinbox.setPrefix(spec.name+': ')
                spinbox.setMinimum(spec.min/spec.unit)
                spinbox.setMaximum(spec.max/spec.unit)
                spinbox.setValue(spec.start/spec.unit)
                spinbox.setSingleStep(spec.step/spec.unit)
                spinbox.setToolTip(spec.description)
                changer = SpinboxChanger(self, spec.name)
                self.spinbox_changers.append(changer)
                self.spinboxes[spec.name] = spinbox
                QtCore.QObject.connect(spinbox, QtCore.SIGNAL(signal), changer)
                pc.addWidget(spinbox)
                self.param_units[spec.name] = spec.unit
            elif isinstance(spec, BooleanParameter):
                self.cur_params[spec.name] = spec.start
                self.default_values[spec.name] = spec.start
                checkbox = QtGui.QCheckBox(spec.name, self)
                checkbox.setToolTip(spec.description)
                checkbox.setChecked(spec.start)
                self.checkboxes[spec.name] = checkbox
                changer = CheckboxChanger(self, spec.name)
                signal = 'stateChanged(int)'
                QtCore.QObject.connect(checkbox, QtCore.SIGNAL(signal), changer)
                pc.addWidget(checkbox)
            else:
                pc.addWidget(QtGui.QLabel(spec, self))
        # load params
        self.get_saved_parameters()
        if auto_compute:
            self.ui.button_compute.hide()
        # initial plot
        self.modifying_form_data = False
        
    def showEvent(self, *args, **kwds):
        super(ModelExplorer, self).showEvent(*args, **kwds)
        QtCore.QTimer.singleShot(1, self.initial_compute_data)
        
    def initial_compute_data(self):
        if hasattr(self, '_initial_compute'):
            return
        self._initial_compute = True
        if self.auto_compute:
            self.compute_data()
            
    def change_plot_style(self, style):
        self.cur_plot_style = str(style)
        self.update_plot()
        
    def get_saved_parameters(self, select=None):
        self.modifying_form_data = True
        params_list = self.model.get_saved_params()
        self.ui.list_saved_params.clear()
        for i, name in enumerate(params_list):
            self.ui.list_saved_params.addItem(name)
            if select is not None and name==select:
                self.ui.list_saved_params.setCurrentRow(i)
        self.modifying_form_data = False
        
    def save_parameters(self):
        param_name, ok = QtGui.QInputDialog.getText(self, 'Parameter set name', 'Parameter set name:')
        if ok:
            param_name = str(param_name)
            if self.model.params_exist(param_name):
                response = QtGui.QMessageBox.question(self, 'Warning', 'Overwrite existing parameters?',
                                                      QtGui.QMessageBox.Cancel | QtGui.QMessageBox.Ok,
                                                      QtGui.QMessageBox.Ok)
                if response==QtGui.QMessageBox.Ok:
                    ok = True
                elif response==QtGui.QMessageBox.Cancel:
                    ok = False
            if ok:
                self.model.save_params(param_name, self.cur_params)
                self.get_saved_parameters(select=param_name)
            
    def delete_parameters(self):
        item = self.ui.list_saved_params.currentItem()
        if item.isSelected():
            self.model.delete_params(str(item.text()))
            self.get_saved_parameters()
        else:
            QtGui.QMessageBox.information(self, 'Information', 'No parameters were selected.')
    
    def delete_all_parameters(self):
        response =  QtGui.QMessageBox.question(self, 'Warning', 'Delete all saved parameters?',
                                               QtGui.QMessageBox.Cancel | QtGui.QMessageBox.Ok,
                                               QtGui.QMessageBox.Cancel)
        if response==QtGui.QMessageBox.Ok:
            self.model.delete_all_params()
            self.get_saved_parameters()
            
    def clicked_saved_parameters(self, item):
        self.load_parameters(str(item.text()))
        
    def load_parameters(self, params):
        if self.modifying_form_data:
            return
        if params:
            params = str(params)
            newparams = self.model.load_params(params)
            keys_new = set(newparams.keys())
            keys_true = set(self.default_values.keys())
            missing_keys = keys_true-keys_new
            ignored_keys = keys_new-keys_true
            if ignored_keys:
                ignored = ', '.join(ignored_keys)
                QtGui.QMessageBox.information(self, 'Information',
                                              'Parameters file has the following ignored  parameters: '+ignored)
                for k in ignored_keys:
                    del newparams[k]
            if missing_keys:
                missing = ', '.join(missing_keys)
                QtGui.QMessageBox.information(self, 'Information',
                                              'Parameters file was missing some keys, '
                                              'the default values will be used: '+missing)
                for k in missing_keys:
                    newparams[k] = self.default_values[k]
            self.cur_params = newparams
            if self.auto_compute:
                self.compute_data()
            self.modifying_form_data = True
            for param_name, val in self.cur_params.items():
                if param_name in self.param_units:
                    self.spinboxes[param_name].setValue(val/self.param_units[param_name])
                else:
                    self.checkboxes[param_name].setChecked(val)
            self.modifying_form_data = False
        
    def param_changed(self, param_name, val):
        if self.modifying_form_data:
            return
        self.ui.list_saved_params.selectionModel().clearSelection()
        QtGui.QApplication.processEvents()
        if param_name in self.param_units:
            val = val*self.param_units[param_name]
        self.cur_params[param_name] = val
        if self.auto_compute:
            self.compute_data()
        
    def compute_data(self):
        data = self.model.compute(**self.cur_params.copy())
        if data is not None:
            self.ui.progress_bar.setValue(0)
            self.curdata = data
            self.update_plot()
    
    def update_plot(self):
        if self.curdata is None:
            return
        self.figure.clear()
        self.model.plot_data(self.figure, self.cur_plot_style, self.curdata)
        try_tight_layout(self.figure)
        self.figure.canvas.draw()
        
    def update_complete(self, fraction):
        complete = int(100*fraction)
        if complete!=self.int_percent_complete:
            self.int_percent_complete = complete
            self.ui.progress_bar.setValue(complete)
            
    def compute(self):
        self.compute_data()
    

class ExplorableModel(object):
    '''
    User should implement this class
    '''
    #: name, used for saving parameters
    explorer_type = None
    #: list of strings, passed to plot_data
    plot_styles = None
    #: list of ``Parameter`` objects, or text for display purposes only
    param_specs = None
    
    def get_data(self, **params):
        '''
        This function should return data or None depending if the computation was interrupted.
        The function should regularly call ``self.update(fraction_complete)`` which will
        raise a ``ModelExplorerInterruptError`` if the computation should be stopped.
        '''
        pass
    
    def plot_data(self, fig, style, data):
        '''
        Function should plot the data returned by get_data on the figure fig with plot style style.
        '''
        pass

    # User should not implement any of the following functions
    
    def __init__(self):
        self.interrupted = False
        self.is_computing = False
        self.next_computation = None
        self.model_explorer = None
        self.basedir = os.path.expanduser('~/.brian2cookbook/tools/model_explorer/'+self.explorer_type)
        ensure_directory(self.basedir)
        
    def params_exist(self, name):
        if os.path.exists(os.path.join(self.basedir, name)):
            return True
        
    def load_params(self, name):
        return pickle.load(open(os.path.join(self.basedir, name), 'rb'))
    
    def save_params(self, name, params):
        pickle.dump(params, open(os.path.join(self.basedir, name), 'wb'), -1)
        
    def delete_params(self, name):
        os.remove(os.path.join(self.basedir, name))
        
    def delete_all_params(self):
        for name in self.get_saved_params():
            self.delete_params(name)
        
    def get_saved_params(self):
        return [os.path.split(fname)[1] for fname in glob.glob(os.path.join(self.basedir, '*'))]
        
    def compute(self, **params):
        if self.is_computing:
            self.interrupted = True
            self.next_computation = params
            return None
        else:
            while True:
                self.interrupted = False
                self.is_computing = True
                try:
                    data = self.get_data(**params)
                except ModelExplorerInterruptError:
                    data = None
                if data is None:
                    params = self.next_computation
                    self.next_computation = None
                else:
                    self.interrupted = False
                    self.is_computing = False
                    return data
                
    def update(self, fraction=None):
        QtGui.QApplication.processEvents()
        if self.model_explorer is not None and fraction is not None:
            self.model_explorer.update_complete(fraction)
        if self.interrupted:
            raise ModelExplorerInterruptError

    def launch_gui(self, auto_compute=True):
        model_explorer(self, auto_compute=auto_compute)
        
    def set_model_explorer(self, model_explorer):
        self.model_explorer = model_explorer    

    
def model_explorer(model, auto_compute=True):
    app = QtGui.QApplication(sys.argv)
    myapp = ModelExplorer(model=model, auto_compute=auto_compute)
    myapp.show()
    sys.exit(app.exec_())
