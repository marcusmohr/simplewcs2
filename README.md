# QGIS Plugin for OGC Web Coverage Service 2.X

Receive tiff files from OGC Web Coverage Services (v2.X) based on map view in QGIS. Created to access certain german official geodata, e.g. digital aerial photographs.

## Supports...
- WCS 2.X Core
- KVP Protocol-Binding
- CRS Extenstion
- Geo Tiff

## Issues with Subsetting:
The plugin provides functionality to use a subset crs that differs from the native one (list of crs is indicated in the get capabilities response of a service). However, many services currently seem not to offer full support of other crs for subsetting, thus an error might be raised.

The names and order of axis labels for subsetting are indicated in the describe coverage response of a coverage. Subsetting depends on the right order of labels, but for crs with inverted axis labels are sometimes indicated in the wrong order. In this case, the user can try to check the "deactivate axis inversion" checkbox to retrieve a coverage.

