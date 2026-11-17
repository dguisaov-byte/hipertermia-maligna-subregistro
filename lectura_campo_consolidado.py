# -*- coding: utf-8 -*-
# Error de lectura del campo CAUSA_MULT y su correccion (hoja 10 del contenido suplementario).
#
# Desde 2019 el DANE encadena los codigos del certificado en un solo campo, CAUSA_MULT,
# con tres separadores: barra, asterisco y espacio, y deja la causa basica en C_BAS1.
#     I219/J960/J988/Z988 Y653*J988        (6 codigos)
#     J960/J384/T782/T784 T412 Y482*B463   (7 codigos)
# La version preliminar del conteo de codigos por certificado tenia dos fallas en esos anios:
#   1. quitaba los espacios antes de separar, asi que "T784 T412" quedaba como "T784T412";
#   2. contaba solo CAUSA_MULT y no sumaba C_BAS1, que en 2008-2018 si se sumaba.
# Este archivo calcula el conteo con la lectura preliminar, con solo la primera falla
# corregida y con las dos corregidas, y compara los periodos.
#
# Uso:  python lectura_campo_consolidado.py

import glob
import os
import re

import numpy as np
import pandas as pd

from lectura_dane import anio_de, leer_anio

RUTA_DANE = "datos/dane"
NO_SON_CAUSA = {"CAUSA_666", "CAUSA_667", "CAU_HOMOL"}


def tokens(serie, con_espacio):
    s = serie.fillna("").astype(str).str.upper().str.replace(r"[.\-]", "", regex=True)
    if con_espacio:
        partes = s.str.split(r"[/*,;+\s]+")
    else:
        partes = s.str.replace(" ", "", regex=False).str.split(r"[/*,;+]")
    return partes.map(lambda p: sum(1 for t in p if t))


def hay_codigo(serie):
    return (serie.fillna("").astype(str).str.strip() != "").astype(int)


ejemplos = pd.Series(["I219/J960/J988/Z988 Y653*J988",
                      "J960/J384/T782/T784 T412 Y482*B463",
                      "T175/R418/T414 Y484",
                      "R688/G931/T885"])
print("Ejemplos del campo consolidado (codigos de CAUSA_MULT con cada lectura)")
for texto, a, b in zip(ejemplos, tokens(ejemplos, False), tokens(ejemplos, True)):
    print(f"  {texto:38s} sin espacio {a}   con espacio {b}")

archivos = sorted(glob.glob(os.path.join(RUTA_DANE, "**", "*.csv"), recursive=True)
                  + glob.glob(os.path.join(RUTA_DANE, "**", "*.sav"), recursive=True), key=anio_de)

filas = []
for ruta in archivos:
    anio = anio_de(ruta)
    df = leer_anio(ruta)
    basica = hay_codigo(df["C_BAS1"])
    if "CAUSA_MULT" in df.columns:
        campo = df["CAUSA_MULT"]
        preliminar = tokens(campo, False)
        solo_espacio = tokens(campo, True)
        corregida = solo_espacio + basica
        espacio = 100 * campo.fillna("").astype(str).str.strip().str.contains(" ").mean()
    else:
        # hasta 2018 cada codigo esta en su propio campo; las dos lecturas coinciden
        campos = [c for c in df.columns
                  if re.match(r"^C_(DIR|ANT|PAT|MCM|COMP|BAS)", c) and c not in NO_SON_CAUSA]
        corregida = sum(tokens(df[c], True) for c in campos)
        preliminar = solo_espacio = corregida
        espacio = np.nan
    filas.append({"anio": anio, "certificados": len(df),
                  "preliminar": preliminar.mean(),
                  "solo_espacio": solo_espacio.mean(),
                  "corregida": corregida.mean(),
                  "con_espacio_interno_pct": espacio})
    print(f"  {anio} leido")

t = pd.DataFrame(filas)
print("\nCodigos por certificado, 2019-2024 (hoja 10)")
print(t[t.anio >= 2019].round({"preliminar": 3, "solo_espacio": 3, "corregida": 3,
                               "con_espacio_interno_pct": 1}).to_string(index=False))

antes = np.average(t.loc[t.anio <= 2018, "corregida"], weights=t.loc[t.anio <= 2018, "certificados"])
print(f"\n2008-2018: {antes:.2f} codigos por certificado")
for col, nombre in (("preliminar", "lectura preliminar"),
                    ("solo_espacio", "solo con el espacio corregido"),
                    ("corregida", "lectura corregida")):
    d = t[t.anio >= 2019]
    m = np.average(d[col], weights=d["certificados"])
    print(f"2019-2024, {nombre}: {m:.2f} ({100 * (m / antes - 1):+.1f} %)")
