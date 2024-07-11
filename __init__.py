"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Marcus Mohr (LGB)
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""
from qgis.gui import QgisInterface

from .simplewcs import SimpleWCS

def classFactory(iface: QgisInterface) -> SimpleWCS:
    """
    Load SimpleWCS class from file simplewcs.
    """

    return SimpleWCS(iface)
