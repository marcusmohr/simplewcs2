"""
        Simple WCS 2 - QGIS Plugin
        Basic support for OGC WCS 2.X

        created by Marcus Mohr (LGB)
        email: marcus.mohr@geobasis-bb.de
        licence: GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
"""

def classFactory(iface):
    """
    Load SimpleWCS class from file SimpleWCS.
    """

    from .simplewcs import SimpleWCS
    return SimpleWCS(iface)
