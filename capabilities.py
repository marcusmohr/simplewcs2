"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007

        Functions are written in mixedCase, see https://docs.qgis.org/testing/en/docs/developers_guide/codingstandards.html
"""
from dataclasses import dataclass
import os.path
from typing import List, Dict
import urllib
import xml.etree.ElementTree


# TODO is it ok that these use .0 versions?
ows_ns = '{http://www.opengis.net/ows/2.0}'
wcs_ns = '{http://www.opengis.net/wcs/2.0}'
crs_ns = '{http://www.opengis.net/wcs/crs/1.0}'  # was overwritten in loop below!
crs_serviceextension_ns = '{http://www.opengis.net/wcs/service-extension/crs/1.0}'
xlink_ns = '{http://www.w3.org/1999/xlink}'


@dataclass
class CoverageSummary:
    crs: List[str]
    bbLowerCorner: str
    bbUpperCorner: str


class Capabilities:

    def __init__(self, capabilities: xml.etree.ElementTree):

        self.title: str=''
        self.provider: str=''
        self.fees: str=''
        self.constraints: str=''
        self.describeCoverageUrl: str=''
        self.getCoverageUrl: str=''
        self.versions: List[str]=[]
        self.formats: List[str]=[]
        self.coverageSummary: Dict[str, CoverageSummary]

        self.readDataFromCapabilities(capabilities)

    def getTitle(self) -> str:
        return self.title

    def setTitle(self, title: str):
        self.title = title

    def getProvider(self) -> str:
        return self.provider

    def setProvider(self, provider: str):
        self.provider = provider

    def getFees(self) -> str:
        return self.fees

    def setFees(self, fees: str):
        self.fees = fees

    def getConstraints(self) -> str:
        return self.constraints

    def setConstraints(self, constraints: str):
        self.constraints = constraints

    def getDescribeCoverageUrl(self) -> str:
        return self.describeCoverageUrl

    def setDescribeCoverageUrl(self, describeCoverageUrl: str):
        self.describeCoverageUrl = describeCoverageUrl

    def getGetCoverageUrl(self) -> str:
        return self.getCoverageUrl

    def setGetCoverageUrl(self, getCoverageUrl: str):
        self.getCoverageUrl = getCoverageUrl

    def getVersions(self) -> List[str]:
        return self.versions

    def setVersions(self, versions: List[str]):
        self.versions = versions

    def getFormats(self) -> List[str]:
        return self.formats

    def setFormats(self, formats: List[str]):
        self.formats = formats

    def getCoverageSummary(self) -> Dict[str, CoverageSummary]:
        return self.coverageSummary

    def setCoverageSummary(self, coverageSummary: Dict[str, CoverageSummary]):
        self.coverageSummary = coverageSummary

    def readDataFromCapabilities(self, capabilities: xml.etree.ElementTree):

        describeCoverageGetElement = capabilities.find(
            f'{ows_ns}OperationsMetadata/{ows_ns}Operation[@name="DescribeCoverage"]/{ows_ns}DCP/{ows_ns}HTTP/{ows_ns}Get')
        if describeCoverageGetElement is not None:
            self.describeCoverageUrl = describeCoverageGetElement.attrib.get(f'{xlink_ns}href')
            if not self.describeCoverageUrl:
                self.describeCoverageUrl = 'No Information available'
        else:
            # ToDo: Include information
            self.describeCoverageUrl = 'No Information available'

        getCoverageElement = capabilities.find(
            f'{ows_ns}OperationsMetadata/{ows_ns}Operation[@name="GetCoverage"]/{ows_ns}DCP/{ows_ns}HTTP/{ows_ns}Get')
        if getCoverageElement is not None:
            self.getCoverageUrl = getCoverageElement.attrib.get(f'{xlink_ns}href')
            if not self.getCoverageUrl:
                self.getCoverageUrl = 'No Information available'
        else:
            # ToDo: Include information
            self.getCoverageUrl = 'No Information available'

        titleElement = capabilities.find(f'{ows_ns}ServiceIdentification/{ows_ns}Title')
        if titleElement is not None:
            self.title = titleElement.text
        else:
            # ToDo
            self.title = 'No Information available'

        providerElement = capabilities.find(f'{ows_ns}ServiceProvider/{ows_ns}ProviderName')
        if providerElement is not None:
            self.provider = providerElement.text
        else:
            # ToDo
            self.provider = 'No Information available'

        feesElement = capabilities.find(f'{ows_ns}ServiceIdentification/{ows_ns}Fees')
        if feesElement is not None:
            self.fees = feesElement.text
        else:
            # ToDO
            self.fees = 'No Information available'

        constraintsElement = capabilities.find(f'{ows_ns}ServiceIdentification/{ows_ns}AccessConstraints')
        if constraintsElement is not None:
            self.constraint = constraintsElement.text
        else:
            self.constraints = 'No Information available'

        self.versions = []
        serviceIdentificationContents = capabilities.find(f'{ows_ns}ServiceIdentification')
        if serviceIdentificationContents is not None:
            for version in serviceIdentificationContents.findall(f'.//{ows_ns}ServiceTypeVersion'):
                self.versions.append(version.text)
        self.versions.sort(reverse=True)

        self.formats = []
        crsx = []
        serviceMetadataContents = capabilities.find(f'{wcs_ns}ServiceMetadata')
        if serviceMetadataContents is not None:
            for format in serviceMetadataContents.findall(f'.//{wcs_ns}formatSupported'):
                self.formats.append(format.text)

        serviceMetadataContents = capabilities.find(f'{wcs_ns}ServiceMetadata')
        if serviceMetadataContents is not None:
            for crsElement in serviceMetadataContents.findall(f'.//{wcs_ns}Extension/{crs_ns}CrsMetadata/{crs_ns}crsSupported'):
                if crsElement.text:
                    crsx.append(crsElement.text)
            # in case of wrong crs extension implementation
            if not crsx:
                for crsElement in serviceMetadataContents.findall(f'.//{wcs_ns}Extension/{crs_serviceextension_ns}CrsMetadata/{crs_serviceextension_ns}crsSupported'):
                    if crsElement.text:
                        crsx.append(crsElement.text)

        self.coverageSummary = {}
        contents = capabilities.find(f'{wcs_ns}Contents')
        if contents is not None:
            for coverageSummary in contents.findall(f'.//{wcs_ns}CoverageSummary'):
                coverageIdElement = coverageSummary.find(f'.//{wcs_ns}CoverageId')
                if coverageIdElement is None:
                    continue
                coverageId = coverageIdElement.text

                coverageCrsElement = coverageSummary.find(f'.//{ows_ns}BoundingBox')
                if coverageCrsElement is not None:
                    # ToDo: compare crs
                    coverageCrs = coverageCrsElement.attrib.get('crs')
                    if coverageCrs:
                        allCrsx = crsx + [coverageCrs]
                    else:
                        allCrsx = crsx

                coverageBbWgsLowerCornerElement = coverageSummary.find(f'.//{ows_ns}WGS84BoundingBox/{ows_ns}LowerCorner')
                if coverageBbWgsLowerCornerElement is not None:
                    coverageBbWgsLowerCorner = coverageBbWgsLowerCornerElement.text
                else:
                    coverageBbWgsLowerCorner = None
                coverageBbWgsUpperCornerElement = coverageSummary.find(f'.//{ows_ns}WGS84BoundingBox/{ows_ns}UpperCorner')
                if coverageBbWgsUpperCornerElement is not None:
                    coverageBbWgsUpperCorner = coverageBbWgsUpperCornerElement.text
                else:
                    coverageBbWgsUpperCorner = None

                summary = CoverageSummary(crs=allCrsx,
                                          bbLowerCorner=coverageBbWgsLowerCorner,
                                          bbUpperCorner=coverageBbWgsUpperCorner)
                self.coverageSummary[coverageId] = summary


