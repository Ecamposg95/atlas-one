"""Atlas BOS module - labels.

DOMAIN: Etiquetas de mostrador (Zebra ZPL, 51 x 25 mm)
STATUS: Stable

Atlas One elige las variantes, calcula las copias y compone el ZPL; el agente
de impresión local se queda con la impresora. No hay tablas propias: el módulo
lee catálogo y existencia y devuelve bytes.
"""
