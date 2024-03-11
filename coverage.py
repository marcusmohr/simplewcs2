"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""

import os.path
import urllib
import xml.etree.ElementTree


class DescribeCoverage:

    def __init__(self, coverage):
        wcs_ns = '{http://www.opengis.net/wcs/2.0}'
        gml_ns = '{http://www.opengis.net/gml/3.2}'
        gmlcov_ns = '{http://www.opengis.net/gmlcov/1.0}'
        swe_ns = '{http://www.opengis.net/swe/2.0}'

        coverageDescription = coverage.find(wcs_ns + 'CoverageDescription')

        envelopeElement = coverageDescription.find(gml_ns + 'boundedBy/' + gml_ns + 'Envelope')
        if envelopeElement is not None:
            print(envelopeElement)
            self.boundingBoxCrsUri = envelopeElement.attrib['srsName']
            if "crs-compound" in self.boundingBoxCrsUri:
                raise NotImplementedError(f"Compound CRS are not supported (yet): {self.boundingBoxCrsUri}")
            # ToDo: necessary? bounding box is retrieved from capabilities
            upperCornerElement = envelopeElement.find(gml_ns + "upperCorner")
            lowerCornerElement = envelopeElement.find(gml_ns + "lowerCorner")
            if upperCornerElement is not None and lowerCornerElement is not None:
                upperCorner = [float(v) for v in upperCornerElement.text.split(" ")]
                lowerCorner = [float(v) for v in lowerCornerElement.text.split(" ")]
                self.boundingBox = lowerCorner + upperCorner
            else:
                # raise error
                pass
            # We only support 2 axes for now  # TODO or can we just ignore non-spatial ones?
            self.axisLabels = envelopeElement.attrib['axisLabels'].split(" ")
            if len(self.axisLabels) > 2:
                raise NotImplementedError(f"More than two axes are not supported (yet): {self.axisLabels}")
        else:
            # ToDo: log Message
            self.boundingBoxCrsUri = None
            self.axisLabels = None

        self.range = []
        coverageDescription = coverage.find(wcs_ns + 'CoverageDescription')
        if coverageDescription is not None:
            for field in coverageDescription.findall('.//' + gmlcov_ns + 'rangeType/' + swe_ns + 'DataRecord/' + swe_ns + 'field'):
                name = field.get('name')
                self.range.append(name)
        else:
            # ToDo: log message
            pass

    def getBoundingBoxCrsUri(self):
        return self.boundingBoxCrsUri

    def getBoundingBox(self):
        return self.boundingBox

    def getAxisLabels(self):
        return self.axisLabels

    def setAxisLabels(self, axisLabels):
        self.axisLabels = axisLabels

    def getRange(self):
        return self.range

    def setRange(self, range):
        self.range = range
