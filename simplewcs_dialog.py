"""lf.capabilities
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Marcus Mohr (LGB)
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""
import os
import json
import urllib
import xml.etree.ElementTree as ET
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
                             QColor,
                             QIcon,
                             QKeySequence)
from qgis.PyQt.QtWidgets import QShortcut

from qgis.core import (QgsApplication,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsDataSourceUri,
                       QgsFeature,
                       QgsGeometry,
                       QgsLayerTreeLayer,
                       QgsMapLayer,
                       QgsMessageLog,
                       QgsNetworkAccessManager,
                       QgsPoint,
                       QgsPointXY,
                       QgsProject,
                       Qgis,
                       QgsTask,
                       QgsRasterLayer,
                       QgsRectangle,
                       QgsRasterLayer,
                       QgsVectorLayer,
                       )
from qgis.utils import iface

from qgis.PyQt import uic
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.PyQt.QtWidgets import (QDialog,
                                 QDockWidget,
                                 QProgressBar,)

from .resources import *  # magically sets up icon etc...
from .capabilities import Capabilities
from .coverage import DescribeCoverage
from .boundingBox import BoundingBox
from .drawPolygon import DrawPolygon
from .utils import crsAsOgcUri, getAxisLabels, switchCrsUriToOpenGis

logheader = 'Simple WCS 2'

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'simplewcs_dialog_base.ui'))


class SimpleWCSDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):

        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        super(SimpleWCSDialog, self).__init__(parent)

        self.requestXMinPolygon: float
        self.requestYMinPolygon: float
        self.requestXMaxPolygon: float
        self.requestYMaxPolygon: float

        self.requestXMinCanvas: float
        self.requestYMinCanvas: float
        self.requestXMaxCanvas: float
        self.requestYMaxCanvas: float

        self.capabilities: Capabilities = None
        self.coverageBoundingBox: BoundingBox = None
        self.requestBoundingBox: BoundingBox = None
        self.sketchingToolAction: QAction = None

        self.acceptedVersions = ['2.1.0', '2.0.1', '2.0.0']

        self.setupUi(self)

        self.setupKey()

        self.connectSignals()

    def showEvent(self, event):
        self.adjustToCovId()

    def setupUi(self, widget):

        super().setupUi(widget)

        self.tabGetCoverage.setEnabled(False)
        self.tabInformation.setEnabled(False)

        self.cbVersion.addItems(self.acceptedVersions)
        self.cbVersion.setCurrentIndex(1)

        self.btnGetCapabilities.setEnabled(False)

        self.cbUseSubset.setChecked(True)
        self.showAndHideExtent()

        self.fillMapExtentCombo()
        self.adjustToMapExtentMode()
        self.sketchingToolAction = QAction()
        self.sketchingToolAction.setIcon(QgsApplication.getThemeIcon('/mActionAddPolygon.svg'))
        self.sketchingToolAction.setToolTip('Draw a polygon on the canvas')
        self.sketchingToolAction.setCheckable(True)
        self.tbDrawPolygon.setDefaultAction(self.sketchingToolAction)

        self.btnGetCoverage.setEnabled(False)

    def connectSignals(self):

        self.leUrl.textChanged.connect(self.enableBtnGetCapabilities)
        self.btnGetCapabilities.clicked.connect(self.getCapabilitiesAndAdjustTabs)

        self.cbCoverage.currentIndexChanged.connect(self.adjustToCovId)
        self.cbUseSubset.stateChanged.connect(self.showAndHideExtent)
        self.cbSetExtentMode.currentIndexChanged.connect(self.adjustToMapExtentMode)
        iface.mapCanvas().extentsChanged.connect(self.setExtentLabel)
        self.sketchingToolAction.triggered.connect(self.startSketchingTool)
        QgsProject.instance().crsChanged.connect(self.clearBoundingBoxes)

        self.btnGetCoverage.clicked.connect(self.getCovTask)

    def adjustBoundingBoxesToCrsIfVisible(self):
        if self.isVisible():
            self.clearBoundingBoxes()
            self.adjustToCovId()

    def setupKey(self):
        escKey = QShortcut(QKeySequence("ESC"), self)
        escKey.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escKey.activated.connect(self.resetPlugin)
        escKey.setEnabled(True)

    def showAndHideExtent(self):
        subsetModeIsActivated = self.cbUseSubset.isChecked()
        if subsetModeIsActivated :
            self.wgMapExtent.show()
        else:
            self.wgMapExtent.hide()

    def fillMapExtentCombo(self):
        self.cbSetExtentMode.clear()
        self.cbSetExtentMode.addItem("Get extent from map canvas", "canvas")
        self.cbSetExtentMode.addItem("Draw polygon", "polygon")

    def adjustToMapExtentMode(self):
        extentMode = self.cbSetExtentMode.currentData()
        if extentMode == "canvas":
            if self.requestBoundingBox:
                self.requestBoundingBox.reset()
            self.tbDrawPolygon.hide()
            self.lblExtentMapCanvas.show()
            self.lblExtentPolygon.hide()
            self.lblExtentPolygon.clear()
        elif extentMode == "polygon":
            self.tbDrawPolygon.show()
            self.lblExtentMapCanvas.hide()
            self.lblExtentPolygon.show()


    def startSketchingTool(self):
        self.sketchTool = DrawPolygon()
        self.sketchTool.sketchFinished.connect(self.onSketchFinished)
        iface.mapCanvas().setMapTool(self.sketchTool)

    def stopSketchingTool(self):
        iface.mapCanvas().unsetMapTool(self.sketchTool)
        self.sketchTool.deactivate()
        self.sketchingToolAction.setChecked(False)

    def onSketchFinished(self, geom: QgsGeometry):
        self.stopSketchingTool()
        if not geom.isGeosValid():
            # ToDo: Write warning
            iface.messageBar().pushWarning("Warning", "ADD WARNING")
            return
        if not self.requestBoundingBox:
            self.requestBoundingBox = BoundingBox('request_extent')
        rectBB = self.requestBoundingBox.setBoundingBoxPolygon(geom)
        self.setPolygonExtentLabel(rectBB)

    def setPolygonExtentLabel(self, rectBB: QgsRectangle):
        self.requestXMaxPolygon = round(rectBB.xMaximum(), 7)
        self.requestYMaxPolygon = round(rectBB.yMaximum(), 7)
        self.requestXMinPolygon = round(rectBB.xMinimum(), 7)
        self.requestYMinPolygon = round(rectBB.yMinimum(), 7)
        self.lblExtentPolygon.setText(f"{self.requestXMinPolygon}, {self.requestYMinPolygon}, {self.requestXMaxPolygon}, {self.requestYMaxPolygon}")

    def getCapabilitiesAndAdjustTabs(self) -> bool:

        """ ToDo """

        baseUrl = self.leUrl.text()
        version = self.cbVersion.currentText()
        capabilities = self.requestCapabilities(version=version, baseUrl=baseUrl)
        self.capabilities = Capabilities(capabilities)

        checkedVersion = self.checkVersion(version)
        if not checkedVersion:
            logWarnMessage(
                f'WCS does not support one of the following Versions: {", ".join(self.acceptedVersions)}')
            openLog()
            return False

        self.setCoverageAndInformationTab(checkedVersion)
        return True

    def checkVersion(self, version: str) -> str:

        versions = self.capabilities.getVersions()
        if version in versions:
            return version
        else:
            for c_version in versions:
                # Take the highest available version
                if c_version in self.acceptedVersions:
                    return c_version
        return None

    def setCoverageAndInformationTab(self, version: str):
        self.setGetCoverageTab(version)
        self.setInformationTab()

    def setGetCoverageTab(self, version: str):
        """
        Collects information about the wcs and shows them in GUI
        - supports only tiff at the moment!
        """
        self.tabGetCoverage.setEnabled(True)

        self.cleanGetCoverageTab()

        title = self.capabilities.getTitle()
        self.lblTitle.setText(title)

        self.lblVersion.setText(version)

        formats = self.capabilities.getFormats()
        for format in formats:
            if 'tiff' in format:
                self.cbFormat.addItem(format)

        if any('tiff' in format for format in formats):
            self.btnGetCoverage.setEnabled(True)
        else:
            self.cbFormat.addItem('no tiff available')
            self.cbFormat.setEnabled(False)

        self.cbCoverage.clear()
        for covId, _ in self.capabilities.getCoverageSummary().items():
            self.cbCoverage.addItem(covId)
        self.adjustToCovId()

        self.setExtentLabel()

        self.tabWidget.setCurrentIndex(1)

    def setInformationTab(self):

        self.tabInformation.setEnabled(True)

        self.cleanInformationTab()

        provider = self.capabilities.getProvider()
        self.lblProvider.setText(provider)

        fees = self.capabilities.getFees()
        self.lblFees.setText(fees)

        constraints = self.capabilities.getConstraints()
        self.lblConstraints.setText(constraints)

    def requestCapabilities(self, version: str, baseUrl: str) -> ET.ElementTree:
        capabilitiesRequest = self.buildCapabilitiesRequest(version=version, baseUrl=baseUrl)
        print('capRequest', capabilitiesRequest)
        capabilitiesStr = sendRequest(request=capabilitiesRequest)
        capabilitiesXml = ET.ElementTree(ET.fromstring(capabilitiesStr))
        return capabilitiesXml

    def buildCoverageRequest(self, covId: str, version: str) -> str:
        params = {"REQUEST": "DescribeCoverage", "SERVICE": "WCS", "VERSION": version, "COVERAGEID": covId}
        queryString = urllib.parse.urlencode(params)
        describeCoverageUrl = self.capabilities.getDescribeCoverageUrl()
        url = self.checkUrlSyntax(describeCoverageUrl)
        return url + queryString

    def describeCoverage(self, covId: str, version: str) -> DescribeCoverage:
        coverageRequest = self.buildCoverageRequest(covId, version)
        print('decrCoverageRequest', coverageRequest)
        coverageStr = sendRequest(request=coverageRequest)
        coverageXml = ET.ElementTree(ET.fromstring(coverageStr))
        return DescribeCoverage(coverageXml)

    def buildCapabilitiesRequest(self, version: str, baseUrl: str) -> str:
        params = {"REQUEST": "GetCapabilities", "SERVICE": "WCS", "Version": version}
        queryString = urllib.parse.urlencode(params)
        baseUrl = self.checkUrlSyntax(baseUrl)
        capabilitiesRequest = baseUrl + queryString
        return capabilitiesRequest

    def cleanGetCoverageTab(self):
        self.lblTitle.clear()
        self.cbCoverage.clear()
        self.cbCRS.clear()
        self.cbFormat.clear()
        self.btnGetCoverage.setEnabled(False)
        self.lblExtentMapCanvas.clear()
        self.lblExtentPolygon.clear()

    def cleanInformationTab(self):
        self.lblProvider.clear()
        self.lblFees.clear()
        self.lblConstraints.clear()

    def adjustToCovId(self):

        covId = self.cbCoverage.currentText()
        if covId:
            # Adjust crs dropdown
            self.cbCRS.clear()
            crsList = self.capabilities.getCoverageSummary()[covId].crs
            self.cbCRS.addItems(crsList)

            # Set bounding box
            if not self.coverageBoundingBox:
                self.coverageBoundingBox = BoundingBox('coverage_extent')

            self.coverageBoundingBox.clearBoundingBox()
            lowerCorner = self.capabilities.getCoverageSummary()[covId].bbLowerCorner
            upperCorner = self.capabilities.getCoverageSummary()[covId].bbUpperCorner
            if lowerCorner and upperCorner:
                x_1, y_1 = lowerCorner.split(" ")
                x_2, y_2 = upperCorner.split(" ")
                try:
                    x_1 = float(x_1)
                    y_1 = float(y_1)
                    x_2 = float(x_2)
                    y_2 = float(y_2)
                except:
                    # ToDo: log message
                    return

                self.coverageBoundingBox.setBoundingBoxFromWgsCoordinates(x_1, y_1, x_2, y_2)

            else:
                # ToDo: log message
                pass

    def resetPlugin(self):
        self.clearBoundingBoxes()
        self.close()

    def closeEvent(self, event):
        self.resetPlugin()

    def clearBoundingBoxes(self):
        if self.coverageBoundingBox:
            self.coverageBoundingBox.clearBoundingBox()
        if self.requestBoundingBox:
            self.requestBoundingBox.clearBoundingBox()
            self.lblExtentPolygon.setText("Draw polygon to get extent coordinates")

    def setExtentLabel(self):
        """
        Collect current extent from mapCanvas and shows it in GUI
        """
        mapExtent = iface.mapCanvas().extent()
        self.requestXMinCanvas = round(mapExtent.xMinimum(), 7)
        self.requestYMinCanvas = round(mapExtent.yMinimum(), 7)
        self.requestXMaxCanvas = round(mapExtent.xMaximum(), 7)
        self.requestYMaxCanvas = round(mapExtent.yMaximum(), 7)
        extentLabel = f"{self.requestXMinCanvas}, {self.requestYMinCanvas}, {self.requestXMaxCanvas}, {self.requestYMaxCanvas}"
        self.lblExtentMapCanvas.setText(extentLabel)

    def getCovTask(self):
        """
        Create an asynchronous QgsTask and add it to the taskManager.
        """

        self.getCovProgressBar()

        try:
            url, covId = self.getCovQueryStr()
        except ValueError as e:
            self.logWarnMessage(str(e))
            return

        # task as instance variable so on_finished works
        # ref https://gis.stackexchange.com/a/435487/51035
        # ref https://gis-ops.com/qgis-3-plugin-tutorial-background-processing/
        self.task = QgsTask.fromFunction(
            'Get Coverage',
            getCoverage,
            url,
            covId,
            on_finished=self.addRLayer,
            flags=QgsTask.CanCancel
        )
        QgsApplication.taskManager().addTask(self.task)

        self.btnGetCoverage.setEnabled(False)


    def getSubsets(self,
                   mapCrs: QgsCoordinateReferenceSystem,
                   outputCrsUri: str):

        coverageCrsUri = self.getNativeCoverageCrsUri()
        if coverageCrsUri == outputCrsUri:
            axisLabel0, axisLabel1 = self.describeCov.getAxisLabels()
        else:
            axisList = getAxisLabels(outputCrsUri)
            if not axisList:
                # ToDo: Log message
                axisLabel0, axisLabel1 = self.describeCov.getAxisLabels()
                outputCrsUri = coverageCrsUri
            else:
                axisLabel0, axisLabel1 = axisList

        try:
            mapCrsUri = crsAsOgcUri(mapCrs)
        except:
            raise  # re-raise exception

        subsetMode = self.cbSetExtentMode.currentData()

        outputCrs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(outputCrsUri)

        if mapCrsUri != outputCrsUri:

            logInfoMessage(f"Transforming extent coordinates from {mapCrsUri} to {outputCrsUri}")

            points = []
            if subsetMode == 'polygon':
                points.append(QgsPoint(self.requestXMinPolygon, self.requestYMinPolygon))
                points.append(QgsPoint(self.requestXMinPolygon, self.requestYMaxPolygon))
                points.append(QgsPoint(self.requestXMaxPolygon, self.requestYMinPolygon))
                points.append(QgsPoint(self.requestXMaxPolygon, self.requestYMaxPolygon))

            elif subsetMode == 'canvas':
                points.append(QgsPoint(self.requestXMinCanvas, self.requestYMinCanvas))
                points.append(QgsPoint(self.requestXMinCanvas, self.requestYMaxCanvas))
                points.append(QgsPoint(self.requestXMaxCanvas, self.requestYMinCanvas))
                points.append(QgsPoint(self.requestXMaxCanvas, self.requestYMaxCanvas))

            transformation = QgsCoordinateTransform(mapCrs, outputCrs, QgsProject.instance())
            for pt in points:
                pt.transform(transformation)

            xValues = [pt.x() for pt in points]
            xMin = round(min(xValues),4)
            xMax = round(max(xValues),4)

            yValues = [pt.y() for pt in points]
            yMin = round(min(yValues),4)
            yMax = round(max(yValues),4)

        else:
            print('else')
            if subsetMode == 'polygon':
                xMin = self.requestXMinPolygon
                xMax = self.requestXMaxPolygon
                yMin = self.requestYMinPolygon
                yMax = self.requestYMaxPolygon
            else:
                xMin = self.requestXMinCanvas
                xMax = self.requestXMaxCanvas
                yMin = self.requestYMinCanvas
                yMax = self.requestYMaxCanvas

        # ToDo: Axis labels are inverted?
        # we need to check if QGIS considers the CRS axes "inverted"
        if outputCrs.hasAxisInverted():
            # e.g. WGS84 or Gauß-Krüger where "north" (y/lat) comes before "east" (x/lon)
            print('inverted')
            subset0 = f"{axisLabel0}({yMin},{yMax})"
            subset1 = f"{axisLabel1}({xMin},{xMax})"
        else:
            # any standard x/y, e/n crs, e. g. UTM
            subset0 = f"{axisLabel0}({xMin},{xMax})"
            subset1 = f"{axisLabel1}({yMin},{yMax})"
        print(subset0, subset1)

        return subset0, subset1

    # ToDo: remove
    def getNativeCoverageCrsUri(self) -> str:
        # the coverage has a bounding box in its original CRS
        # the subsetting coordinates must correspond to this unless a different subsetting CRS is set
        coverageCrsUri = self.describeCov.getBoundingBoxCrsUri()
        if not coverageCrsUri.startswith("http://www.opengis.net/def/crs/"):
            logWarnMessage(f"Trying to adjust {coverageCrsUri} to point to www.opengis.net database")
            coverageCrsUri = switchCrsUriToOpenGis(coverageCrsUri)
        return coverageCrsUri

    def getCovQueryStr(self):
        """Returns a query string for an GetCoverage request with the current dialog settings.

        Raises:
            ValueError: If a OGC URI string could not be created for the map CRS
        """
        version = self.lblVersion.text()

        covId = self.cbCoverage.currentText()
        self.describeCov = self.describeCoverage(covId, version)

        # Map CRS is our QGIS project/canvas CRS: used for setting the extent
        mapCrs = QgsProject.instance().crs()
        # Output CRS must be one of the CRS offered by the service (as OGC URI), chosen by the user in the dialog
        outputCrsUri = self.cbCRS.currentText()

        format = self.cbFormat.currentText()

        if self.cbUseSubset.isChecked():
            subset0, subset1 = self.getSubsets(mapCrs=mapCrs, outputCrsUri=outputCrsUri)
            print('subsets', subset0, subset1)
            params = [
                ('REQUEST', 'GetCoverage'),
                ('SERVICE', 'WCS'),
                ('VERSION', version),
                ('COVERAGEID', covId),
                ('OUTPUTCRS', outputCrsUri),
                ('SUBSETTINGCRS', outputCrsUri),
                ('FORMAT', format),
                ('SUBSET', subset0),
                ('SUBSET', subset1),
            ]
        else:
            params = [
                ('REQUEST', 'GetCoverage'),
                ('SERVICE', 'WCS'),
                ('VERSION', version),
                ('COVERAGEID', covId),
                ('OUTPUTCRS', outputCrsUri),
                ('FORMAT', format)
            ]

        querystring = urllib.parse.urlencode(params)
        print('getcoveragestring', querystring)

        getCoverageUrl = self.capabilities.getGetCoverageUrl()
        getCoverageUrl = self.checkUrlSyntax(getCoverageUrl)
        getCoverageUrlQuery = getCoverageUrl + querystring
        print('getCoverageUrlQuery', getCoverageUrlQuery)

        return getCoverageUrlQuery, covId

    def getCovProgressBar(self):
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        progressMessageBar = iface.messageBar().createMessage("GetCoverage Request")
        progressMessageBar.layout().addWidget(self.progress)
        iface.messageBar().pushWidget(progressMessageBar, Qgis.Info)

    def requestXML(self, url):
        logInfoMessage('Requested URL: ' + url)

        try:
            xmlReponse = urllib.request.urlopen(url)
        except HTTPError as e:
            logWarnMessage(str(e))
            logWarnMessage(str(e.read().decode()))
            openLog()
            return None
        except URLError as e:
            logWarnMessage(str(e))
            logWarnMessage(str(e.read().decode()))
            openLog()
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
        if len(self.leUrl.text()) > 0:
            self.btnGetCapabilities.setEnabled(True)
        else:
            self.btnGetCapabilities.setEnabled(False)

    def enableBtnGetCoverage(self):
        self.btnGetCoverage.setEnabled(True)

    def addRLayer(self, exception, result=None):
        """
        Add the response layer to MapCanvas
        Works only with QgsTask if this function is global...
        :param exception: useless
        :param values: filepath and coverage as string, set to None by default
        :return:
        """

        if exception:
            raise exception

        if result:
            rlayer = QgsRasterLayer(result['file'], result['coverage'], 'gdal')
            QgsProject.instance().addMapLayer(rlayer)
        else:
            openLog()
            logWarnMessage('Error while loading Coverage!')

        self.enableBtnGetCoverage()
        iface.messageBar().clearWidgets()


def logInfoMessage(msg):
    QgsMessageLog.logMessage(msg, logheader, Qgis.Info)


def logWarnMessage(msg):
    QgsMessageLog.logMessage(msg, logheader, Qgis.Warning)


def openLog():
    iface.mainWindow().findChild(QDockWidget, 'MessageLog').show()


def getCoverage(task, url, covId):

    #file = sendRequest(url)
    logInfoMessage('Requested URL: ' + url)

    try:
        file, header = urllib.request.urlretrieve(url)
    except HTTPError as e:
        logWarnMessage(str(e))
        logWarnMessage(str(e.read().decode()))
        return None
    except URLError as e:
        logWarnMessage(str(e))
        logWarnMessage(str(e.read().decode()))
        return None
    return {'file': file, 'coverage': covId}


def sendRequest(request: str) -> str:
    networkManager = QgsNetworkAccessManager.instance()
    request = QNetworkRequest(QUrl(request))
    reply = networkManager.blockingGet(request)
    replyContent = reply.content()
    reply = bytes(replyContent).decode()
    return reply
