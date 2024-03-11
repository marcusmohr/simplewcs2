from collections import OrderedDict
from typing import List
import re
from qgis.core import Qgis, QgsCoordinateReferenceSystem

def getAxisLabels(crsUri: str) -> List[str]:
    crsQgis = QgsCoordinateReferenceSystem.fromOgcWmsCrs(crsUri)
    try:
        # ToDo: try further versions
        crsWktString = crsQgis.toWkt(4)
        return readAxisLabelsAndOrderFromWktString(crsWktString)
    except:
        # ToDo: log message
        return []


def readAxisLabelsAndOrderFromWktString(wktString: str) -> List[str]:

    axisDict = OrderedDict()
    axisList = []
    axis: str = None
    position: int = None
    positionFound = True
    findPosition = False

    wktElements = wktString.split(',')
    for el in wktElements:
        if el.strip().startswith("AXIS"):
            if axis:
                axisList.append(axis)
                if position >= 0:
                    axisDict[position] = axis
                else:
                    positionFound = False
                position = None
            axis = re.findall(r'\(.*?\)', el)
            if axis:
                axis = axis[0][1:-1]
                if axis:
                    findPosition = True
        if findPosition:
            if el.strip().startswith("ORDER"):
                position = re.findall(r'\[.*?\]', el)
                if position:
                    position = position[0][1:-1]
                    if position:
                        try:
                            position = int(position) - 1
                        except:
                            position = None
    if axis:
        axisList.append(axis)
        if position >= 0:
            axisDict[position] = axis
        else:
            positionFound = False

    if positionFound:
        orderedAxisDict = OrderedDict(sorted(axisDict.items()))
        axisList = list(orderedAxisDict.values())

    return axisList


def crsAsOgcUri(crs: QgsCoordinateReferenceSystem) -> str:
    """Returns a OGC URI string representation of the CRS.

    This is only possible if the CRS is a standard OGC or EPSG CRS.

    Raises:
        ValueError: If a OGC URI could not be constructed
    """
    if Qgis.QGIS_VERSION_INT < 33000:
        # - QgsCoordinateReferenceSystem.toOgcUri is not available yet
        # - Logic ported from QGIS 3.30's qgscoordinatereferencesystem.cpp,
        # - Note: Versions are ignored, just like in the native QGIS function:
        #   https://qgis.org/pyqgis/3.30/core/QgsCoordinateReferenceSystem.html#crs-definition-formats
        crsAuth, crsId = crs.authid().split(":")
        if crsAuth == "EPSG":
            ogcUri = f"http://www.opengis.net/def/crs/EPSG/0/{crsId}"
        elif crsAuth == "OGC":
            ogcUri = f"http://www.opengis.net/def/crs/OGC/1.3/{crsId}"
        else:
            raise ValueError("Project CRS must be OGC or EPSG.")
    else:
        ogcUri = crs.toOgcUri()
        if not ogcUri:
            raise ValueError("Project CRS must be OGC or EPSG.")
    return ogcUri


def switchCrsUriToOpenGis(crsUri: str) -> str:
    """Changes a OGC CRS URI to reference the database at opengis.net.

    The namespaces "AUTO", "COSMO", "EPSG", "IAU" and "OGC" are supported.

    This is to fix misconfigured WCS servers, e.g. those that followed
    the rasdaman documentation too closely and specify "localhost:8080".
    It can also be used to "fix" URIs that reference a database on the
    service' server itself, e. g. http://example.com/def/crs/EPSG/0/4326

    >>> switchCrsUriToOpenGis("http://localhost:8080/rasdaman/def/crs/EPSG/0/25832")
    "http://www.opengis.net/def/crs/EPSG/0/25832"
    """
    if crsUri.startswith("http://www.opengis.net/def/crs/"):
        # it's already ok
        return crsUri

    crs = crsUri.split("/def/crs/")[1]

    # opengis.net hosts the following namespaces as of 2023-06:
    if not crs.startswith(("AUTO", "COSMO", "EPSG", "IAU", "OGC")):
        return crsUri

    return f"http://www.opengis.net/def/crs/{crs}"
