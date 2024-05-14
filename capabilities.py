"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007

        Functions are written in mixedCase, see https://docs.qgis.org/testing/en/docs/developers_guide/codingstandards.html
"""
from dataclasses import dataclass
from typing import List, Dict
import xml.etree.ElementTree

from .helpers import logWarnMessage
from .custom_exceptions import CapabilitiesException


# TODO is it ok that these use .0 versions?
ows_ns = '{http://www.opengis.net/ows/2.0}'
wcs_ns = '{http://www.opengis.net/wcs/2.0}'
crs_ns = '{http://www.opengis.net/wcs/crs/1.0}'  # was overwritten in loop below!
crs_serviceextension_ns = '{http://www.opengis.net/wcs/service-extension/crs/1.0}'
xlink_ns = '{http://www.w3.org/1999/xlink}'


@dataclass
class BbCorners:
    bbLowerCorner: str
    bbUpperCorner: str


class Capabilities:


    def __init__(self, capabilitiesXmlResponse: xml.etree.ElementTree):

        self.title: str = ''
        self.provider: str = ''
        self.fees: str = ''
        self.constraints: str = ''
        self.describeCoverageUrl: str = ''
        self.getCoverageUrl: str = ''
        self.versions: List[str] = []
        self.formats: List[str] = []
        self.coverageSummary: Dict[str, BbCorners]
        self.crsx: List[str] = []

        self.__initializeFromCapabilitiesResponse(capabilitiesXmlResponse)

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, newTitle: str):
        self._title = newTitle

    @property
    def provider(self) -> str:
        return self._provider

    @provider.setter
    def provider (self, newProvider: str):
        self._provider = newProvider

    @property
    def fees(self) -> str:
        return self._fees

    @fees.setter
    def fees(self, newFees: str):
        self._fees = newFees

    @property
    def constraints(self) -> str:
        return self._constraints

    @constraints.setter
    def constraints(self, newConstraints: str):
        self._constraints = newConstraints

    @property
    def describeCoverageUrl(self) -> str:
        return self._describeCoverageUrl

    @describeCoverageUrl.setter
    def describeCoverageUrl(self, newUrl: str):
        self._describeCoverageUrl = newUrl

    @property
    def getCoverageUrl(self) -> str:
        return self._getCoverageUrl

    @getCoverageUrl.setter
    def getCoverageUrl(self, newUrl):
        self._getCoverageUrl = newUrl

    @property
    def versions(self) -> List[str]:
        return self._versions

    @versions.setter
    def versions(self, newVersions):
        self._versions = newVersions

    @property
    def formats(self) -> List[str]:
        return self._formats

    @formats.setter
    def formats(self, newFormats: List[str]):
        self._formats = newFormats

    @property
    def coverageSummary(self) -> Dict[str, BbCorners]:
        return self._coverageSummary

    @coverageSummary.setter
    def coverageSummary(self, newCoverageSummary: Dict[str, BbCorners]):
        self._coverageSummary = newCoverageSummary

    @property
    def crsx(self) -> List[str]:
        return self._crsx

    @crsx.setter
    def crsx(self, newCrsx: List[str]):
        self._crsx = newCrsx

    def __initializeFromCapabilitiesResponse(self, capabilitiesXmlResponse: xml.etree.ElementTree):

        """
        Raises:
            CapabilitiesException, if ...
        """

        operationsMetadataElement = capabilitiesXmlResponse.find(f'{ows_ns}OperationsMetadata')
        if operationsMetadataElement:
            try:
                self._describeCoverageUrl = operationsMetadataElement.find(f'{ows_ns}Operation[@name="DescribeCoverage"]/{ows_ns}DCP/{ows_ns}HTTP/{ows_ns}Get').attrib.get(f'{xlink_ns}href')
            except:
                logWarnMessage('Error in getCapabilities response: Missing describeCoverage url in <OperationsMetadata>')
                self._describeCoverageUrl = ''
            try:
                self._getCoverageUrl = operationsMetadataElement.find(f'{ows_ns}Operation[@name="GetCoverage"]/{ows_ns}DCP/{ows_ns}HTTP/{ows_ns}Get').attrib.get(f'{xlink_ns}href')
            except:
                logWarnMessage('Error in getCapabilities response: Missing getCoverage url in OperationsMetadata')
                self._getCoverageUrl = ''
        else:
            self._describeCoverageUrl = ''
            self._getCoverageUrl = ''

        titleElement = capabilitiesXmlResponse.find(f'{ows_ns}ServiceIdentification/{ows_ns}Title')
        if titleElement is not None:
            self._title = titleElement.text
        else:
            logWarnMessage('Error in getCapabilities response: title of coverage in Service Identification is missing')
            self._title = 'No information available'

        providerElement = capabilitiesXmlResponse.find(f'{ows_ns}ServiceProvider/{ows_ns}ProviderName')
        if providerElement is not None:
            self._provider = providerElement.text
        else:
            logWarnMessage('Error in getCapabilities response: provider information is missing')
            self._provider = 'No ínformation available'

        feesElement = capabilitiesXmlResponse.find(f'{ows_ns}ServiceIdentification/{ows_ns}Fees')
        if feesElement is not None:
            self._fees = feesElement.text
        else:
            logWarnMessage('Error in getCapabilities response: fees are missing')
            self._fees = 'No onformation available'

        constraintsElement = capabilitiesXmlResponse.find(f'{ows_ns}ServiceIdentification/{ows_ns}AccessConstraints')
        if constraintsElement is not None:
            self._constraint = constraintsElement.text
        else:
            logWarnMessage('Error in getCapabilities response: access constraints are missing')
            self._constraints = 'No information available'

        self._versions = []
        serviceIdentificationContents = capabilitiesXmlResponse.find(f'{ows_ns}ServiceIdentification')
        if serviceIdentificationContents is not None:
            for version in serviceIdentificationContents.findall(f'.//{ows_ns}ServiceTypeVersion'):
                self._versions.append(version.text)
        self._versions.sort(reverse=True)
        if not self._versions:
            logWarnMessage('Error in getCapabilities response: no information about versions found')

        self._formats = []
        self._crsx = []
        serviceMetadataContents = capabilitiesXmlResponse.find(f'{wcs_ns}ServiceMetadata')
        if serviceMetadataContents is not None:
            for format in serviceMetadataContents.findall(f'.//{wcs_ns}formatSupported'):
                self._formats.append(format.text)
        if not self._formats:
            raise CapabilitiesException("Error in getCapabilities response: no formats available")

        serviceMetadataContents = capabilitiesXmlResponse.find(f'{wcs_ns}ServiceMetadata')
        if serviceMetadataContents is not None:
            for crsElement in serviceMetadataContents.findall(f'.//{wcs_ns}Extension/{crs_ns}CrsMetadata/{crs_ns}crsSupported'):
                if crsElement.text:
                    self._crsx.append(crsElement.text)
            # In case of wrong crs extension implementation
            if not self._crsx:
                for crsElement in serviceMetadataContents.findall(f'.//{wcs_ns}Extension/{crs_serviceextension_ns}CrsMetadata/{crs_serviceextension_ns}crsSupported'):
                    if crsElement.text:
                        self._crsx.append(crsElement.text)

        self._coverageSummary = {}
        contents = capabilitiesXmlResponse.find(f'{wcs_ns}Contents')
        if contents is not None:
            for coverageSummary in contents.findall(f'.//{wcs_ns}CoverageSummary'):
                coverageIdElement = coverageSummary.find(f'.//{wcs_ns}CoverageId')
                if coverageIdElement is None:
                    continue
                coverageId = coverageIdElement.text

                """
                coverageCrsElement = coverageSummary.find(f'.//{ows_ns}BoundingBox')
                if coverageCrsElement is not None:
                    coverageCrs = coverageCrsElement.attrib.get('crs')
                    if coverageCrs and coverageCrs not in crsx:
                        allCrsx = crsx + [coverageCrs]
                    else:
                        allCrsx = crsx
                """
                coverageBbWgsLowerCornerElement = coverageSummary.find(
                    f'.//{ows_ns}WGS84BoundingBox/{ows_ns}LowerCorner')
                if coverageBbWgsLowerCornerElement is not None:
                    coverageBbWgsLowerCorner = coverageBbWgsLowerCornerElement.text
                else:
                    coverageBbWgsLowerCorner = None
                coverageBbWgsUpperCornerElement = coverageSummary.find(
                    f'.//{ows_ns}WGS84BoundingBox/{ows_ns}UpperCorner')
                if coverageBbWgsUpperCornerElement is not None:
                    coverageBbWgsUpperCorner = coverageBbWgsUpperCornerElement.text
                else:
                    coverageBbWgsUpperCorner = None

                corners = BbCorners(bbLowerCorner=coverageBbWgsLowerCorner,
                                    bbUpperCorner=coverageBbWgsUpperCorner)
                self._coverageSummary[coverageId] = corners
