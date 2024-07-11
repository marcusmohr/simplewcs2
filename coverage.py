"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Landesvermessung und Geobasisinformation Brandenburg
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""
from dataclasses import dataclass
from typing import List, Dict, Optional
import xml.etree.ElementTree

from .helpers import logWarnMessage

@dataclass
class CoverageInformation:
    nativeCrs: str
    axisLabels: List[str]

wcs_ns = '{http://www.opengis.net/wcs/2.0}'
gml_ns = '{http://www.opengis.net/gml/3.2}'
gmlcov_ns = '{http://www.opengis.net/gmlcov/1.0}'
swe_ns = '{http://www.opengis.net/swe/2.0}'

class DescribeCoverage:

    """Stores information from descrive coverage response"""

    def __init__(self, coverageXmlResponse: xml.etree.ElementTree) -> None:

        self.coverageInformation: Optional[Dict[str, CoverageInformation]] = None

        self.readDescribeCoverage(coverageXmlResponse)

    @property
    def coverageInformation(self) -> Dict[str, CoverageInformation]:
        return self._coverageInformation

    @coverageInformation.setter
    def coverageInformation(self, newInformation):
        self._coverageInformation = newInformation

    def readDescribeCoverage(self, coverageXmlResponse: xml.etree.ElementTree) -> None:

        self.coverageInformation = {}

        for covIdDescription in coverageXmlResponse.findall(f'.//{wcs_ns}CoverageDescription'):

            covId = covIdDescription.attrib.get(f'{gml_ns}id')
            if not covId:
                logWarnMessage("Error in Describe Coverage: covId could not be read")
                continue

            envelopeElement = covIdDescription.find(f'{gml_ns}boundedBy/{gml_ns}Envelope')
            if envelopeElement is not None:
                nativeCrs = envelopeElement.attrib.get('srsName')
                if not nativeCrs:
                    logWarnMessage("Error in Describe Coverage: native crs could not be read")
                    continue
                axisLabels = envelopeElement.attrib.get('axisLabels')
                if axisLabels:
                    axisLabels = axisLabels.split(" ")
                    if len(axisLabels) > 2:
                        logWarnMessage(f"More than two axes are not supported (yet): {axisLabels}")
                        continue
                else:
                    logWarnMessage("Error in Describe Coverage: native crs could not be read")
                    continue
            else:
                logWarnMessage("Error in Describe Coverage: envelope could not be read")
                continue

            self.coverageInformation[covId] = CoverageInformation(nativeCrs=nativeCrs, axisLabels=axisLabels)
