from PyQt5 import QtGui

import matplotlib.pyplot as plt
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from matplotlib.backend_bases import key_press_handler, MouseEvent
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, \
    NavigationToolbar2QT as NavigationToolbar

from .common.register import register_widget


class Axes(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setFocus()
        self.layout.addWidget(self.canvas)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)
        self.layout.addWidget(self.mpl_toolbar)
        self.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.mpl_toolbar.pan()  # we usually want to pan with mouse, since zooming is on the scroll

        self.axes = self.figure.add_subplot(111)
        self.axes.set_adjustable('datalim')  # use whole area when keeping aspect ratio of images
        self.canvas.draw()

    def on_key_press(self, event):
        # implement the default mpl key press events described at
        # http://matplotlib.org/users/navigation_toolbar.html#navigation-keyboard-shortcuts
        key_press_handler(event, self.canvas, self.mpl_toolbar)

    def on_scroll(self, event: MouseEvent):
        ax = self.axes
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xfocus = event.xdata # get event x location
        yfocus = event.ydata # get event y location
        xlim_delta = [l - xfocus for l in xlim]
        ylim_delta = [l - yfocus for l in ylim]

        SCALE_PER_TICK = 1.3
        if event.button == 'up':
            scale_factor = 1/SCALE_PER_TICK
        elif event.button == 'down':
            scale_factor = SCALE_PER_TICK
        else:
            # deal with something that should never happen
            scale_factor = 1

        xlim_zoomed = [l*scale_factor + xfocus for l in xlim_delta]
        ylim_zoomed = [l*scale_factor + yfocus for l in ylim_delta]
        ax.set_xlim(xlim_zoomed)
        ax.set_ylim(ylim_zoomed)
        self.draw()

    def draw(self):
        self.canvas.draw()

    def resizeEvent(self, a0: QtGui.QResizeEvent):
        self.figure.tight_layout()



@register_widget("matplotlib plot")
class Plot(Axes):
    pass