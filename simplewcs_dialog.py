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
from typing import List, Optional, Tuple
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
                       QgsProcessingUtils,
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


# GENERATED_CLASS contains the setupUi method and sets up all elements defined in the .ui file
# BASE is the used base widget (here QDialog)
GENERATED_CLASS, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'simplewcs_dialog_base.ui'))

wcs_ns = '{http://www.opengis.net/wcs/2.0}'


class SimpleWCSDialog(BASE, GENERATED_CLASS):
    """
    Dialog for wcs plugin and functionalities to request capabilities,
    describe coverage and get coverage
    """

    def __init__(self) -> None:
        """ Initializes the dialog and attributes, sets up ui elements inside the dialog, ESC Key and connects signals. """
        super().__init__(iface.mainWindow())

        # Subset coordinates (polygon mode)
        self.requestXMinPolygon: Optional[float] = None
        self.requestYMinPolygon: Optional[float] = None
        self.requestXMaxPolygon: Optional[float] = None
        self.requestYMaxPolygon: Optional[float] = None

        # Subset coordinates (canvas mode)
        self.requestXMinCanvas: Optional[float] = None
        self.requestYMinCanvas: Optional[float] = None
        self.requestXMaxCanvas: Optional[float] = None
        self.requestYMaxCanvas: Optional[float] = None

        self.coverageBoundingBox: Optional[BoundingBox] = None
        self.subsetBoundingBox: Optional[BoundingBox] = None

        self.capabilities: Optional[Capabilities] = None
        self.describeCov: Optional[DescribeCoverage] = None

        self.sketchingToolAction: Optional[QAction] = None

        self.mapCrs: str = self.getMapCrs()

        self.acceptedWcsVersions = ['2.1.0', '2.0.1', '2.0.0']

        self.setupUi(self)

        self.setupKey()

        self.connectSignals()

    def showEvent(self, event) -> None:
        """
        Adjusts the "Get Coverage" tab (crs dropdown, etc.)
        and the extent bounding box to the current coverage (if set),
        when the gui is shown.
        """
        self.adjustCovTabToCovIdAndCreateBB()

    def setupUi(self, widget: QDialog) -> None:
        """
        Adds ui Elements from GENERATED_CLASS to the dialog,
        creates a message bar inside the dialog and sets up  "URL and "GetCoverage" tab.
        """
        super().setupUi(widget)

        # Create a messageBar within the plugin gui
        self.messageBar = QgsMessageBar(self)
        self.layout().insertWidget(0, self.messageBar)
        self.messageBar.hide()

        self.setupUrlTab()

        self.setupGetCoverageTab()

    def setupUrlTab(self) -> None:
        """
        Sets up "URL" tab:
        Adds currently accepted wcs versions and disables "Get Capabilities" button.
        """
        self.cbVersion.addItems(self.acceptedWcsVersions)
        self.cbVersion.setCurrentIndex(1)
        self.btnGetCapabilities.setEnabled(False)

    def setupGetCoverageTab(self) -> None:
        """
        Sets up "Get Coverage" Tab:
        Adds elements for subset request functionality.
        """
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

    def connectSignals(self) -> None:
        self.leBaseUrl.textChanged.connect(self.enableBtnGetCapabilities)
        self.btnGetCapabilities.clicked.connect(self.adjustGetCoverageAndInformationTabsToService)

        self.cbCoverage.currentIndexChanged.connect(self.adjustCovTabToCovIdAndCreateBB)
        self.cbUseSubset.stateChanged.connect(self.showAndHideSubsetExtentWidget)
        self.cbSetExtentMode.currentIndexChanged.connect(self.adjustCovTabToSubsetExtentMode)
        self.sketchingToolAction.triggered.connect(self.startSketchingTool)

        iface.mapCanvas().extentsChanged.connect(self.setSubsetExtentLabelFromMapCanvas)
        QgsProject.instance().crsChanged.connect(self.adjustBoundingBoxesToCrsIfVisible)
        QgsProject.instance().crsChanged.connect(self.adjustMapCrsAndLabelForSubsetExtent)

        self.btnGetCoverage.clicked.connect(self.getCovTask)

    def adjustBoundingBoxesToCrsIfVisible(self) -> None:
        """
        Slot called when the crs of the project has changed:
        if the plugin dialog is open, the coverage bounding box is relaoded
        and the subset bounding box is cleared.
        """
        if self.isVisible():
            self.clearBoundingBoxes()
            self.adjustCovTabToCovIdAndCreateBB()

    def setupKey(self) -> None:
        """ Modifies ESC key so that the plugin is reset. """
        escKey = QShortcut(QKeySequence("ESC"), self)
        escKey.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escKey.activated.connect(self.closeGui)
        escKey.setEnabled(True)

    def showAndHideSubsetExtentWidget(self) -> None:
        """Shows and hides widget for subset functionality. """
        subsetModeIsActivated = self.cbUseSubset.isChecked()
        if subsetModeIsActivated:
            self.wgMapExtent.show()
        else:
            self.wgMapExtent.hide()

    def fillSubsetExtentModeCombo(self) -> None:
        """Adds two options for subsetting to the dropdown menu"""
        self.cbSetExtentMode.addItem("Get extent from map canvas", "canvas")
        self.cbSetExtentMode.addItem("Draw polygon", "polygon")

    def adjustCovTabToSubsetExtentMode(self) -> None:
        """Adjusts subset widget to either polygon or canvas mode"""
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

    def adjustMapCrsAndLabelForSubsetExtent(self) -> None:
        """Stores current map crs. Retrieves current extent from map canvas and shows it in GUI"""
        self.mapCrs = self.getMapCrs()
        self.setSubsetExtentLabelFromMapCanvas()

    def setSubsetExtentLabelFromMapCanvas(self) -> None:
        """Retrieves current map extent, stores coordinates and sets the subset label"""
        mapExtent = iface.mapCanvas().extent()
        self.requestXMinCanvas = mapExtent.xMinimum()
        self.requestYMinCanvas = mapExtent.yMinimum()
        self.requestXMaxCanvas = mapExtent.xMaximum()
        self.requestYMaxCanvas = mapExtent.yMaximum()
        extentLabel = f"{round(self.requestXMinCanvas, 5)}, {round(self.requestYMinCanvas, 5)}, {round(self.requestXMaxCanvas, 5)}, {round(self.requestYMaxCanvas, 5)}\n(Map crs: {self.mapCrs})"
        self.lblExtentMapCanvas.setText(extentLabel)

    def getMapCrs(self) -> str:
        """Returns id of current map crs (e.g. 'EPSG:25832')."""
        return QgsProject.instance().crs().authid()

    def startSketchingTool(self) -> None:
        """Creates and sets sketching tool as map tool."""
        self.sketchTool = DrawPolygon()
        self.sketchTool.sketchFinished.connect(self.onSketchFinished)
        iface.mapCanvas().setMapTool(self.sketchTool)

    def stopSketchingTool(self) -> None:
        """Unsets sketching tool as map tool and unchecks tool button."""
        iface.mapCanvas().unsetMapTool(self.sketchTool)
        self.sketchTool.deactivate()
        self.sketchingToolAction.setChecked(False)

    def onSketchFinished(self, geom: QgsGeometry) -> None:
        """
        Stops sketching tool. Receives drawn polygon geometry and
        sets subset bounding box to extent of the polygon.
        """
        self.stopSketchingTool()
        if not geom.isGeosValid():
            errorMessage = "Drawn polygon has no valid geometry"
            self.writeToPluginMessageBar(errorMessage,
                                         level=Qgis.Warning)
            return
        if not self.subsetBoundingBox:
            self.subsetBoundingBox = BoundingBox('request_extent')
        rectBB = self.subsetBoundingBox.setBoundingBoxFromPolygon(geom)
        self.setPolygonSubset(rectBB)

    def setPolygonSubset(self, rectBB: QgsRectangle) -> None:
        """Stores subset coordinates and adjusts label showing the extent."""
        self.setPolygonSubsetCoordinates(rectBB)
        self.setPolygonSubsetLabel()

    def setPolygonSubsetCoordinates(self, rectBB: QgsRectangle) -> None:
        """Stores subset coordinates."""
        self.requestXMaxPolygon = rectBB.xMaximum()
        self.requestYMaxPolygon = rectBB.yMaximum()
        self.requestXMinPolygon = rectBB.xMinimum()
        self.requestYMinPolygon = rectBB.yMinimum()

    def setPolygonSubsetLabel(self) -> None:
        """ Adjusts subset label."""
        self.lblExtentPolygon.setText(
            f"{round(self.requestXMinPolygon, 5)},"
            f"{round(self.requestYMinPolygon, 5)},"
            f"{round(self.requestXMaxPolygon, 5)},"
            f"{round(self.requestYMaxPolygon, 5)}"
            f"\n(Map crs: {self.mapCrs})")

    def requestAndReadCapabilities(self) -> bool:
        """
        Returns False, if capabilities of a wcs service could not be read.
        Raises:
        - CapabilitiesException
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
            self.capabilities = None
            return False

    def getWcsVersion(self) -> str:
        """
        Reads the wcs version from the plugin gui (given by the user)
        and compares it with the versions offered by the service:
        - checks if the wcs version indicated by the user in the plugin gui is supported
        by the wcs service.
        - if not, it is then checked if the service provides another version, supported by the plugin.
        If so, the newest version is chosen.
        - else, None is returned
        """
        wcsVersion = self.cbVersion.currentText()

        if wcsVersion in self.capabilities.versions:
            return wcsVersion
        else:
            for alternativeVersion in self.capabilities.versions:
                # Take the highest available version
                if alternativeVersion in self.acceptedWcsVersions:
                    logInfoMessage(
                        f"WCS {wcsVersion} is not supported by the service, {alternativeVersion } is used instead")
                    return alternativeVersion
        return None

    def adjustGetCoverageAndInformationTabsToService(self) -> None:
        """
        Retrieves the capabilities of the service.
        If the capabilities could be retrieved successfully and a wcs version supported by the plugin is found,
        describeCoverage is requested for all available coverage.
        The tab 'Get Coverage' is enabled and adjusted to the service and the coverages provided by the service.
        """
        self.cleanCoverageAndInformationTab()

        capabilitiesRead = self.requestAndReadCapabilities()
        if not capabilitiesRead:
            return

        wcsVersion = self.getWcsVersion()
        if not wcsVersion:
            self.writeToPluginMessageBar(f'Service does not support one of the following Versions: {", ".join(self.acceptedWcsVersions)}',
                                         level=Qgis.Warning)
            logWarnMessage(
                f'Service does not support one of the following Versions: {", ".join(self.acceptedWcsVersions)}')
            return

        describeCoverageRead = self.requestAndReadDescribeCoverage(wcsVersion)
        if not describeCoverageRead:
            return

        self.setCoverageAndInformationTab(wcsVersion)

    def requestAndReadDescribeCoverage(self, wcsVersion: str) -> bool:
        """
        Requests DescribeCoverage of the service.
        Raises:
        - DescribeCoverageException
        - NotImplementedError
        """
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
            self.capabilities = None
            self.describeCov = None
            return False

    def cleanCoverageAndInformationTab(self) -> None:
        """Removes information from getCapabilities and describeCoverage from both tabs"""
        self.cleanGetCoverageTab()
        self.cleanInformationTab()

    def setCoverageAndInformationTab(self, wcsVersion: str) -> None:
        """Writes information from getCapabilities and describeCoverage to both tabs"""
        self.setGetCoverageTab(wcsVersion)
        self.setInformationTab()

    def setGetCoverageTab(self, version: str) -> None:
        """
        Collects information about the wcs and shows it in the dialog
        - supports only tiff and geotiff at the moment!
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

    def setInformationTab(self) -> None:
        """Adjusts information tab to capabilities information of a service"""
        self.tabInformation.setEnabled(True)

        self.lblProvider.setText(self.capabilities.provider)

        self.lblFees.setText(self.capabilities.fees)

        self.lblConstraints.setText(self.capabilities.constraints)

    def requestCapabilities(self, version: str, baseUrl: str) -> ET.ElementTree:
        """
        Requests capabilities of the service.
        Raises:
            CapabilitiesException, if any error occurs and the response is not a capabilities document
        """

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
        """Creates a string to request describeCoverage of all available coverages of the service"""
        covIdsString = ','.join(covIds)
        params = {"REQUEST": "DescribeCoverage",
                  "SERVICE": "WCS",
                  "VERSION": version,
                  "COVERAGEID": covIdsString}
        queryString = urllib.parse.urlencode(params)
        describeCoverageUrl = self.capabilities.describeCoverageUrl
        url = self.checkUrlSyntax(describeCoverageUrl)

        return url + queryString

    def requestDescribeCoverage(self, covIds: List[str], version: str) -> DescribeCoverage:
        """
        Requests describe coverage information of all coverages provided by the servce.
        Raises:
            DescribeCoverageException, if any error occurs and the response is not a descrive coverage document
        """
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

    def buildCapabilitiesRequest(self, version: str, baseUrl: str) -> str:
        """ Creates a string to request the capabilities of a a service"""
        params = {"REQUEST": "GetCapabilities",
                  "SERVICE": "WCS",
                  "Version": version}
        queryString = urllib.parse.urlencode(params)
        baseUrl = self.checkUrlSyntax(baseUrl)
        capabilitiesRequest = baseUrl + queryString

        return capabilitiesRequest

    def cleanGetCoverageTab(self) -> None:
        """ Clears all capabilities and describe coverage information from getCoverage tab"""
        self.tabGetCoverage.setEnabled(False)
        self.lblTitle.setText('<no service loaded>')
        self.lblVersion.setText('<no service loaded>')
        self.cbCoverage.clear()
        self.cbCrs.clear()
        self.cbFormat.clear()
        self.btnGetCoverage.setEnabled(False)
        self.lblExtentMapCanvas.setText('<no service loaded>')
        self.lblExtentPolygon.setText('<no service loaded>')

    def cleanInformationTab(self) -> None:
        """ Clears all capabilities information from information tab"""
        self.tabInformation.setEnabled(False)
        self.lblProvider.setText('<no service loaded>')
        self.lblFees.setText('<no service loaded>')
        self.lblConstraints.setText('<no service loaded>')

    def adjustCovTabToCovIdAndCreateBB(self) -> None:
        """
        Resets the "Get Coverage" tab if a coverage is chosen from the dropdown menu:
        - Creates or resets the bounding box showing the extent of the coverage.
        - Adds available crs to the dropdown menus (native crs is marked by a *).

        Uses information from the capabilities and describe coverage responses.
        The method is also called when the project's crs has changed.
        """
        self.cbCrs.clear()
        self.cbSubsetCrs.clear()

        covId = self.cbCoverage.currentText()

        if covId:
            coverageInformation = self.describeCov.coverageInformation[covId]
            self.cbCrs.addItem(f'{coverageInformation.nativeCrs}*', coverageInformation.nativeCrs)
            self.cbSubsetCrs.addItem(f'{coverageInformation.nativeCrs}*', coverageInformation.nativeCrs)
            for crs in self.capabilities.crsx:

                if crs != coverageInformation.nativeCrs:
                    self.cbCrs.addItem(crs, crs)
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

    def closeGui(self) -> None:
        """ Clears the bounding boxes and closes the dialog."""
        self.clearBoundingBoxes()
        self.close()

    def closeEvent(self, event) -> None:
        """ Triggered when the dialog is closed."""
        self.closeGui()

    def clearBoundingBoxes(self) -> None:
        """Clears the geometry of the bounding boxes and clears the subset coordinates."""
        self.clearCoverageBoundingBox()
        self.clearSubsetBoundingBox()

    def clearCoverageBoundingBox(self) -> None:
        """ Clears the coverage extent bounding box """
        if self.coverageBoundingBox:
            self.coverageBoundingBox.clearBoundingBox()

    def clearSubsetBoundingBox(self) -> None:
        """ Clears the subset bounding box and clears the coordinates"""
        if self.subsetBoundingBox:
            self.subsetBoundingBox.clearBoundingBox()
            self.lblExtentPolygon.setText("Draw polygon to get extent coordinates")
            self.requestXMinPolygon = None
            self.requestYMinPolygon = None
            self.requestXMaxPolygon = None
            self.requestYMaxPolygon = None

    def getCovTask(self):
        """
        Create an asynchronous QgsTask and add it to the taskManager:
        - Creates getCoverage request string
        - tasks runs function getCoverage
        - on finished self.addRLayer is called
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
                   subsetCrsUri: str) -> Tuple[str, str]:
        """
        Creates the subset string for the get coverage request.

        Retrieval of axislabels:
        - If the native crs of the coverage (from descrive coverage) is the subset crs chosen by the user
        axis labels come from describe coverage response
        - If the subset crs and the native crs differ axis labels are retreived using proj4:
            - If more than 2 or no labels are found, native crs labels are used instead

        Subset coordinates are defined in map crs of qgis project and must be transformed to subset crs

        If subset crs has inverted axis, axis labels order must be switched.
        Optional: User can deactivate the inversion, as some services might not have implemented the inverted axis order.
        """
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
        if not self.cbAxisInversion.isChecked() and subsetCrs.hasAxisInverted():
        #    # e.g. WGS84 or Gauß-Krüger where "north" (y/lat) comes before "east" (x/lon)
            subset0 = f"{axisLabel0}({yMin},{yMax})"
            subset1 = f"{axisLabel1}({xMin},{xMax})"
        else:
        #    # any standard x/y, e/n crs, e. g. UTM
            subset0 = f"{axisLabel0}({xMin},{xMax})"
            subset1 = f"{axisLabel1}({yMin},{yMax})"

        return subset0, subset1

    def getNativeCoverageCrsUri(self) -> str:
        """Retrieves a the native crs of a coverage from describe coverage response."""
        # the coverage has a bounding box in its original CRS
        # the subsetting coordinates must correspond to this unless a different subsetting CRS is set
        coverageCrsUri = self.describeCov.getBoundingBoxCrsUri()
        if not coverageCrsUri.startswith("http://www.opengis.net/def/crs/"):
            logWarnMessage(f"Trying to adjust {coverageCrsUri} to point to www.opengis.net database")
            coverageCrsUri = switchCrsUriToOpenGis(coverageCrsUri)
        return coverageCrsUri

    def getCovQueryStr(self) -> None:
        """
        Returns a query string for an GetCoverage request with the current dialog settings.

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

    def getCovProgressBar(self) -> None:
        """Creates a progress bar for the getCoverage task and adds it to the qgis gui."""
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        progressMessageBar = iface.messageBar().createMessage("GetCoverage Request")
        progressMessageBar.layout().addWidget(self.progress)
        iface.messageBar().pushWidget(progressMessageBar, Qgis.Info)

    def checkUrlSyntax(self, url: str) -> str:
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

    def enableBtnGetCapabilities(self) -> None:
        """Enables GetCapabilities button if a wcs service url is entered"""
        if len(self.leBaseUrl.text()) > 0:
            self.btnGetCapabilities.setEnabled(True)
        else:
            self.btnGetCapabilities.setEnabled(False)

    def enableBtnGetCoverage(self) -> None:
        self.btnGetCoverage.setEnabled(True)

    def addRLayer(self, exception, result=None) -> None:
        """
        Add the response layer to MapCanvas.
        Works only with QgsTask if this function is global...
        :param exception: useless
        """
        if exception:
            raise exception
        if result:
            newFile = QgsProcessingUtils.generateTempFilename('wcs')
            with open(newFile, 'wb') as fl:
                fl.write(result['file'])
            rlayer = QgsRasterLayer(newFile, result['coverage'], 'gdal')
            QgsProject.instance().addMapLayer(rlayer)

        else:
            openLog()
            logWarnMessage('Error while loading Coverage!')

        self.enableBtnGetCoverage()
        iface.messageBar().clearWidgets()

    def writeToPluginMessageBar(self, msg: str, level=Qgis.Warning, duration=0) -> None:
        self.messageBar.pushMessage(msg, level=level, duration=duration)


def getCoverage(task, urlGetCoverage: str, covId: str) -> dict:
    """Requests get coverage using QgsNetworkAccessManager"""
    logInfoMessage('Requested URL: ' + urlGetCoverage)
    try:
        networkManager = QgsNetworkAccessManager()
        resultGetCoverage = networkManager.blockingGet(QNetworkRequest(QUrl(urlGetCoverage)))
        replyContent = resultGetCoverage.content()
    except HTTPError as e:
        logWarnMessage(str(e))
        logWarnMessage(str(e.read().decode()))
        return None
    except URLError as e:
        logWarnMessage(str(e))
        logWarnMessage(str(e.read().decode()))
        return None
    except:
        return None
    try:
        replyString = bytes(replyContent).decode()
        root = ET.fromstring(replyString)
        coverageXmlMainTag = root.tag
        if 'ExceptionReport' in coverageXmlMainTag:
            return None
    except:
        return {'file': replyContent, 'coverage': covId}


def sendRequest(request: str) -> str:
    networkManager = QgsNetworkAccessManager.instance()
    request = QNetworkRequest(QUrl(request))
    reply = networkManager.blockingGet(request)
    replyContent = reply.content()
    reply = bytes(replyContent).decode()
    return reply
