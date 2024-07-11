"""
        Simple WCS 2 - QGIS Plugin
        ---   v0.2   ---
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007

        Functions are written in mixedCase, see https://docs.qgis.org/testing/en/docs/developers_guide/codingstandards.html
"""

import os.path
from typing import Optional

from qgis.PyQt.QtCore import (QCoreApplication,
                              QSettings,
                              QTranslator,)
from qgis.PyQt.QtGui import (QAction,
                             QIcon)

from qgis.gui import QgisInterface
from qgis.utils import iface


from .simplewcs_dialog import SimpleWCSDialog
from .resources import *


class SimpleWCS:
    """ Simple WCS Plugin class. """

    def __init__(self, iface: QgisInterface) -> None:

        """ Initializes the plugin and the dialog. """

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

        self.dlg: Optional[SimpleWCSDialog] = None

    def tr(self, message) -> str:
        """ Returns a translated string. """

        return QCoreApplication.translate('SimpleWCS', message)

    def initGui(self) -> None:
        """Create the toolbar icon inside the QGIS GUI.
        """
        icon_path = ':/plugins/simplewcs/icon.png'
        self.startAction = QAction(QIcon(icon_path), self.tr('Simple WCS 2'), iface.mainWindow())
        iface.addPluginToRasterMenu(self.tr('Simple WCS 2'), self.startAction)
        iface.addToolBarIcon(self.startAction)
        self.startAction.triggered.connect(self.startWcsPlugin)

    def unload(self) -> None:
        """Removes the toolbar icon from QGIS GUI."""

        iface.removePluginRasterMenu(self.tr('Simple WCS 2'), self.startAction)
        iface.removeToolBarIcon(self.startAction)

        if self.dlg:
            self.dlg.closeGui()

    def startWcsPlugin(self) -> None:
        """ Creates and shows plugin dialog. """

        if not self.dlg:
            self.dlg = SimpleWCSDialog()
        self.dlg.show()
