"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Marcus Mohr (LGB)
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""
import os
import urllib
import xml.etree.ElementTree as ET
from typing import List
from urllib.error import HTTPError, URLError

from qgis.PyQt.QtCore import (Qt,
                              QUrl,)
from qgis.PyQt.QtGui import (QAction,
                             QKeySequence,)
from qgis.PyQt.QtWidgets import QShortcut

from qgis.core import (QgsApplication,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsGeometry,
                       QgsNetworkAccessManager,
                       QgsPoint,
                       QgsProject,
                       Qgis,
                       QgsTask,
                       QgsRasterLayer,
                       QgsRectangle,
                       QgsRasterLayer,)
from qgis.gui import QgsMessageBar
from qgis.utils import iface

from qgis.PyQt import uic
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.PyQt.QtWidgets import (QDialog,
                                 QProgressBar,)

from .resources import *  # magically sets up icon etc...
from .capabilities import Capabilities
from .coverage import DescribeCoverage
from .bounding_box import BoundingBox
from .draw_polygon import DrawPolygon
from .crs_utils import crsAsOgcUri, getAxisLabels, switchCrsUriToOpenGis
from .helpers import openLog, logWarnMessage, logInfoMessage
from .custom_exceptions import CapabilitiesException, DescribeCoverageException


# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'simplewcs_dialog_base.ui'))

wcs_ns = '{http://www.opengis.net/wcs/2.0}'

