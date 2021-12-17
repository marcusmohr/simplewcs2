"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""

import os.path, urllib, xml.etree.ElementTree

class Coverage:


    def __init__(self, coverage):
        wcs = '{http://www.opengis.net/wcs/2.0}'
        gml = '{http://www.opengis.net/gml/3.2}'
        gmlcov = '{http://www.opengis.net/gmlcov/1.0}'
        swe = '{http://www.opengis.net/swe/2.0}'

        self.coverage = coverage

        envelope = self.coverage.find(wcs + 'CoverageDescription/' + gml + 'boundedBy/' + gml + 'Envelope')
        if envelope is None:
            envelope = self.coverage.find(wcs + 'CoverageDescription/' + gml + 'boundedBy/' + gml + 'EnvelopeWithTimePeriod')
        self.axisLabels = envelope.attrib['axisLabels'].split(" ")

        self.range = []
        contents = self.coverage.find(wcs + 'CoverageDescription')
        for field in contents.findall('.//' + gmlcov + 'rangeType/' + swe + 'DataRecord/' + swe + 'field'):
            name = field.get('name')
            self.range.append(name)


    def getAxisLabels(self):
        return self.axisLabels


    def setAxisLabels(self, axisLabels):
        self.axisLabels = axisLabels


    def getRange(self):
        return self.range


    def setRange(self, range):
        self.range = range
