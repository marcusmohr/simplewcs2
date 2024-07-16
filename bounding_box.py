
from dataclasses import dataclass

from qgis.core import (Qgis,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsGeometry,
                       QgsPoint,
                       QgsProject,
                       QgsRectangle)
from qgis.gui import QgsRubberBand
from qgis.utils import iface
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt


@dataclass
class RubberBandStyle:
    PENWIDTH: float
    COLOR: QColor
    RUBBERBANDCOLOR: QColor


rubberBandStyles = {
    'coverage_extent': RubberBandStyle(PENWIDTH=1,
                                       COLOR=QColor(255, 0, 0),
                                       RUBBERBANDCOLOR=QColor(255, 0, 0, 50)),
    'request_extent': RubberBandStyle(PENWIDTH=2,
                                      COLOR=QColor(0, 0, 0),
                                      RUBBERBANDCOLOR=QColor(255, 0, 0, 0))
}


class BoundingBox(QgsRubberBand):

    """Rubberband to represent bounding boxes (defined by either corner coordinates or a polygon sketch)."""

    def __init__(self, mode: str) -> None:
        """
        Intializes and styles the rubberband.
        mode is either
        """
        super().__init__(iface.mapCanvas(), Qgis.GeometryType.Polygon)

        self.setStyle(mode)

    def setStyle(self, mode: str) -> None:
        style = rubberBandStyles[mode]
        self.setWidth(style.PENWIDTH)
        self.setColor(style.COLOR)
        self.setFillColor(style.RUBBERBANDCOLOR)
        self.setLineStyle(Qt.DashLine)

    def clearBoundingBox(self) -> None:
        """ Resets the rubberband to an empty polygon"""
        self.reset(Qgis.GeometryType.Polygon)
        iface.mapCanvas().refresh()

    def setBoundingBoxFromWgsCoordinates(self, x_1: float, y_1: float, x_2: float, y_2: float) -> None:
        """ Calculates a rectangle from wgs84 coordinates and sets the boundingbox rubberband to the geometry of the rectangle"""
        sourceCrs = QgsCoordinateReferenceSystem('EPSG:4326')
        destCrs = QgsProject.instance().crs()
        coordsTransform = QgsCoordinateTransform(sourceCrs, destCrs, QgsProject.instance())

        lowerPoint = QgsPoint(x_1, y_1)
        lowerPoint.transform(coordsTransform)
        upperPoint = QgsPoint(x_2, y_2)
        upperPoint.transform(coordsTransform)

        boundingBoxRectangle = QgsRectangle(lowerPoint.x(), lowerPoint.y(), upperPoint.x(), upperPoint.y())
        geom = QgsGeometry.fromRect(boundingBoxRectangle)
        self.setToGeometry(geom)

        #iface.mapCanvas().refresh()

    def setBoundingBoxFromPolygon(self, geom: QgsGeometry, sourceCrs: QgsCoordinateReferenceSystem=None) -> QgsRectangle:
        """ Calculates a rectangle from the bounding box of a polygon and sets the boundingbox rubberband to the geometry of the rectangle"""
        if sourceCrs:
            destCrs = QgsProject.instance().crs()
            coordsTransform = QgsCoordinateTransform(sourceCrs, destCrs, QgsProject.instance())
            geom.transform(coordsTransform)

        boundingBoxRectangle = geom.boundingBox()
        geomBB = QgsGeometry.fromRect(boundingBoxRectangle)
        self.setToGeometry(geomBB)

        return boundingBoxRectangle
