import asyncio
import io
import traceback
from typing import Any, Callable, List, NamedTuple
import gc

import numpy as np
import pandas as pd
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLineEdit, QTableView, QVBoxLayout, QWidget

from sdupy.utils import ignore_errors
from .common.register import register_factory, register_widget
from ..reactive import WrapperInterface, reactive, unwrap


@register_widget("generic table")
class Table(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self._table_view = QTableView(self)
        self._table_view.horizontalHeader().setSectionsMovable(True)
        self.layout.addWidget(self._table_view)

    def dump_state(self):
        return dict(
            header_state=bytes(self._table_view.horizontalHeader().saveState()).hex(),
        )

    def load_state(self, state: dict):
        if 'header_state' in state:
            self._table_view.horizontalHeader().restoreState(bytes.fromhex(state['header_state']))


@register_widget("variables table")
class VarsTable(Table):
    def __init__(self, parent):
        super().__init__(parent)
        self.model = VarsModel(self)
        self._table_view.setModel(self.model)

        self.insert_var = self.model.insert_var
        self.remove_var = self.model.remove_var
        self.clear = self.model.clear


class VarsModel(QAbstractTableModel):
    class VarInList(NamedTuple):
        title: str
        var: WrapperInterface
        notify_func: Callable
        to_value: Callable[[str], Any]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vars = []  # type: List[VarsModel.VarInList]

    def rowCount(self, parent=None):
        return len(self.vars)

    def columnCount(self, parent=None):
        return 2

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if index.isValid():
            if index.row() < len(self.vars):
                item = self.vars[index.row()]
                if role == Qt.DisplayRole or role == Qt.EditRole:
                    if index.column() == 0:
                        return item.title
                    elif index.column() == 1:
                        try:
                            return str(unwrap(item.var))
                        except Exception as e:
                            return "{}{}".format(e.__class__, e)

    def flags(self, index: QModelIndex):
        if index.row() < len(self.vars):
            item = self.vars[index.row()]
            return super().flags(index) | (Qt.ItemIsEditable if hasattr(item.var, 'set') else 0)
        return super().flags(index)

    def setData(self, index: QModelIndex, value: Any, role: int):
        if index.isValid():
            if index.row() < len(self.vars):
                item = self.vars[index.row()]
                try:
                    converted_value = item.to_value(value)
                    item.var.set(converted_value)
                except Exception as e:
                    logging.exception('exception during setting var')
                    item.var.set_exception(e)
                return True
        return super().setData(index, value, role)

    def remove_var(self, title):
        indices_for_removal = [i for i, var_in_the_list in enumerate(self.vars) if var_in_the_list.title == title]

        for i in reversed(indices_for_removal):
            self.beginRemoveRows(QModelIndex(), i, i)
            del self.vars[i]
            self.endRemoveRows()

    def clear(self):
        if len(self.vars) > 0:
            self.beginRemoveRows(QModelIndex(), 0, len(self.vars) - 1)
            self.vars.clear()
            self.endRemoveRows()

    def insert_var(self, title: str, var: WrapperInterface, to_value: Callable[[str], Any]):
        assert var is not None
        self.remove_var(title)

        async def notify_changed():
            for i, var_in_the_list in enumerate(self.vars):
                if var_in_the_list.var == var:
                    self.dataChanged.emit(self.index(i, 1), self.index(i, 1))

        var.__notifier__.add_observer(notify_changed, None)

        self.beginInsertRows(QModelIndex(), len(self.vars), len(self.vars))
        self.vars.append(VarsModel.VarInList(title=title, var=var, notify_func=notify_changed, to_value=to_value))
        self.endInsertRows()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return "name" if section == 0 else "value"
            # if orientation == Qt.Vertical and role == Qt.DisplayRole:
            #    return self.data.index[section]


@register_widget("array table")
class ArrayTable(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self._table_view = QTableView(self)
        self.layout.addWidget(self._table_view)

        self._model = None
        self._var = None
        self._setter = None
        self._set_current_val(np.array([[]]))

    @property
    def var(self):
        return self._var

    @var.setter
    def var(self, new_var):
        self._var = new_var
        self._setter = None
        gc.collect()
        self._setter = reactive(self._set_current_val)(self._var)

    def _set_current_val(self, val):
        self._model = ArrayModel(val, self)
        self._table_view.setModel(self._model)


class ArrayModel(QAbstractTableModel):
    def __init__(self, array: np.ndarray, parent=None):
        super().__init__(parent)
        assert hasattr(array, 'shape')
        assert hasattr(array, '__getitem__')
        self._array = array  # type: np.ndarray

        # if array.shape[0]>0:
        #     self.beginInsertRows(QModelIndex(), 0, array.shape[0]-1)
        #     self.endInsertRows()
        #
        # if array.shape[1]>0:
        #     self.beginInsertColumns(QModelIndex(), 0, array.shape[1]-1)
        #     self.endInsertColumns()
        #
        #     self.dataChanged.emit(self.index(0, 0), self.index(array.shape[0]-1, array.shape[1]-1))

    @ignore_errors(retval=0)
    def rowCount(self, parent=None):
        return self._array.shape[0]

    @ignore_errors(retval=0)
    def columnCount(self, parent=None):
        return self._array.shape[1]

    @ignore_errors
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        #print("get data", role)
        #print("index: ", index.row(), index.column(), role)
        if self._index_is_good(index):
            #print("good")
            if role in [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole, Qt.StatusTipRole]:
                res = str(self._array[index.row(), index.column()])
                #print("returning", res)
                return res


    @ignore_errors(retval=Qt.ItemFlags())
    def flags(self, index: QModelIndex):
        if self._index_is_good(index):
            return super().flags(index) | (Qt.ItemIsEditable if True else 0)
        return super().flags(index)

    def _index_is_good(self, index: QModelIndex):
        #print(self._array.shape)
        res = (index.isValid()
               and index.row() < self._array.shape[0]
               and index.column() < self._array.shape[1])
        #print("good?", res)
        return res

    @ignore_errors
    def setData(self, index: QModelIndex, value: Any, role: int):
        if self._index_is_good(index):
            try:
                self._array[index.row(), index.column()] = eval(value)
            except Exception as e:
                logging.exception('exception during setting var (ignoring)')
            return True
        return super().setData(index, value, role)

    @ignore_errors
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return str(section)


@register_widget("data_table")
class PandasTable(Table):
    def __init__(self, parent):
        super().__init__(parent)
        self.model = DataTreeModel(self)
        self._table_view.setModel(self.model)
        # self._table_view.setSortingEnabled(True)

        self._filter_edit = QLineEdit(self)
        self._filter_edit.editingFinished.connect(lambda: self.model.set_query(self._filter_edit.text()))
        self.layout.insertWidget(0, self._filter_edit)

    @reactive()
    def set_data(self, data: pd.DataFrame):
        if data is None:
            data = pd.DataFrame()
        self.model.set_data(data)


class DataTreeModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        size = 1000 * 100
        arr = ((int(n) for n in d) for d in np.array(np.random.randn(size, 4)))
        # arrs=np.array(list(map(tuple, arr.tolist())), dtype=dict(names=['a', 'b', 'c', 'd'], formats=[np.float]*4))
        test_data = pd.DataFrame(arr, columns=['a', 'b', 'c', 'd'])
        self.original_data = test_data
        self.data = self.original_data
        self.query_is_ok = True

        self._sort_columns = []
        self._query = None

    def rowCount(self, parent=None):
        return len(self.data)

    def columnCount(self, parent=None):
        return len(self.data.columns)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return str(self.data.iloc[index.row(), index.column()])

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.data.columns[section]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return self.data.index[section]

    def rebuild_data(self):
        self.beginResetModel()
        self.data = self.original_data
        self.query_is_ok = True
        try:
            if self._sort_columns:
                cols, orders = zip(*reversed(self._sort_columns))
                self.data = self.data.sort_values(by=list(cols), ascending=list(orders))
            self.query_is_ok = False
            if self._query:
                self.data = self.data.query(self._query)
                self.query_is_ok = True
        except Exception:
            logging.exception("ignoring")
        self.endResetModel()

    def sort(self, column: int, order: Qt.SortOrder):
        column_name = self.original_data.columns[column]
        self._sort_columns = list(filter(lambda t: t[0] != column_name, self._sort_columns))
        self._sort_columns.append((column_name, order == Qt.AscendingOrder))
        while len(self._sort_columns) > 5:
            self._sort_columns.pop(0)
        self.rebuild_data()

    def set_query(self, query: str):
        self._query = query
        self.rebuild_data()

    def set_data(self, data):
        self.original_data = data
        self.rebuild_data()


@reactive()
async def gen(n, t=1):
    for i in range(n):
        await asyncio.sleep(t)
        yield 1 + i * i


@reactive()
async def append_data_frame(gen):
    res = pd.DataFrame(index=[], columns=['a'])
    async for v in gen:
        res.loc[len(res.index), 'a'] = v
        yield res


@register_factory("generated data table")
def make_dt(parent):
    dt = PandasTable(parent)

    async def set_data(parent):
        dt.set_data(await var_from_gen(append_data_frame(gen(100))))

    asyncio.ensure_future(set_data(parent))

    return dt


import logging
import logging.handlers


class LogRecordsModel(QAbstractTableModel, logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []  # type: List[logging.LogRecord]
        self.columns = ['timestamp', 'name', 'level', 'message', 'path', 'file']
        self.records_limit = 100000
        self.bg_colors = {
            logging.CRITICAL: QColor(Qt.magenta).lighter(),
            logging.ERROR: QColor(Qt.red).lighter(),
            logging.WARNING: QColor(Qt.yellow).lighter(),
            logging.INFO: QColor(Qt.green).lighter(),
            logging.DEBUG: QColor(Qt.cyan).lighter(),
        }

    def emit(self, record: logging.LogRecord):
        if len(self.records) > self.records_limit:
            chunk_size = 10
            self.beginRemoveRows(QModelIndex(), 0, chunk_size - 1)
            del self.records[0:chunk_size]  # it's probably faster to remove in greater chunks
            self.endRemoveRows()

        try:
            self.beginInsertRows(QModelIndex(), len(self.records), len(self.records))
            self.records.append(record)
            self.endInsertRows()
        except Exception:
            self.handleError(record)
        if len(self.records) % 10 == 0:
            logging.fatal('has %d records', len(self.records))

    def __repr__(self):
        level = logging.getLevelName(self.level)
        return '<%s (%s)>' % (self.__class__.__name__, level)

    def rowCount(self, parent=None):
        return len(self.records)

    def columnCount(self, parent=None):
        return len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if index.row() < len(self.records) and index.column() < len(self.columns):
                record = self.records[index.row()]
                col_name = self.columns[index.column()]
                if role == Qt.DisplayRole or role == Qt.ToolTipRole:
                    if col_name == 'message':
                        if record.exc_info:
                            if role == Qt.ToolTipRole:
                                return record.getMessage() + '\n' + self.formatException(record.exc_info)
                            else:
                                return record.getMessage() + " (see tooltop for more)"
                        else:
                            return record.getMessage()
                    elif col_name == 'level':
                        return record.levelname
                    elif col_name == 'timestamp':
                        return '{:.3f}'.format(record.relativeCreated)
                    elif col_name == 'path':
                        return record.pathname
                    elif col_name == 'file':
                        return record.filename + ":" + str(record.lineno)
                    elif col_name == 'name':
                        return record.name
                elif role == Qt.BackgroundColorRole:
                    # TODO interpolate between two nearest?
                    if record.levelno in self.bg_colors:
                        return self.bg_colors[record.levelno]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section]

    def formatException(self, ei):
        """
        Stolen from logging module.

        Format and return the specified exception information as a string.

        This default implementation just uses
        traceback.print_exception()
        """
        sio = io.StringIO()
        tb = ei[2]
        # See issues #9427, #1553375. Commented out for now.
        # if getattr(self, 'fullstack', False):
        #    traceback.print_stack(tb.tb_frame.f_back, file=sio)
        traceback.print_exception(ei[0], ei[1], tb, None, sio)
        s = sio.getvalue()
        sio.close()
        if s[-1:] == "\n":
            s = s[:-1]
        return s


global_logger_handler = LogRecordsModel()

logging.getLogger().addHandler(global_logger_handler)
# logging.getLogger().setLevel(logging.DEBUG)
# global_logger_handler.setLevel(logging.DEBUG)

logging.getLogger().setLevel(logging.INFO)
global_logger_handler.setLevel(logging.INFO)


@register_widget("logs")
class Logs(Table):
    def __init__(self, parent):
        super().__init__(parent)
        self._table_view.setModel(global_logger_handler)
