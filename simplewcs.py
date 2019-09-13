"""
        Simple WCS 2 - QGIS Plugin
        ---   v0.2   ---
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from .simplewcs_dialog import SimpleWCSDialog
from .resources import *
from .wcs import *
from .coverage import *
from qgis.core import QgsApplication, QgsMessageLog, QgsRasterLayer, QgsProject, QgsLayerTreeLayer, Qgis, QgsTask, QgsRectangle, QgsDataSourceUri, QgsCoordinateReferenceSystem
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.parse import urlparse

import os.path, urllib

logheader = 'Simple WCS 2'

class SimpleWCS:


    def __init__(self, iface):
        """
        The constructor!

        :param iface: iface
        """

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

        # instance attributes
        self.iface = iface
        globals()['iface'] = iface

        self.actions = []
        self.menu = self.tr(u'&Simple WCS 2')
        self.firstStart = None
        self.wcs = ''
        self.acceptedVersions = ['2.1.0', '2.0.1', '2.0.0']


    def tr(self, message):
        """
        Returns a translated string
        """

        return QCoreApplication.translate('SimpleWCS', message)


    def add_action(
        self,
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
            self.iface.addToolBarIcon(action)

        if addToMenu:
            self.iface.addPluginToRasterMenu(self.menu, action)

        self.actions.append(action)

        return action


    def initGui(self):
        """
        Create the menu entries and toolbar icons inside the QGIS GUI.
        """

        icon_path = ':/plugins/simplewcs/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Simple WCS 2'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.firstStart = True


    def unload(self):
        """
        Removes the plugin menu item and icon from QGIS GUI.
        """

        for action in self.actions:
            self.iface.removePluginRasterMenu(self.menu, action)
            #self.iface.removePluginRasterMenu(self.tr(u'&Simple WCS 2'),action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """
        Run that thing!
        """

        if self.firstStart == True:
            self.firstStart = False
            self.dlg = SimpleWCSDialog()

            self.dlg.cbVersion.addItems(self.acceptedVersions)
            self.dlg.cbVersion.setCurrentIndex(1)

            self.dlg.btnGetCapabilities.clicked.connect(self.getCapabilities)
            self.dlg.btnGetCapabilities.setEnabled(False)

            self.dlg.leUrl.textChanged.connect(self.enableBtnGetCapabilities)

            globals()['btnGetCoverage'] = self.dlg.btnGetCoverage
            self.dlg.btnGetCoverage.clicked.connect(self.getCovTask)
            self.dlg.btnGetCoverage.setEnabled(False)

            self.iface.mapCanvas().extentsChanged.connect(self.setExtentLabel)

        self.dlg.show()

        result = self.dlg.exec_()


    def getCapabilities(self):
        self.cleanTabGetCoverage()

        self.wcs = ''

        baseUrl = self.dlg.leUrl.text()

        version = self.dlg.cbVersion.currentText()

        params = {"REQUEST": "GetCapabilities", "SERVICE": "WCS", "Version": version}
        querystring = urllib.parse.urlencode(params)
        url = self.checkUrlSyntax(baseUrl)
        xmlResponse = self.requestXML(url + querystring)

        capabilities = xml.etree.ElementTree.parse(xmlResponse).getroot()
        self.wcs = WCS(capabilities)

        versions = self.wcs.getVersions()

        if version in versions:
            self.setTabGetCoverage(version)
            self.setTabInformation()
            versionsOk = True
        else:
            for c_version in versions:
                # take the first match of accepted versions
                if c_version in self.acceptedVersions:
                    self.setTabGetCoverage(c_version)
                    self.setTabInformation()
                    versionsOk = True
                    break
                else:
                    versionsOk = False

        if versionsOk is False:
            self.logWarnMessage('WCS does not support one of the following Versions: ' + ', '.join(self.acceptedVersions))
            self.openLog()


    def cleanTabGetCoverage(self):

        self.dlg.lblTitle.clear()

        self.dlg.cbCoverage.clear()

        self.dlg.cbCRS.clear()

        self.dlg.cbFormat.clear()

        self.dlg.btnGetCoverage.setEnabled(False)

        self.dlg.lblExtent.clear()


    def setTabGetCoverage(self, version):
        """
        Collects information about the wcs and shows them in GUI
        - supports only tiff at the moment!
        """

        title = self.wcs.getTitle()
        self.dlg.lblTitle.setText(title)

        self.dlg.lblVersion.setText(version)

        coverages = self.wcs.getCoverageIds()
        for coverage in coverages:
            self.dlg.cbCoverage.addItem(coverage)

        crsx = self.wcs.getCRS()
        for crs in crsx:
            self.dlg.cbCRS.addItem(crs)

        formats = self.wcs.getFormats()
        for format in formats:
            if 'tiff' in format:
                self.dlg.cbFormat.addItem(format)

        if any('tiff' in format for format in formats):
            self.dlg.btnGetCoverage.setEnabled(True)
        else:
            self.dlg.cbFormat.addItem('no tiff available')
            self.dlg.cbFormat.setEnabled(False)

        self.setExtentLabel()

        self.dlg.tabWidget.setCurrentIndex(1)


    def setTabInformation(self):
        provider = self.wcs.getProvider()
        self.dlg.lblProvider.setText(provider)

        fees = self.wcs.getFees()
        self.dlg.lblFees.setText(fees)

        constraints = self.wcs.getConstraints()
        self.dlg.lblConstraints.setText(constraints)


    def setExtentLabel(self):
        """
        Collect current extent from mapCanvas and shows it in GUI
        """

        extent = self.iface.mapCanvas().extent().toString()
        coordinates = self.roundExtent(extent)
        extent = str(coordinates[0]) + ', ' + str(coordinates[1]) + ', ' + str(coordinates[2]) + ', ' + str(coordinates[3])
        self.dlg.lblExtent.setText(extent)


    def roundExtent(self, extent):
        extent = extent.split(",")
        extentDump = extent[1].split(" : ")
        coord0 = round(float(extent[0]), 7)
        coord1 = round(float(extentDump[0]), 7)
        coord2 = round(float(extentDump[1]), 7)
        coord3 = round(float(extent[2]), 7)

        coordinates = []
        coordinates.append(coord0)
        coordinates.append(coord1)
        coordinates.append(coord2)
        coordinates.append(coord3)

        return coordinates


    def describeCoverage(self, covId):
        params = {"REQUEST": "DescribeCoverage", "SERVICE": "WCS", "VERSION": "2.0.1", "COVERAGEID": covId}
        querystring = urllib.parse.urlencode(params)

        describeCoverageUrl = self.wcs.getDescribeCoverageUrl()
        url = self.checkUrlSyntax(describeCoverageUrl)
        xmlResponse = self.requestXML(url + querystring)

        describeCoverageRoot = xml.etree.ElementTree.parse(xmlResponse).getroot()
        coverage = Coverage(describeCoverageRoot)

        return coverage


    def getCovTask(self):
        """
        Create an asynchronous QgsTask and add it to the taskManager.
        Task variable is declared as 'global' because of a
        bug in QgsTask or taskManager which prevents the
        'on_finished' function to be executed correctly
        """

        self.getCovProgressBar()

        url, covId = self.getCovQueryStr()
        globals()['gctask'] = QgsTask.fromFunction(u'GetCoverage', getCoverage, url, covId, on_finished=addRLayer)
        QgsApplication.taskManager().addTask(globals()['gctask'])
        self.dlg.btnGetCoverage.setEnabled(False)


    def getCovQueryStr(self):
        version = self.dlg.lblVersion.text()

        covId = self.dlg.cbCoverage.currentText()
        coverage = self.describeCoverage(covId)

        #range = coverage.getRange()
        #self.logInfoMessage(str(range))

        labels = coverage.getAxisLabels()
        label0 = labels[0]
        label1 = labels[1]

        extent = self.iface.mapCanvas().extent().toString()
        coordinates = self.roundExtent(extent)
        subset0 = label0 + '(' + str(coordinates[0]) + ',' + str(coordinates[2]) + ')'
        subset1 = label1 + '(' + str(coordinates[1]) + ',' + str(coordinates[3]) + ')'

        outputcrs = self.dlg.cbCRS.currentText()
        mapcrs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        format = self.dlg.cbFormat.currentText()

        params = [('REQUEST', 'GetCoverage'), ('SERVICE', 'WCS'), ('VERSION', version), ('COVERAGEID', covId), ('OUTPUTCRS', outputcrs), ('SUBSETTINGCRS', mapcrs), ('FORMAT', format), ('SUBSET', subset0), ('SUBSET', subset1)]

        querystring = urllib.parse.urlencode(params)

        getCoverageUrl = self.wcs.getGetCoverageUrl()
        url = self.checkUrlSyntax(getCoverageUrl)
        url = url + querystring

        return url, covId


    def getCovProgressBar(self):
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        progressMessageBar = self.iface.messageBar().createMessage("GetCoverage Request")
        progressMessageBar.layout().addWidget(self.progress)
        globals()['iface'].messageBar().pushWidget(progressMessageBar, Qgis.Info)


    def requestXML(self, url):
        self.logInfoMessage('Requested URL: ' + url)

        try:
            xmlReponse = urllib.request.urlopen(url)
        except HTTPError as e:
            self.logWarnMessage(str(e))
            self.logWarnMessage(str(e.read().decode()))
            self.openLog()
            return None
        except URLError as e:
            self.logWarnMessage(str(e))
            self.logWarnMessage(str(e.read().decode()))
            self.openLog()
            return None

        return xmlReponse


    def checkUrlSyntax(self, url):
        if '?' in url:
            if url.endswith('?'):
                newUrl = url
            elif url.endswith('&'):
                newUrl = url
            else:
                newUrl = url + '&'
        else:
            newUrl = url + '?'

        return newUrl


    def enableBtnGetCapabilities(self):
        if len(self.dlg.leUrl.text()) > 0:
            self.dlg.btnGetCapabilities.setEnabled(True)


    @classmethod
    def enableBtnGetCoverage(self):
        globals()['btnGetCoverage'].setEnabled(True)


    @classmethod
    def logInfoMessage(self, msg):
        QgsMessageLog.logMessage(msg, logheader, Qgis.Info)


    @classmethod
    def logWarnMessage(self, msg):
        QgsMessageLog.logMessage(msg, logheader, Qgis.Warning)


    @classmethod
    def openLog(self):
        globals()['iface'].mainWindow().findChild(QDockWidget, 'MessageLog').show()


    @classmethod
    def cancelMessageBar(self):
        globals()['iface'].messageBar().clearWidgets()


def getCoverage(task, url, covId):
    SimpleWCS.logInfoMessage('Requested URL: ' + url)

    try:
        file, header = urllib.request.urlretrieve(url)
    except HTTPError as e:
        SimpleWCS.logWarnMessage(str(e))
        SimpleWCS.logWarnMessage(str(e.read().decode()))
        return None
    except URLError as e:
        SimpleWCS.logWarnMessage(str(e))
        SimpleWCS.logWarnMessage(str(e.read().decode()))
        return None

    return {'file': file, 'coverage': covId}


def addRLayer(exception, values=None):
    """
    Add the response layer to MapCanvas
    Works only with QgsTask if this function is global...
    :param exception: useless
    :param values: filepath and coverage as string, set to None by default
    :return:
    """

    if values != None:
        rlayer = QgsRasterLayer(values['file'], values['coverage'], 'gdal')
        QgsProject.instance().addMapLayer(rlayer)
    else:
        SimpleWCS.openLog()
        SimpleWCS.logWarnMessage('Error while loading Coverage!')

    SimpleWCS.enableBtnGetCoverage()
    SimpleWCS.cancelMessageBar()

