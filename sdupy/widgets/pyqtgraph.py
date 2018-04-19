import asyncio
import logging
from math import isfinite
from typing import Any, Mapping, Tuple

import networkx as nx
import pyqtgraph as pg
from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFileDialog, QProgressBar
from pyqtgraph.parametertree import Parameter, ParameterItem
from pyqtgraph.parametertree.parameterTypes import WidgetParameterItem

from sdupy.utils import ignore_errors
from stitching.progress import Progress
from . import register_widget
from ..pyreactive import reactive_finalizable


@register_widget("pyqtgraph figure")
class PyQtGraphPlot(pg.PlotWidget):
    pass


@register_widget("pyqtgraph view box")
class PyQtGraphViewBox(pg.GraphicsView):
    def __init__(self, parent):
        super().__init__(parent)
        self.item = pg.ViewBox(lockAspect=True)
        self.setCentralItem(self.item)



@register_widget("pyqtgraph plot")
class PgPlot(pg.GraphicsView):
    def __init__(self, parent):
        super().__init__(parent)
        self.item = pg.PlotItem(lockAspect=True)
        self.item.setAspectLocked(True)
        self.setCentralItem(self.item)


def index_to_str(index):
    res = []
    for i in index:
        if isinstance(i, slice):
            res.append("{}:{}".format(i.start if i.start is not None else "", i.stop if i.stop is not None else ""))
        else:
            res.append(str(i))
    return ','.join(res)

@register_widget("pyqtgraph image view")
class PyQtGraphImage(pg.ImageView):
    def __init__(self, parent):
        super().__init__(parent, view=pg.PlotItem())
        self.view.setAspectLocked(True)
        self._show_cursor_proxy = None
        self.cursor_pos_label = None
        self.show_cursor_pos()

    def show_cursor_pos(self, show=True):
        if self._show_cursor_proxy:
            self._show_cursor_proxy.disconnect()
            self._show_cursor_proxy = None
        if self.cursor_pos_label is not None:
            self.removeItem(self.cursor_pos_label)
            self.cursor_pos_label = None

        if show:
            @ignore_errors
            def mouseMoved(evt):
                view_point = self.view.vb.mapSceneToView(evt[0])
                text = "x,y = ({:0.2f}, {:0.2f})".format(view_point.x(), view_point.y())
                if self.image is not None and 'x' in self.axes and 'y' in self.axes:
                    item_point = self.imageItem.mapFromScene(evt[0])
                    ix = int(item_point.x())
                    iy = int(item_point.y())
                    if 0 <= ix < self.image.shape[self.axes['x']] and 0 <= iy < self.image.shape[self.axes['y']]:
                        index = [slice(None, None)] * len(self.image.shape)
                        index[self.axes['x']] = ix
                        index[self.axes['y']] = iy
                        if self.axes.get('t') is not None:
                            index[self.axes['t']] = self.currentIndex
                        val = self.image[tuple(index)]
                        text += "\ndata[{}] = {}".format(index_to_str(index), val)
                self.cursor_pos_label.setText(text)
                if all(isfinite(c) for c in [view_point.x(), view_point.y()]):
                    self.cursor_pos_label.setPos(view_point)
                else:
                    self.cursor_pos_label.setPos(QPointF(0, 0))

            self.cursor_pos_label = pg.TextItem(anchor=(0, 1))
            self.addItem(self.cursor_pos_label)

        self._show_cursor_proxy = pg.SignalProxy(self.scene.sigMouseMoved, rateLimit=60, slot=mouseMoved)

    def dump_state(self):
        return dict(
            #view_state=self.getView().getState(),
            view_state=self.getView().saveState(),
            colormap=self.getHistogramWidget().gradient.saveState(),
            colormap_region=self.getHistogramWidget().region.getRegion()
        )

    def load_state(self, state: dict):
        if 'view_state' in state:
            #self.getView().setState(state['view_state'])
            self.getView().restoreState(state['view_state'])
        if 'colormap' in state:
            self.getHistogramWidget().gradient.restoreState(state['colormap'])
        if 'colormap_region' in state:
            self.getHistogramWidget().region.setRegion(state['colormap_region'])


HOVER_COLOR = 'blue'


@reactive_finalizable
def display_graph2(g: nx.Graph, widget: pg.GraphicsWidget, pos: Mapping[Any, Tuple[float, float]]):
    nodes = list(g)

    def pos_for_node(node):
        return pos[node]

    def text_for_node(node):
        # g.get_no
        return str(node)

    widget.addItem(pg.GraphItem(pos, adj=[[1, 2]], size=1))
    return

    def make_node(node):
        p = pos_for_node(node)
        artist = ax.text(p[0], p[1], text_for_node(node), bbox=dict(boxstyle='square'))
        # patch = mpatches.Ellipse(pos[node], width=10, height=10)
        artist.set_picker(True)
        # patch.node = node
        # patch.autoscale_None()
        # patch.set_transform(mtransforms.IdentityTransform())
        # col = mcollections.PathCollection([patch])
        # col.autoscale_None()
        return artist

    def hover_artist(artist: Artist):
        assert isinstance(artist, Text)
        artist.get_bbox_patch().set_color(HOVER_COLOR)

    def unhover_artist(artist: Artist):
        assert isinstance(artist, Text)
        artist.get_bbox_patch().set_color('red')

    patches = [make_node(node) for node in nodes]

    node_for_artist = {patch: node for node, patch in zip(nodes, patches)}

    hovered_artists = set()

    def on_plot_hover(event: MouseEvent):
        axes = None
        for artist, node in node_for_artist.items():  # type: Tuple[Artist, Any]
            if artist.contains(event)[0]:
                if artist not in hovered_artists:
                    hover_artist(artist)
                    hovered_artists.add(artist)
                    axes = artist.axes
            else:
                if artist in hovered_artists:
                    unhover_artist(artist)
                    hovered_artists.remove(artist)
                    axes = artist.axes
        if axes:
            axes.get_figure().canvas.draw_idle()

    connection_id = ax.figure.canvas.mpl_connect('motion_notify_event', on_plot_hover)

    yield patches, id

    ax.figure.canvas.mpl_disconnect(connection_id)
    for patch in patches:
        patch.remove()
    ax.figure.canvas.draw_idle()
    # , ax.add_collection(PatchCollection(node_collection))


