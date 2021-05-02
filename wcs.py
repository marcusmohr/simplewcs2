"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007

        Functions are written in mixedCase, see https://docs.qgis.org/testing/en/docs/developers_guide/codingstandards.html
"""

import os.path, urllib, xml.etree.ElementTree

class WCS:


    def __init__(self, capabilities):
        ows = '{http://www.opengis.net/ows/2.0}'
        wcs = '{http://www.opengis.net/wcs/2.0}'
        crs = '{http://www.opengis.net/wcs/crs/1.0}'
        crs_nonstandard = '{http://www.opengis.net/wcs/service-extension/crs/1.0}'
        xlink = '{http://www.w3.org/1999/xlink}'

        self.capabilities = capabilities

        self.describeCoverageUrl = self.capabilities.find(ows + 'OperationsMetadata/' + ows + 'Operation[@name="DescribeCoverage"]/' + ows + 'DCP/' + ows + 'HTTP/' + ows + 'Get').attrib[xlink + 'href']

        self.getCoverageUrl = self.capabilities.find(ows + 'OperationsMetadata/' + ows + 'Operation[@name="GetCoverage"]/' + ows + 'DCP/' + ows + 'HTTP/' + ows + 'Get').attrib[xlink + 'href']

        self.title = self.capabilities.find(ows + 'ServiceIdentification/' + ows + 'Title')

        self.provider = self.capabilities.find(ows + 'ServiceProvider/' + ows + 'ProviderName')

        self.fees = self.capabilities.find(ows + 'ServiceIdentification/' + ows + 'Fees')

        self.constraints = self.capabilities.find(ows + 'ServiceIdentification/' + ows + 'AccessConstraints')

        self.versions = []
        contents = self.capabilities.find(ows + 'ServiceIdentification')
        for version in contents.findall('.//' + ows + 'ServiceTypeVersion'):
            self.versions.append(version.text)

        self.crsx = []
        contents = self.capabilities.find(wcs + 'ServiceMetadata')
        for crs in contents.findall('.//' + wcs + 'Extension/' + crs + 'CrsMetadata/' + crs + 'crsSupported'):
            self.crsx.append(crs.text)

        # in case of wrong crs extension implementation
        if not self.crsx:
            contents = self.capabilities.find(wcs + 'ServiceMetadata')
            for crs in contents.findall('.//' + wcs + 'Extension/' + crs_nonstandard + 'crsSupported'):
                self.crsx.append(crs.text)

        self.formats = []
        contents = self.capabilities.find(wcs + 'ServiceMetadata')
        for format in contents.findall('.//' + wcs + 'formatSupported'):
            self.formats.append(format.text)

        self.covIds = []
        contents = self.capabilities.find(wcs + 'Contents')
        for coverage in contents.findall('.//' + wcs + 'CoverageSummary/' + wcs + 'CoverageId'):
            self.covIds.append(coverage.text)


    def getTitle(self):
        return self.title.text


    def setTitle(self, title):
        self.title = title


    def getProvider(self):
        return self.provider.text


    def setProvider(self, provider):
        self.provider = provider


    def getFees(self):
        return self.fees.text


    def setFees(self, fees):
        self.fees = fees


    def getConstraints(self):
        return self.constraints.text


    def setConstraints(self, constraints):
        self.constraints = constraints


    def getDescribeCoverageUrl(self):
        return self.describeCoverageUrl


    def setDescribeCoverageUrl(self, describeCoverageUrl):
        self.describeCoverageUrl = describeCoverageUrl


    def getGetCoverageUrl(self):
        return self.getCoverageUrl


    def setGetCoverageUrl(self, getCoverageUrl):
        self.getCoverageUrl = getCoverageUrl


    def getVersions(self):
        return self.versions


    def setVersions(self, versions):
        self.versions = versions


    def getCRS(self):
        return self.crsx


    def setCRS(self, crs):
        self.crs = crs


    def getFormats(self):
        return self.formats


    def setFormats(self, formats):
        self.formats = formats


    def getCoverageIds(self):
        return self.covIds


    def setCoverageIds(self, covIds):
        self.covIds = covIds
