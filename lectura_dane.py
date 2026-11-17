# -*- coding: utf-8 -*-
# Lectura de los archivos anuales de defunciones del DANE (.csv o .sav).
# La usan replicacion_hipertermia.py y lectura_campo_consolidado.py.

import os
import re

import pandas as pd


def anio_de(ruta):
    return int(re.search(r"(19|20)\d{2}", os.path.basename(ruta)).group(0))


def leer_anio(ruta):
    """Devuelve el archivo anual con todas las columnas como texto y vacios como ''."""
    if ruta.lower().endswith(".sav"):
        import pyreadstat
        df, _ = pyreadstat.read_sav(ruta, disable_datetime_conversion=True)
        for c in df.columns:
            if df[c].dtype.kind in "fi":
                # 1.0 -> "1"; los faltantes quedan vacios
                df[c] = df[c].map(lambda v: "" if pd.isna(v)
                                  else str(int(v)) if float(v).is_integer() else str(v))
        df = df.fillna("").astype(str)
    else:
        with open(ruta, encoding="latin-1") as f:
            encabezado = f.readline()
        sep = ";" if encabezado.count(";") > encabezado.count(",") else ","
        df = pd.read_csv(ruta, dtype=str, sep=sep, encoding="latin-1",
                         keep_default_na=False, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]
    for c in ("COD_DPTO", "CODPTORE", "GRU_ED1"):
        if c in df.columns:
            df[c] = df[c].str.strip().str.zfill(2)
    return df