class PathParameterItem(WidgetParameterItem):
    def __init__(self, param, depth):
        param.opts['type'] = 'str'
        super().__init__(param, depth)

    def makeWidget(self):
        # opts = self.param.opts
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        widget.setLayout(layout)
        textbox = super().makeWidget()
        layout.addWidget(textbox)
        button = QPushButton('Browse...')
        #button.setFixedWidth(20)
        #button.setFixedHeight(20)

        layout.addWidget(button)
        button.clicked.connect(self.browse)

        #widget.setMaximumHeight(20)  ## set to match height of spin box and line edit
        widget.sigChanged = textbox.sigChanged
        widget.value = textbox.value
        widget.setValue = textbox.setValue
        self.widget = widget
        return widget


    @ignore_errors
    def browse(self, xx):
        file_dialog = QFileDialog()
        self.widget.setValue(file_dialog.getExistingDirectory(directory=self.widget.value()))


class PathParameter(Parameter):
    itemClass = PathParameterItem


class TaskParameterItem(ParameterItem):
    def __init__(self, param, depth):
        super().__init__(param, depth)
        self.layoutWidget = QWidget()
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)

        self.start_stop_button = QPushButton()
        self.start_stop_button.setFixedHeight(20)
        self.start_stop_button.setFixedWidth(48)
        self.layout.addWidget(self.start_stop_button)
        self.start_stop_button.clicked.connect(self.buttonClicked)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.layout.addWidget(self.progress_bar)

        self.layoutWidget.setLayout(self.layout)
        #self.layout.addStretch()
        #param.sigNameChanged.connect(self.paramRenamed)
        #self.setText(0, '')
        self.param.sigValueChanged.connect(self.refresh)
        self.refresh(param, None)


    @ignore_errors
    def treeWidgetChanged(self):
        super().treeWidgetChanged()
        tree = self.treeWidget()
        if tree is None:
            return

        #tree.setFirstItemColumnSpanned(self, True)
        tree.setItemWidget(self, 1, self.layoutWidget)

    # def paramRenamed(self, param, name):
    #     self.start_stop_button.setText(name)

    def buttonClicked(self):
        self.param.start_or_stop()

    @ignore_errors
    def refresh(self, param, val):
        self.progress_bar.setMaximum(1000)
        progress = param.progress_tracker
        task = param.task
        if progress is None or task is None:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat('')
            self.start_stop_button.setText('start')
        elif task.done():
            if task is None:
                self.progress_bar.setFormat('')
            elif task.cancelled():
                self.progress_bar.setFormat('cancelled')
            elif task.exception():
                self.progress_bar.setFormat('error: ' + str(task.exception()))
                logging.exception('task finished with error')
            else:
                self.progress_bar.setValue(1000)
                self.progress_bar.setFormat('finished')
            self.start_stop_button.setText('start')
        else:
            self.progress_bar.setFormat('%p% {}'.format(progress._current_status))
            self.progress_bar.setValue(progress._progress*1000)
            self.start_stop_button.setText('cancel')
        print("aa", param)


class TaskParameter(Parameter):
    """Used for displaying a button within the tree."""
    itemClass = TaskParameterItem

    # TODO: replace with some better control
    def __init__(self, func=None, **opts):
        super().__init__(**opts)
        self.func = func
        self.task = None  # type: asyncio.Task
        #self.progress_param = self.addChild(dict(name="progress", type='float', readonly=True, value=0))
        #self.state_param = self.addChild(dict(name="state", type='str', readonly=True, value=0))
        #self.result_param = self.addChild(dict(name="result", type='text', readonly=True))

        self.progress_tracker = None

    @ignore_errors
    def start_or_stop(self):
        if self.task is not None and not self.task.done():
            self.task.cancel()
        else:
            self.task = asyncio.ensure_future(self.run_task())

    async def run_task(self):
        print("starting")
        self.progress_tracker = Progress()
        self.sigValueChanged.emit(self, None)
        refresher = asyncio.ensure_future(self.show_progress())
        await asyncio.sleep(0.001)
        await self.func(self.progress_tracker)
        #self.progress_param.setValue(999)
        #await refresher
        print("finished")

    async def show_progress(self):
        try:
            while True:
                await asyncio.sleep(0.1)
                self.sigValueChanged.emit(self, None)
                if self.task.done():
                    return
        except:
            logging.exception("error in show_progress")