from qgis.utils import iface
from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtWidgets import QDockWidget



LOGHEADER = 'Simple WCS 2'


def logInfoMessage(msg):
    QgsMessageLog.logMessage(message=msg, tag=LOGHEADER, level=Qgis.MessageLevel.Info)


def logWarnMessage(msg):
    QgsMessageLog.logMessage(message=msg, tag=LOGHEADER, level=Qgis.MessageLevel.Warning)


def openLog():
    iface.mainWindow().findChild(QDockWidget, 'MessageLog').show()