class SimpleWCSDialog(QDialog, FORM_CLASS):

    def __init__(self, parent=None):

        super(SimpleWCSDialog, self).__init__(parent)

        # Subset coordinates (polygon mode)
        self.requestXMinPolygon: float
        self.requestYMinPolygon: float
        self.requestXMaxPolygon: float
        self.requestYMaxPolygon: float

        # Subset coordinates (canvas mode)
        self.requestXMinCanvas: float
        self.requestYMinCanvas: float
        self.requestXMaxCanvas: float
        self.requestYMaxCanvas: float

        self.coverageBoundingBox: BoundingBox = None
        self.subsetBoundingBox: BoundingBox = None

        self.capabilities: Capabilities = None
        self.describeCov: DescribeCoverage=None

        self.sketchingToolAction: QAction = None

        self.mapCrs: str = self.getMapCrs()

        self.acceptedVersions = ['2.1.0', '2.0.1', '2.0.0']

        self.setupUi(self)

        self.setupKey()

        self.connectSignals()

    def showEvent(self, event):
        """
        Adjusts the Get Coverage Tab (Crs Dropdown, etc.)
        and the extent Bounding Box to the current coverage (if set),
        when the gui is shown.
        """
        self.adjustCovTabToCovIdAndCreateBB()

    def setupUi(self, widget):

        super().setupUi(widget)

        # Create a messageBar within the plugin gui
        self.messageBar = QgsMessageBar(self)
        self.layout().insertWidget(0, self.messageBar)
        self.messageBar.hide()

        self.setupUrlTab()

        self.setupGetCoverageTab()

    def setupUrlTab(self):
        self.cbVersion.addItems(self.acceptedVersions)
        self.cbVersion.setCurrentIndex(1)
        self.btnGetCapabilities.setEnabled(False)

    def setupGetCoverageTab(self):

        self.cbUseSubset.setChecked(True)
        self.showAndHideSubsetExtentWidget()

        self.fillSubsetExtentModeCombo()
        self.adjustCovTabToSubsetExtentMode()

        # Create sketch tool to retrieve extent of the request from a polygon
        self.sketchingToolAction = QAction()
        self.sketchingToolAction.setIcon(QgsApplication.getThemeIcon('/mActionAddPolygon.svg'))
        self.sketchingToolAction.setToolTip('Draw a polygon on the canvas')
        self.sketchingToolAction.setCheckable(True)
        self.tbDrawPolygon.setDefaultAction(self.sketchingToolAction)

        self.btnGetCoverage.setEnabled(False)

    def connectSignals(self):

        self.leBaseUrl.textChanged.connect(self.enableBtnGetCapabilities)
        self.btnGetCapabilities.clicked.connect(self.adjustTabsToService)

        self.cbCoverage.currentIndexChanged.connect(self.adjustCovTabToCovIdAndCreateBB)
        self.cbUseSubset.stateChanged.connect(self.showAndHideSubsetExtentWidget)
        self.cbSetExtentMode.currentIndexChanged.connect(self.adjustCovTabToSubsetExtentMode)
        iface.mapCanvas().extentsChanged.connect(self.setSubsetExtentLabelFromMapCanvas)
        self.sketchingToolAction.triggered.connect(self.startSketchingTool)
        QgsProject.instance().crsChanged.connect(self.adjustBoundingBoxesToCrsIfVisible)
        QgsProject.instance().crsChanged.connect(self.adjustMapCrsLabelForSubsetExtent)

        self.btnGetCoverage.clicked.connect(self.getCovTask)

    def adjustBoundingBoxesToCrsIfVisible(self):
        if self.isVisible():
            self.clearBoundingBoxes()
            self.adjustCovTabToCovIdAndCreateBB()

    def setupKey(self):
        """ Modify ESC key so that plugin is reset"""
        escKey = QShortcut(QKeySequence("ESC"), self)
        escKey.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escKey.activated.connect(self.resetPlugin)
        escKey.setEnabled(True)

    def showAndHideSubsetExtentWidget(self):
        subsetModeIsActivated = self.cbUseSubset.isChecked()
        if subsetModeIsActivated:
            self.wgMapExtent.show()
        else:
            self.wgMapExtent.hide()

    def fillSubsetExtentModeCombo(self):
        self.cbSetExtentMode.clear()
        self.cbSetExtentMode.addItem("Get extent from map canvas", "canvas")
        self.cbSetExtentMode.addItem("Draw polygon", "polygon")

    def adjustCovTabToSubsetExtentMode(self):
        extentMode = self.cbSetExtentMode.currentData()
        if extentMode == "canvas":
            if self.subsetBoundingBox:
                self.subsetBoundingBox.reset()
            self.tbDrawPolygon.hide()
            self.lblExtentMapCanvas.show()
            self.lblExtentPolygon.hide()
            self.lblExtentPolygon.setText("Draw polygon to get extent coordinates")
        elif extentMode == "polygon":
            self.tbDrawPolygon.show()
            self.lblExtentMapCanvas.hide()
            self.lblExtentPolygon.show()

    def adjustMapCrsLabelForSubsetExtent(self):
        self.mapCrs = self.getMapCrs()
        self.setSubsetExtentLabelFromMapCanvas()

    def getMapCrs(self) -> str:
        return QgsProject.instance().crs().authid()

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
            errorMessage = "Drawn polygon has no valid geometry"
            self.writeToPluginMessageBar(errorMessage,
                                         level=Qgis.Warning)
            return
        if not self.subsetBoundingBox:
            self.subsetBoundingBox = BoundingBox('request_extent')
        rectBB = self.subsetBoundingBox.setBoundingBoxPolygon(geom)
        self.setPolygonSubset(rectBB)

    def setPolygonSubset(self, rectBB: QgsRectangle):
        self.setPolygonSubsetCoordinates(rectBB)
        self.setPolygonSubsetLabel()

    def setPolygonSubsetCoordinates(self, rectBB: QgsRectangle):
        self.requestXMaxPolygon = rectBB.xMaximum()
        self.requestYMaxPolygon = rectBB.yMaximum()
        self.requestXMinPolygon = rectBB.xMinimum()
        self.requestYMinPolygon = rectBB.yMinimum()

    def setPolygonSubsetLabel(self):
        self.lblExtentPolygon.setText(
            f"{round(self.requestXMinPolygon, 5)}, {round(self.requestYMinPolygon, 5)}, {round(self.requestXMaxPolygon, 5)}, {round(self.requestYMaxPolygon, 5)}\n(Map crs: {self.mapCrs})")

    def requestAndReadCapabilities(self) -> bool:
        """
        Returns False, if capabilities could not be read
        """
        baseUrl = self.leBaseUrl.text()
        wcsVersion = self.cbVersion.currentText()
        try:
            capabilitiesXmlResponse = self.requestCapabilities(version=wcsVersion, baseUrl=baseUrl)
            self.capabilities = Capabilities(capabilitiesXmlResponse)
            return True
        except CapabilitiesException as e:
            errorMessage = e.args[0]
            self.writeToPluginMessageBar(errorMessage,
                                         level=Qgis.Warning)
            logWarnMessage(errorMessage)
            return False

    def getWcsVersion(self):
        """ Reads the wcs version from the plugin gui (given by the user)
        and compares it with the versions offered by the service"""
        wcsVersion = self.cbVersion.currentText()
        checkedVersion = self.getCheckedWcsVersion(wcsVersion)
        if not checkedVersion:
            return False
        return checkedVersion

    def adjustTabsToService(self):

        """
        Retrieves the capabilities of the service.
        If the capabilities could be retrieved successfully and wcs version supported by the plugin is found,
        describeCoverage is requested for all available coverages and the tab 'Get Coverage' is enabled
        and adjusted to the service and the coverages provided by the service.
        """

        self.cleanCoverageAndInformationTab()

        capabilitiesRead = self.requestAndReadCapabilities()
        if not capabilitiesRead:
            self.capabilities = None
            return

        wcsVersion = self.getWcsVersion()
        if not wcsVersion:
            self.writeToPluginMessageBar(f'Service does not support one of the following Versions: {", ".join(self.acceptedVersions)}',
                                         level=Qgis.Warning)
            logWarnMessage(
                f'Service does not support one of the following Versions: {", ".join(self.acceptedVersions)}')
            return

        describeCoverageRead = self.requestAndReadDescribeCoverage(wcsVersion)
        if not describeCoverageRead:
            self.capabilities = None
            self.describeCov = None
            return

        self.setCoverageAndInformationTab(wcsVersion)

    def requestAndReadDescribeCoverage(self, wcsVersion: str) -> bool:

        covIds = self.capabilities.coverageSummary.keys()
        try:
            describeCoverageXmlResponse = self.requestDescribeCoverage(covIds, wcsVersion)
            self.describeCov = DescribeCoverage(describeCoverageXmlResponse)
            return True
        except (DescribeCoverageException, NotImplementedError) as e:
            errorMessage = e.args[0]
            self.writeToPluginMessageBar(errorMessage,
                                         level=Qgis.Warning)
            logWarnMessage(errorMessage)
            return False

    def getCheckedWcsVersion(self, version: str) -> str:

        """
        Checks if the wcs version indicated by the user in the plugin gui is supported
        by the wcs service.
        If not it is checked if the service provides an other version, supported by the plugin. If so, the newest version is chosen.
        If no supported version is provided by the service, None is returned.
        """

        if version in self.capabilities.versions:
            return version
        else:
            for c_version in self.capabilities.versions:
                # Take the highest available version
                if c_version in self.acceptedVersions:
                    logInfoMessage(f"WCS {version} is not supported by the service, {c_version} is used instead")
                    return c_version
        return None

    def cleanCoverageAndInformationTab(self):
        self.cleanGetCoverageTab()
        self.cleanInformationTab()

    def setCoverageAndInformationTab(self, wcsVersion: str):
        self.setGetCoverageTab(wcsVersion)
        self.setInformationTab()

    def setGetCoverageTab(self, version: str):
        """
        Collects information about the wcs and shows them in GUI
        - supports only tiff at the moment!
        """
        self.tabGetCoverage.setEnabled(True)

        self.lblTitle.setText(self.capabilities.title)

        self.lblVersion.setText(version)

        for format in self.capabilities.formats:
            if 'tiff' in format:
                self.cbFormat.addItem(format)

        if any('tiff' in format for format in self.capabilities.formats):
            self.btnGetCoverage.setEnabled(True)
        else:
            self.cbFormat.addItem('no tiff available')
            self.cbFormat.setEnabled(False)

        self.cbCoverage.clear()
        for covId, _ in self.capabilities.coverageSummary.items():
            if covId in self.describeCov.coverageInformation.keys():
                self.cbCoverage.addItem(covId)
        self.adjustCovTabToCovIdAndCreateBB()

        self.setSubsetExtentLabelFromMapCanvas()
        self.lblExtentPolygon.setText("Draw polygon to get extent coordinates")

        self.tabWidget.setCurrentIndex(1)

    def setInformationTab(self):

        self.tabInformation.setEnabled(True)

        self.lblProvider.setText(self.capabilities.provider)

        self.lblFees.setText(self.capabilities.fees)

        self.lblConstraints.setText(self.capabilities.constraints)

    def requestCapabilities(self, version: str, baseUrl: str) -> ET.ElementTree:
        """  Requests capabilities of the service.
        Raises:
            CapabilitiesException, if any error occurs and the response is not a capabilities document"""
        capabilitiesRequest = self.buildCapabilitiesRequest(version=version, baseUrl=baseUrl)
        capabilitiesStr = sendRequest(request=capabilitiesRequest)
        try:
            root = ET.fromstring(capabilitiesStr)
            capabilitiesXmlMainTag = root.tag
            if capabilitiesXmlMainTag != f'{wcs_ns}Capabilities':
                raise CapabilitiesException('Error: Could not read capabilities for this service')
            capabilitiesXml = ET.ElementTree(ET.fromstring(capabilitiesStr))
        except:
            raise CapabilitiesException('Error: Could not read capabilities for this service')
        return capabilitiesXml

    def buildDescribeCoverageRequest(self, covIds: List[str], version: str) -> str:
        covIdsString = ','.join(covIds)
        params = {"REQUEST": "DescribeCoverage", "SERVICE": "WCS", "VERSION": version, "COVERAGEID": covIdsString}
        queryString = urllib.parse.urlencode(params)
        describeCoverageUrl = self.capabilities.describeCoverageUrl
        url = self.checkUrlSyntax(describeCoverageUrl)
        return url + queryString

    def requestDescribeCoverage(self, covIds: List[str], version: str) -> DescribeCoverage:
        """Requests describe coverage information of all coverages provided by the servce.
        Raises:
            DescribeCoverageException, if any error occurs and the response is not a descrive coverage document"""
        coverageRequest = self.buildDescribeCoverageRequest(covIds, version)
        coverageStr = sendRequest(request=coverageRequest)
        try:
            root = ET.fromstring(coverageStr)
            coverageXmlMainTag = root.tag
            if coverageXmlMainTag != f'{wcs_ns}CoverageDescriptions':
                raise DescribeCoverageException('Error: Could not read describeCoverage for this service')
            describeCoverageXml = ET.ElementTree(ET.fromstring(coverageStr))
        except:
            raise DescribeCoverageException('Error: Could not read describeCoverage for this service')

        return describeCoverageXml
        #return DescribeCoverage(describeCoverageXml)

    def buildCapabilitiesRequest(self, version: str, baseUrl: str) -> str:
        params = {"REQUEST": "GetCapabilities", "SERVICE": "WCS", "Version": version}
        queryString = urllib.parse.urlencode(params)
        baseUrl = self.checkUrlSyntax(baseUrl)
        capabilitiesRequest = baseUrl + queryString
        return capabilitiesRequest

    def cleanGetCoverageTab(self):
        self.tabGetCoverage.setEnabled(False)
        self.lblTitle.setText('<no service loaded>')
        self.lblVersion.setText('<no service loaded>')
        self.cbCoverage.clear()
        self.cbCrs.clear()
        self.cbFormat.clear()
        self.btnGetCoverage.setEnabled(False)
        self.lblExtentMapCanvas.setText('<no service loaded>')
        self.lblExtentPolygon.setText('<no service loaded>')

    def cleanInformationTab(self):
        self.tabInformation.setEnabled(False)
        self.lblProvider.setText('<no service loaded>')
        self.lblFees.setText('<no service loaded>')
        self.lblConstraints.setText('<no service loaded>')

    def adjustCovTabToCovIdAndCreateBB(self):

        """
        Resets the get coverage tab if a coverage is chosen in the dropdown menu.
        Creates or resets the bounding box which shows the extent of the coverage.
        The method is also called if the project's crs is changed.
        """

        self.cbCrs.clear()
        self.cbSubsetCrs.clear()

        covId = self.cbCoverage.currentText()

        if covId:

            coverageInformation = self.describeCov.coverageInformation[covId]

            self.cbCrs.addItem(f'{coverageInformation.nativeCrs}*', coverageInformation.nativeCrs)
            for crs in self.capabilities.crsx:
                if crs != coverageInformation.nativeCrs:
                    self.cbCrs.addItem(crs, crs)

            self.cbSubsetCrs.addItem(f'{coverageInformation.nativeCrs}*', coverageInformation.nativeCrs)
            for crs in self.capabilities.crsx:
                self.cbSubsetCrs.addItem(crs, crs)

            # Create bounding box rubber band and set it to coverage extent
            if not self.coverageBoundingBox:
                self.coverageBoundingBox = BoundingBox('coverage_extent')

            self.coverageBoundingBox.clearBoundingBox()
            lowerCorner = self.capabilities.coverageSummary[covId].bbLowerCorner
            upperCorner = self.capabilities.coverageSummary[covId].bbUpperCorner
            if lowerCorner and upperCorner:
                x_1, y_1 = lowerCorner.split(" ")
                x_2, y_2 = upperCorner.split(" ")
                try:
                    x_1 = float(x_1)
                    y_1 = float(y_1)
                    x_2 = float(x_2)
                    y_2 = float(y_2)
                except:
                    warningMessage = 'No bounding box available for this coverage'
                    self.writeToPluginMessageBar(warningMessage)
                    logWarnMessage(warningMessage)
                    return

                self.coverageBoundingBox.setBoundingBoxFromWgsCoordinates(x_1, y_1, x_2, y_2)

            else:
                warningMessage = 'No bounding box available for this coverage'
                self.writeToPluginMessageBar(warningMessage)
                logWarnMessage(warningMessage)


    def resetPlugin(self):
        self.clearBoundingBoxes()
        self.close()

    def closeEvent(self, event):
        self.resetPlugin()

    def clearBoundingBoxes(self):
        self.clearCoverageBoundingBox()
        self.clearSubsetBoundingBox()

    def clearCoverageBoundingBox(self):
        if self.coverageBoundingBox:
            self.coverageBoundingBox.clearBoundingBox()

    def clearSubsetBoundingBox(self):
        if self.subsetBoundingBox:
            self.subsetBoundingBox.clearBoundingBox()
            self.lblExtentPolygon.setText("Draw polygon to get extent coordinates")
            self.requestXMinPolygon = None
            self.requestYMinPolygon = None
            self.requestXMaxPolygon = None
            self.requestYMaxPolygon = None

    def setSubsetExtentLabelFromMapCanvas(self):
        """
        Collect current extent from mapCanvas and shows it in GUI
        """
        mapExtent = iface.mapCanvas().extent()
        self.requestXMinCanvas = mapExtent.xMinimum()
        self.requestYMinCanvas = mapExtent.yMinimum()
        self.requestXMaxCanvas = mapExtent.xMaximum()
        self.requestYMaxCanvas = mapExtent.yMaximum()
        extentLabel = f"{round(self.requestXMinCanvas, 5)}, {round(self.requestYMinCanvas, 5)}, {round(self.requestXMaxCanvas, 5)}, {round(self.requestYMaxCanvas, 5)}\n(Map crs: {self.mapCrs})"
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
                   covId: str,
                   mapCrs: QgsCoordinateReferenceSystem,
                   subsetCrsUri: str):

        """  """

        nativeCrsUri = self.describeCov.coverageInformation[covId].nativeCrs

        if nativeCrsUri == subsetCrsUri:
            axisLabel0, axisLabel1 = self.describeCov.coverageInformation[covId].axisLabels
        else:
            axisList = getAxisLabels(subsetCrsUri)
            if not axisList:
                logInfoMessage(f"Axis labels of subset crs could not be found. Native crs is used as subset crs instead.")
                axisLabel0, axisLabel1 = self.describeCov.coverageInformation[covId].axisLabels
                subsetCrsUri = nativeCrsUri
            elif len(axisList) > 2:
                logWarnMessage(f"More than two axes are not supported (yet): {axisList}")
                axisLabel0, axisLabel1 = self.describeCov.coverageInformation[covId].axisLabels
                subsetCrsUri = nativeCrsUri
            else:
                axisLabel0, axisLabel1 = axisList

        try:
            mapCrsUri = crsAsOgcUri(mapCrs)
        except:
            raise  # re-raise exception

        subsetMode = self.cbSetExtentMode.currentData()

        subsetCrs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(switchCrsUriToOpenGis(subsetCrsUri))

        if mapCrsUri != subsetCrsUri:

            logInfoMessage(f"Transforming extent coordinates from {mapCrsUri} to {subsetCrsUri}")

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

            transformation = QgsCoordinateTransform(mapCrs, subsetCrs, QgsProject.instance())
            for pt in points:
                pt.transform(transformation)

            xValues = [pt.x() for pt in points]
            xMin = min(xValues)
            xMax = max(xValues)

            yValues = [pt.y() for pt in points]
            yMin = min(yValues)
            yMax = max(yValues)

        else:
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



        # we need to check if QGIS considers the CRS axes "inverted"
        if subsetCrs.hasAxisInverted():
            # e.g. WGS84 or Gauß-Krüger where "north" (y/lat) comes before "east" (x/lon)
            subset0 = f"{axisLabel0}({yMin},{yMax})"
            subset1 = f"{axisLabel1}({xMin},{xMax})"
        else:
            # any standard x/y, e/n crs, e. g. UTM
            subset0 = f"{axisLabel0}({xMin},{xMax})"
            subset1 = f"{axisLabel1}({yMin},{yMax})"

        return subset0, subset1

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
        wcsVersion = self.lblVersion.text()

        covId = self.cbCoverage.currentText()

        # Map CRS is our QGIS project/canvas CRS: used for setting the extent
        mapCrs = QgsProject.instance().crs()
        # Output and subset CRS must be one of the CRS offered by the service (as OGC URI), chosen by the user in the dialog
        outputCrsUri = self.cbCrs.currentData()
        subsetCrsUri = self.cbSubsetCrs.currentData()

        format = self.cbFormat.currentText()

        if self.cbUseSubset.isChecked():
            subset0, subset1 = self.getSubsets(covId=covId, mapCrs=mapCrs, subsetCrsUri=subsetCrsUri)
            params = [
                ('REQUEST', 'GetCoverage'),
                ('SERVICE', 'WCS'),
                ('VERSION', wcsVersion),
                ('COVERAGEID', covId),
                ('OUTPUTCRS', outputCrsUri),
                ('SUBSETTINGCRS', subsetCrsUri),
                ('FORMAT', format),
                ('SUBSET', subset0),
                ('SUBSET', subset1),
            ]
        else:
            params = [
                ('REQUEST', 'GetCoverage'),
                ('SERVICE', 'WCS'),
                ('VERSION', wcsVersion),
                ('COVERAGEID', covId),
                ('OUTPUTCRS', outputCrsUri),
                ('FORMAT', format)
            ]

        querystring = urllib.parse.urlencode(params)

        getCoverageUrl = self.checkUrlSyntax(self.capabilities.getCoverageUrl)
        getCoverageUrlQuery = getCoverageUrl + querystring

        return getCoverageUrlQuery, covId

    def getCovProgressBar(self):
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        progressMessageBar = iface.messageBar().createMessage("GetCoverage Request")
        progressMessageBar.layout().addWidget(self.progress)
        iface.messageBar().pushWidget(progressMessageBar, Qgis.Info)

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
        if len(self.leBaseUrl.text()) > 0:
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

    def writeToPluginMessageBar(self, msg: str, level=Qgis.Warning, duration=0):
        self.messageBar.pushMessage(msg, level=level, duration=duration)


def getCoverage(task, url, covId):
    print(url)
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
    except:
        pass
    return {'file': file, 'coverage': covId}


def sendRequest(request: str) -> str:
    networkManager = QgsNetworkAccessManager.instance()
    request = QNetworkRequest(QUrl(request))
    reply = networkManager.blockingGet(request)
    replyContent = reply.content()
    reply = bytes(replyContent).decode()
    return reply
