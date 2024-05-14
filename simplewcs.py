"""
        Simple WCS 2 - QGIS Plugin
        ---   v0.2   ---
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007

        Functions are written in mixedCase, see https://docs.qgis.org/testing/en/docs/developers_guide/codingstandards.html
"""
import json
import os.path
import urllib
from typing import Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.parse import urlparse

from qgis.PyQt.QtCore import (QCoreApplication,
                              QSettings,
                              Qt,
                              QTranslator,
                              QUrl,)
from qgis.PyQt.QtGui import (QAction,
                             QIcon)
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.PyQt.QtWidgets import (QDockWidget,
                                 QProgressBar,)

from qgis.core import (QgsApplication,
                       QgsCoordinateReferenceSystem,
                       QgsDataSourceUri,
                       QgsLayerTreeLayer,
                       QgsMessageLog,
                       QgsNetworkAccessManager,
                       QgsProject,
                       Qgis,
                       QgsTask,
                       QgsRasterLayer,
                       QgsRectangle,
                       QgsRasterLayer,
                       )
from qgis.utils import iface

from .simplewcs_dialog import SimpleWCSDialog
from .resources import *


class SimpleWCS:

    def __init__(self, iface):
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'SimpleWCS_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr('&Simple WCS 2')
        self.dlg: SimpleWCSDialog = None

    def tr(self, message):
        """
        Returns a translated string
        """
        return QCoreApplication.translate('SimpleWCS', message)

    def add_action(self,
                   iconPath,
                   text,
                   callback,
                   enabledFlag=True,
                   addToMenu=True,
                   addToToolbar=True,
                   statusTip=None,
                   whatsThis=None,
                   parent=None):
        """
        Adds plugin icon to toolbar
        """
        icon = QIcon(iconPath)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabledFlag)
        if statusTip is not None:
            action.setStatusTip(statusTip)
        if whatsThis is not None:
            action.setWhatsThis(whatsThis)
        if addToToolbar:
            iface.addToolBarIcon(action)
        if addToMenu:
            iface.addPluginToRasterMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        """
        Create the toolbar icon inside the QGIS GUI.
        """
        icon_path = ':/plugins/simplewcs/icon.png'
        self.add_action(icon_path,
                        text=self.tr('Simple WCS 2'),
                        callback=self.run,
                        parent=iface.mainWindow())

    def unload(self):
        """
        Removes the toolbar icon from QGIS GUI.
        """
        for action in self.actions:
            iface.removePluginRasterMenu(self.menu, action)
            iface.removeToolBarIcon(action)
        if self.dlg:
            self.dlg.resetPlugin()

    def run(self):
        if not self.dlg:
            self.dlg = SimpleWCSDialog()
        self.dlg.show()
