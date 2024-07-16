from qgis.gui import (QgsMapTool,
                      QgsRubberBand,)
from qgis.core import (Qgis,
                       QgsGeometry,)
from qgis.utils import iface

from qgis.PyQt.QtCore import Qt, QPoint, pyqtSignal
from qgis.PyQt.QtGui import QColor

PENWIDTH = 1
COLOR = QColor(255, 0, 0)
RUBBERBANDCOLOR = QColor(255, 0, 0, 50)

class DrawPolygon(QgsMapTool):

    sketchFinished = pyqtSignal(QgsGeometry)

    def __init__(self):
        self.rubberBand: QgsRubberBand=None
        super().__init__(iface.mapCanvas())

    def resetTool(self):
        if self.rubberBand:
            iface.mapCanvas().scene().removeItem(self.rubberBand)
            self.rubberBand = None

    def deactivate(self):
        self.resetTool()
        QgsMapTool.deactivate(self)

    def canvasPressEvent(self, event):
        pass

    def canvasReleaseEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        thisPoint = QPoint(x, y)

        mapToPixel = iface.mapCanvas().getCoordinateTransform()  # QgsMapToPixel instance

        if event.button() == Qt.LeftButton:
            if not self.rubberBand:
                self.rubberBand = QgsRubberBand(mapCanvas=iface.mapCanvas(), geometryType=Qgis.GeometryType.Polygon)
                self.rubberBand.setLineStyle(Qt.DashLine)
                self.rubberBand.setWidth(PENWIDTH)
                self.rubberBand.setColor(COLOR)
                self.rubberBand.setFillColor(RUBBERBANDCOLOR)
            self.rubberBand.addPoint(mapToPixel.toMapCoordinates(thisPoint))

        elif event.button() == Qt.RightButton:
            if self.rubberBand and self.rubberBand.numberOfVertices() > 3:
                # Finish rubberband sketch
                self.rubberBand.removeLastPoint()
                geometry = self.rubberBand.asGeometry()
                self.sketchFinished.emit(geometry)
            self.resetTool()
            iface.mapCanvas().refresh()

    def canvasMoveEvent(self, event):
        if not self.rubberBand:
            return
        x = event.pos().x()
        y = event.pos().y()
        thisPoint = QPoint(x, y)
        mapToPixel = iface.mapCanvas().getCoordinateTransform()
        self.rubberBand.movePoint(self.rubberBand.numberOfVertices() - 1, mapToPixel.toMapCoordinates(thisPoint))


