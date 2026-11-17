# -*- coding: utf-8 -*-
# Hipertermia maligna en Colombia: subregistro o falta de consciencia en su reporte
# Rutina de replicacion (Python 3). Guisao-Villa DA, Navarro-Vargas JR, Rojas JE.
#
# Entradas (carpeta datos/):
#   datos/dane/   un archivo por anio de defunciones no fetales 2008-2024 (.csv o .sav),
#                 tal como se descargan de microdatos.dane.gov.co
#   datos/RtaHipertermiaRIPS.xlsx   tabulados entregados por Minsalud (tres hojas)
# Salidas: carpeta resultados/
#
# Uso:  python replicacion_hipertermia.py
# Requiere pandas, numpy, scipy, openpyxl y, si los archivos son .sav, pyreadstat.

import glob
import os
import re

import numpy as np
import pandas as pd
from scipy.stats import chi2, poisson

from lectura_dane import anio_de, leer_anio

RUTA_DANE = "datos/dane"
RUTA_RIPS = "datos/RtaHipertermiaRIPS.xlsx"
SALIDA = "resultados"
os.makedirs(SALIDA, exist_ok=True)

OBJETIVO = "T883"
# causa externa anestesica; Y48.3 (locales) y Y48.5 (gases terapeuticos) quedan fuera
EXTERNAS = ["Y480", "Y481", "Y482", "Y484", "Y653"]
ANESTESICAS = ["T882", "T884", "T885"]      # sin T88.3, que es el codigo evaluado
RESIDUALES = ["T887", "T888", "T889"]

# CAUSA_666, CAUSA_667 y CAU_HOMOL son agrupaciones del DANE, no codigos del certificado
NO_SON_CAUSA = {"CAUSA_666", "CAUSA_667", "CAU_HOMOL"}

# En CAUSA_MULT (2019 en adelante) los codigos vienen separados por barra, asterisco
# y tambien por espacio. Si el espacio no se trata como separador, dos codigos
# contiguos quedan pegados (ver lectura_campo_consolidado.py).
SEPARADOR = r"[/*,;+\s]+"
CIE10 = r"^[A-Z][0-9]{2}[0-9A-Z]?$"

GRUPO_EDAD = {
    "00": "Menor de 1 hora", "01": "Menor de 1 dia", "02": "1 a 6 dias",
    "03": "7 a 27 dias", "04": "28 a 29 dias", "05": "1 a 5 meses",
    "06": "6 a 11 meses", "07": "1 año", "08": "2 a 4 años", "09": "5 a 9 años",
    "10": "10 a 14 años", "11": "15 a 19 años", "12": "20 a 24 años",
    "13": "25 a 29 años", "14": "30 a 34 años", "15": "35 a 39 años",
    "16": "40 a 44 años", "17": "45 a 49 años", "18": "50 a 54 años",
    "19": "55 a 59 años", "20": "60 a 64 años", "21": "65 a 69 años",
    "22": "70 a 74 años", "23": "75 a 79 años", "24": "80 a 84 años",
    "25": "85 a 89 años", "26": "90 a 94 años", "27": "95 a 99 años",
    "28": "100 años o mas", "29": "Edad desconocida",
}
SEXO = {"1": "Hombre", "2": "Mujer", "3": "Indeterminado"}
MANERA = {"1": "Natural", "2": "Violenta", "3": "En estudio"}
DEPARTAMENTO = {
    "05": "Antioquia", "08": "Atlántico", "11": "Bogotá", "13": "Bolívar",
    "15": "Boyacá", "17": "Caldas", "18": "Caquetá", "19": "Cauca", "20": "Cesar",
    "23": "Córdoba", "25": "Cundinamarca", "27": "Chocó", "41": "Huila",
    "44": "La Guajira", "47": "Magdalena", "50": "Meta", "52": "Nariño",
    "54": "Norte de Santander", "63": "Quindío", "66": "Risaralda",
    "68": "Santander", "70": "Sucre", "73": "Tolima", "76": "Valle del Cauca",
    "81": "Arauca", "85": "Casanare", "86": "Putumayo", "88": "San Andrés",
    "91": "Amazonas", "94": "Guainía", "95": "Guaviare", "97": "Vaupés",
    "99": "Vichada",
}


# ------------------------------------------------------------------ lectura

def campos_de_causa(df):
    patron = r"^C_(DIR|ANT|PAT|MCM|COMP|BAS)"
    return [c for c in df.columns
            if (re.match(patron, c) or c == "CAUSA_MULT") and c not in NO_SON_CAUSA]


def limpiar(serie):
    """Mayusculas, sin puntos ni guiones y con un solo espacio entre codigos."""
    s = serie.fillna("").astype(str).str.upper()
    s = s.str.replace(r"[.\-]", "", regex=True)
    s = s.str.replace(SEPARADOR, " ", regex=True).str.strip()
    return s.replace({"NAN": "", "NONE": ""})


def codigos(limpio, campos):
    """Lista de codigos de cada certificado a partir de campos ya limpios."""
    if not campos:
        return pd.Series([[] for _ in range(len(limpio))], index=limpio.index)
    texto = limpio[campos[0]].str.cat([limpio[c] for c in campos[1:]], sep=" ")
    return texto.str.split()


# ------------------------------------------------------------------ mortalidad

archivos = sorted(glob.glob(os.path.join(RUTA_DANE, "**", "*.csv"), recursive=True)
                  + glob.glob(os.path.join(RUTA_DANE, "**", "*.sav"), recursive=True),
                  key=anio_de)
# si un anio esta en csv y en sav se usa uno solo
vistos, unicos = set(), []
for f in archivos:
    if anio_de(f) not in vistos:
        vistos.add(anio_de(f))
        unicos.append(f)
archivos = unicos
print(f"Archivos de defunciones: {len(archivos)}")

traza, familia, faltantes = [], [], []
casos_t883, casos_ext = [], []
comparacion = {}

for ruta in archivos:
    anio = anio_de(ruta)
    df = leer_anio(ruta)
    cc = campos_de_causa(df)
    asociadas = [c for c in cc if c != "C_BAS1"]

    limpio = pd.DataFrame({c: limpiar(df[c]) for c in cc})
    listas = codigos(limpio, cc)
    largo = listas.explode().dropna()
    largo = largo[largo != ""]

    def con(conjunto):
        idx = largo.index[largo.isin(conjunto)].unique()
        return df.index.isin(idx)

    es_t883 = con([OBJETIVO])
    es_ext = con(EXTERNAS)

    traza.append({
        "anio": anio,
        "certificados": len(df),
        "campos_causa": len(cc),
        "estructura": "Campo consolidado CAUSA_MULT" if "CAUSA_MULT" in cc
                      else "Campos separados por renglon",
        "apariciones_T883": int((largo == OBJETIVO).sum()),
        "cert_T883": int(es_t883.sum()),
        "cert_externa": int(es_ext.sum()),
        "ambos": int((es_t883 & es_ext).sum()),
        "codigos_por_certificado": round(float(listas.str.len().mean()), 6),
    })

    # familia T88: por codigo (un certificado con dos codigos cuenta en dos filas)
    # y por subconjunto (cada certificado una sola vez)
    fila = {"anio": anio, "certificados": len(df)}
    for k in range(10):
        fila[f"T88{k}"] = int(con([f"T88{k}"]).sum())
    fila["anestesicas_sin_T883"] = int(con(ANESTESICAS).sum())
    fila["anestesicas_con_T883"] = int(con(ANESTESICAS + [OBJETIVO]).sum())
    fila["residuales"] = int(con(RESIDUALES).sum())
    fila["familia_T88"] = int(df.index.isin(largo.index[largo.str.startswith("T88")]).sum())
    fila["T70_T89"] = int(df.index.isin(largo.index[largo.str.match(r"T[78]")]).sum())
    familia.append(fila)

    # datos faltantes en los campos de causa
    asoc = codigos(limpio, asociadas)
    no_validos = largo.index[~largo.str.match(CIE10)].unique()
    faltantes.append({
        "anio": anio,
        "certificados": len(df),
        "sin_causa_basica": int((limpio["C_BAS1"] == "").sum()),
        "sin_causas_asociadas": int((asoc.str.len() == 0).sum()),
        "sin_ningun_codigo": int((listas.str.len() == 0).sum()),
        "con_codigo_no_valido": int(len(no_validos)),
    })

    if es_t883.any():
        d = df[es_t883].copy()
        d["anio"] = anio
        d["campos_T883"] = [", ".join(c for c in cc if OBJETIVO in fila_[c].split())
                            for _, fila_ in limpio[es_t883].iterrows()]
        d["tambien_externa"] = es_ext[es_t883]
        casos_t883.append(d)
    if es_ext.any():
        d = df[es_ext].copy()
        d["anio"] = anio
        d["codigo_externa"] = [", ".join(sorted(set(x) & set(EXTERNAS))) for x in listas[es_ext]]
        d["tambien_T883"] = es_t883[es_ext]
        casos_ext.append(d)

    # comparacion de estructuras: ultimo anio con campos separados y primero consolidado
    if anio == 2018:
        parte1 = [c for c in cc if re.match(r"^C_(DIR|ANT|MCM)", c)]
        parte2 = [c for c in cc if c.startswith("C_PAT")]
        comparacion[2018] = {
            "primer_codigo": limpio["C_DIR1"].replace("", np.nan).value_counts(normalize=True).head(6),
            "parte_II": codigos(limpio, parte2).explode().dropna().value_counts(normalize=True).head(5),
            "cod_parte_I": codigos(limpio, parte1).str.len().mean(),
            "cod_parte_II": codigos(limpio, parte2).str.len().mean(),
            "muerte_natural": (df["PMAN_MUER"].str.strip() == "1").mean() if "PMAN_MUER" in df else np.nan,
        }
    if anio == 2019:
        bruto = df["CAUSA_MULT"].fillna("").astype(str)
        antes = bruto.str.split("*", n=1, regex=False).str[0]
        despues = bruto.str.split("*", n=1, regex=False).str[1].fillna("")
        p1 = limpiar(antes).str.split()
        p2 = limpiar(despues).str.split()
        comparacion[2019] = {
            "primer_codigo": p1.str[0].dropna().value_counts(normalize=True).head(6),
            "parte_II": p2.explode().dropna().value_counts(normalize=True).head(5),
            "cod_parte_I": p1.str.len().mean(),
            "cod_parte_II": p2.str.len().mean(),
            "muerte_natural": (df["P_PMAN_IRIS"].str.strip() == "0").mean() if "P_PMAN_IRIS" in df else np.nan,
        }

    print(f"  {anio}: {len(df):>7} certificados | T88.3 {int(es_t883.sum())} | causa externa {int(es_ext.sum())}")

traza = pd.DataFrame(traza)
familia = pd.DataFrame(familia)
faltantes = pd.DataFrame(faltantes)
t883 = pd.concat(casos_t883, ignore_index=True)
ext = pd.concat(casos_ext, ignore_index=True)


def posicion(campos):
    etiquetas = []
    for c in campos.split(", "):
        if c.startswith("C_DIR"):
            etiquetas.append("Directa")
        elif c.startswith("C_ANT"):
            etiquetas.append("Antecedente")
        elif c.startswith("C_PAT"):
            etiquetas.append("Contribuyente")
        elif c != "C_BAS1":
            etiquetas.append(c)
    return " y ".join(dict.fromkeys(etiquetas)).capitalize()


def tabla_casos(d, extra):
    out = pd.DataFrame({
        "Año": d["anio"],
        "Departamento": d["COD_DPTO"].map(DEPARTAMENTO).fillna(d["COD_DPTO"]),
        "Sexo": d["SEXO"].str.strip().map(SEXO),
        "Grupo de edad": d["GRU_ED1"].map(GRUPO_EDAD).fillna(d["GRU_ED1"]),
    })
    for nombre, valores in extra.items():
        out[nombre] = valores
    return out


manera = t883["PMAN_MUER"].str.strip().map(MANERA) if "PMAN_MUER" in t883 else ""
tabla4 = tabla_casos(t883, {
    "Posición del código": t883["campos_T883"].map(posicion),
    "Campo del archivo": t883["campos_T883"],
    "Causa básica": t883["C_BAS1"],
    "Manera de muerte": manera,
    "También con causa externa": np.where(t883["tambien_externa"], "Sí", "No"),
})
tabla_ext = tabla_casos(ext, {
    "Código de causa externa": ext["codigo_externa"],
    "Causa básica": ext["C_BAS1"],
    "También con T88.3": np.where(ext["tambien_T883"], "Sí", "No"),
})

p1 = traza[traza.anio <= 2018]
p2 = traza[traza.anio >= 2019]
N1, N2 = int(p1.certificados.sum()), int(p2.certificados.sum())
union = int(traza.cert_T883.sum() + traza.cert_externa.sum() - traza.ambos.sum())


def tasa(k, n):
    return 1e5 * k / n


# tabla 5
f1 = familia[familia.anio <= 2018].sum(numeric_only=True)
f2 = familia[familia.anio >= 2019].sum(numeric_only=True)
filas5 = [f"T88{k}" for k in range(10)] + ["anestesicas_sin_T883", "anestesicas_con_T883",
                                             "residuales", "familia_T88", "T70_T89"]
tabla5 = pd.DataFrame({
    "conjunto": filas5,
    "n_2008_2018": [int(f1[c]) for c in filas5],
    "tasa_2008_2018": [round(tasa(f1[c], N1), 2) for c in filas5],
    "n_2019_2024": [int(f2[c]) for c in filas5],
    "tasa_2019_2024": [round(tasa(f2[c], N2), 2) for c in filas5],
})
# sin variacion porcentual cuando algun conteo es menor de cinco, salvo el cero de T88.3
estable = (tabla5[["n_2008_2018", "n_2019_2024"]].min(axis=1) >= 5) | (tabla5.conjunto == OBJETIVO)
cambio = 100 * (tabla5.n_2019_2024 / N2) / (tabla5.n_2008_2018 / N1).replace(0, np.nan) - 100
tabla5["cambio_pct"] = cambio.where(estable).round(0)

# esperados de T88.3 en 2019-2024 y probabilidad de observar cero
n_previo = int(p1.cert_T883.sum())
esp = n_previo / N1 * N2
factor = tasa(f2["anestesicas_sin_T883"], N2) / tasa(f1["anestesicas_sin_T883"], N1)
esp_aj = esp * factor
# intervalo exacto de Poisson para los eventos del primer periodo
li = chi2.ppf(0.025, 2 * n_previo) / 2
ls = chi2.ppf(0.975, 2 * (n_previo + 1)) / 2
esp_li, esp_ls = li / N1 * N2, ls / N1 * N2

# profundidad de la cadena causal, ponderada por certificados
prof1 = np.average(p1.codigos_por_certificado, weights=p1.certificados)
prof2 = np.average(p2.codigos_por_certificado, weights=p2.certificados)

ext1, ext2 = int(p1.cert_externa.sum()), int(p2.cert_externa.sum())

# datos faltantes por periodo
faltantes["periodo"] = np.where(faltantes.anio <= 2018, "2008-2018", "2019-2024")
falt_periodo = faltantes.drop(columns="anio").groupby("periodo").sum()
for c in ["sin_causa_basica", "sin_causas_asociadas", "sin_ningun_codigo", "con_codigo_no_valido"]:
    falt_periodo[c + "_pct"] = (100 * falt_periodo[c] / falt_periodo["certificados"]).round(3)

print("\nMortalidad")
print(traza.to_string(index=False))
print("\nDefunciones con T88.3")
print(tabla4.to_string(index=False))
print("\nCausa externa anestesica, por codigo")
print(tabla_ext["Código de causa externa"].value_counts().to_string())
print("\nFamilia T88 (tabla 5)")
print(tabla5.to_string(index=False))
print("\nDatos faltantes en los campos de causa")
print(falt_periodo.T.to_string())

if comparacion:
    print("\nComparacion 2018 (campos separados) frente a 2019 (campo consolidado)")
    for a in sorted(comparacion):
        c = comparacion[a]
        print(f"  {a}: codigos parte I {c['cod_parte_I']:.2f} | parte II {c['cod_parte_II']:.2f}"
              f" | muerte natural {100 * c['muerte_natural']:.2f} %")
        print("     primer codigo:", "  ".join(f"{k} {100 * v:.2f}%" for k, v in c["primer_codigo"].items()))
        print("     parte II     :", "  ".join(f"{k} {100 * v:.2f}%" for k, v in c["parte_II"].items()))


# ------------------------------------------------------------------ RIPS

N = "Número de Personas Atendidas"


def leer_hoja(hoja):
    d = pd.read_excel(RUTA_RIPS, sheet_name=hoja, header=11).dropna(how="all")
    d.columns = [str(c).strip() for c in d.columns]
    d = d[d["Año"].notna()].copy()
    col_edad = "Edades Simples DANE" if "Edades Simples DANE" in d.columns else "Edad"
    d["anio"] = d["Año"].astype(int)
    d["edad"] = d[col_edad].str.extract(r"(\d+)")[0].astype(int)
    d["n"] = d[N].astype(int)
    d["dpto"] = d["Departamento"].str.split(" - ").str[0].str.strip()
    d["mun"] = d["Municipio"].str.split(" - ").str[0].str.strip()
    d["sexo"] = d["Sexo"].str.strip()
    return d


h1 = leer_hoja("Hoja1")   # consulta externa y urgencias
h2 = leer_hoja("Hoja2")   # procedimientos
h3 = leer_hoja("Hoja3")   # hospitalizacion

tipo = h1["Tipo de Atención"].str.contains("URGENCIAS").map({True: "Urgencias", False: "Consulta externa"})
tabla1 = pd.concat([
    h1.groupby(["anio", tipo])["n"].sum().unstack(fill_value=0),
    h3.groupby("anio")["n"].sum().rename("Hospitalización"),
    h2.groupby("anio")["n"].sum().rename("Persona-procedimiento"),
], axis=1).fillna(0).astype(int)
tabla1.loc["Total"] = tabla1.sum()

CORTES = [(0, 4), (5, 14), (15, 17), (18, 44), (45, 64), (65, 200)]


def describir(d):
    e = np.repeat(d["edad"].values, d["n"].values)
    con_territorio = d[d["dpto"] != "-1"]     # -1 es "no definido" en la fuente
    return {
        "registros": int(d["n"].sum()),
        "mediana": float(np.median(e)),
        "p25": round(float(np.percentile(e, 25))), "p75": round(float(np.percentile(e, 75))),
        "min": int(e.min()), "max": int(e.max()),
        "grupos": [int(((e >= a) & (e <= b)).sum()) for a, b in CORTES],
        "mujeres": int(d.loc[d.sexo == "FEMENINO", "n"].sum()),
        "hombres": int(d.loc[d.sexo == "MASCULINO", "n"].sum()),
        "departamentos": con_territorio["dpto"].nunique(),
        "municipios": con_territorio["mun"].nunique(),
        "sin_territorio": int(d.loc[d["dpto"] == "-1", "n"].sum()),
    }


amb, hosp = describir(h1), describir(h3)

# procedimientos por capitulo de la CUPS (dos primeros caracteres del codigo)
CAPITULO = {"90": "Laboratorio clínico", "91": "Laboratorio clínico",
            "87": "Imagenología", "88": "Imagenología",
            "89": "Consulta, evaluación y procedimientos diagnósticos",
            "93": "Terapia y rehabilitación",
            "95": "Otros procedimientos diagnósticos especializados",
            "97": "Odontología preventiva",
            "99": "Otros servicios (educación en salud, inyecciones)"}
h2["cups"] = h2["Procedimiento CUPS"].str.split(" - ").str[0].str.strip()
h2["descripcion"] = h2["Procedimiento CUPS"].str.split(" - ", n=1).str[1].str.strip()
h2["capitulo"] = h2["cups"].str[:2]
h2["categoria"] = h2["capitulo"].map(CAPITULO).fillna("Procedimientos quirúrgicos e invasivos")

tabla3 = h2.groupby("categoria")["n"].sum().sort_values(ascending=False).to_frame("registros")
total_proc = int(h2["n"].sum())
tabla3["pct"] = (100 * tabla3["registros"] / total_proc).round(1)
correspondencia = (h2.groupby(["cups", "descripcion", "capitulo", "categoria"], as_index=False)["n"].sum()
                     .rename(columns={"n": "registros"})
                     .sort_values(["categoria", "registros"], ascending=[True, False]))
top10 = h2.groupby("Procedimiento CUPS")["n"].sum().sort_values(ascending=False).head(10)

txt = h2["Procedimiento CUPS"].str.upper()
MARCADORES = {
    "Potasio sérico": "POTASIO",
    "Lactato": "LACTATO|ACIDO LACTICO",
    "Creatinquinasa total": "CREATIN.?QUINASA|CPK",
    "Mioglobina en orina": "MIOGLOBINA",
    "Gases arteriales": "GASES ARTERIAL",
}
marc = {k: int(h2.loc[txt.str.contains(p), "n"].sum()) for k, p in MARCADORES.items()}
marc_anio = h2[txt.str.contains("|".join(MARCADORES.values()))].groupby("anio")["n"].sum()

SUSCEPTIBILIDAD = {
    "Prueba de contractura in vitro": "CONTRACTURA|HALOTANO|CAFEINA",
    "Biopsia muscular": "BIOPSIA",
    "Electromiografía": "ELECTROMIOGRAF",
}
susc = {k: int(h2.loc[txt.str.contains(p), "n"].sum()) for k, p in SUSCEPTIBILIDAD.items()}
# Los estudios moleculares se revisaron uno por uno por su descripcion. De los cuatro
# codigos que traen la palabra, 908890 (VPH) y 908859 (panel de patogenos) son
# microbiologia y no estudios geneticos del paciente.
candidatos = h2[txt.str.contains("MOLECULAR|GENETIC|SECUENCIA|EXON|EXOMA")]
moleculares = candidatos[~candidatos["cups"].isin(["908890", "908859"])]
susc["Estudio molecular, gen no especificado"] = int(moleculares["n"].sum())


def cadenas(anio, mun, sexo, edad):
    """Registros del mismo municipio y sexo cuya edad avanza igual que los anios."""
    orden = np.lexsort((anio, edad, sexo, mun))
    anio, mun, sexo, edad = anio[orden], mun[orden], sexo[orden], edad[orden]
    usado = np.zeros(len(anio), bool)
    todas = []
    for i in range(len(anio)):
        if usado[i]:
            continue
        usado[i] = True
        actual, miembros = i, [i]
        while True:
            j = np.where(~usado & (mun == mun[actual]) & (sexo == sexo[actual])
                         & (anio > anio[actual])
                         & (np.abs((edad - edad[actual]) - (anio - anio[actual])) <= 0.5))[0]
            if len(j) == 0:
                break
            actual = j[0]
            usado[actual] = True
            miembros.append(actual)
        todas.append([(int(anio[k]), str(mun[k]), str(sexo[k]), int(edad[k])) for k in miembros])
    return todas


A, M, S, E = (h1["anio"].values, h1["mun"].values.astype(str),
              h1["sexo"].values.astype(str), h1["edad"].values)
todas = cadenas(A, M, S, E)
largas = [c for c in todas if len(c) > 1]
rng = np.random.default_rng(7)
nulo = np.array([sum(len(c) > 1 for c in cadenas(rng.permutation(A), M, S, E))
                 for _ in range(5000)])
p_perm = float((nulo >= len(largas)).mean())

print("\nRIPS")
print(tabla1.to_string())
print(tabla3.to_string())
print("Marcadores:", marc, "| por año:", marc_anio.to_dict())
print("Pruebas de susceptibilidad:", susc)
print(moleculares[["anio", "Municipio", "edad", "sexo", "Procedimiento CUPS"]].to_string(index=False))
print("Cadenas de más de un año:")
for c in largas:
    print("  ", c)


# ------------------------------------------------------------------ contraste con el articulo

def pct(a, b):
    return round(100 * a / b, 1)


obtenido = {
    "Certificados examinados": int(traza.certificados.sum()),
    "Certificados 2008-2018 / 2019-2024": (N1, N2),
    "Apariciones de T88.3": int(traza.apariciones_T883.sum()),
    "Defunciones con T88.3": int(traza.cert_T883.sum()),
    "T88.3 desde 2019": int(p2.cert_T883.sum()),
    "T88.3 como causa basica": int((t883["C_BAS1"].str.replace(".", "", regex=False) == OBJETIVO).sum()),
    "Causa basica Y48.4 entre las de T88.3": int((t883["C_BAS1"] == "Y484").sum()),
    "Mujeres entre las de T88.3": int((t883["SEXO"].str.strip() == "2").sum()),
    "Defunciones con causa externa": int(traza.cert_externa.sum()),
    "Causa externa por periodo": (ext1, ext2),
    "Solapamiento / union": (int(traza.ambos.sum()), union),
    "Captacion T88.3 / causa externa (%)": (pct(traza.cert_T883.sum(), union), pct(traza.cert_externa.sum(), union)),
    "Esperadas de causa externa 2019-2024": round(ext1 / N1 * N2, 1),
    "Codigos por certificado 2018 / 2019": (round(float(traza.loc[traza.anio == 2018, "codigos_por_certificado"].iloc[0]), 2),
                                            round(float(traza.loc[traza.anio == 2019, "codigos_por_certificado"].iloc[0]), 2)),
    "Codigos por certificado por periodo": (round(prof1, 2), round(prof2, 2)),
    "Familia T88, n": (int(f1["familia_T88"]), int(f2["familia_T88"])),
    "Familia T88, por 100.000": (round(tasa(f1["familia_T88"], N1), 1), round(tasa(f2["familia_T88"], N2), 1)),
    "Anestesicas sin T88.3, n": (int(f1["anestesicas_sin_T883"]), int(f2["anestesicas_sin_T883"])),
    "Residuales, n": (int(f1["residuales"]), int(f2["residuales"])),
    "Residuales sobre la familia, primer periodo (%)": pct(f1["residuales"], f1["familia_T88"]),
    "T70-T89 por 100.000": (round(tasa(f1["T70_T89"], N1)), round(tasa(f2["T70_T89"], N2))),
    "Esperados de T88.3 sin ajustar": round(esp, 1),
    "P(0) sin ajustar": float(f"{poisson.pmf(0, esp):.1e}"),
    "Esperados, intervalo": (round(esp_li, 1), round(esp_ls, 1)),
    "P(0) maxima": round(float(poisson.pmf(0, esp_li)), 3),
    "Esperados ajustados": round(esp_aj, 1),
    "Consulta externa / urgencias": (int(tabla1.loc["Total", "Consulta externa"]), int(tabla1.loc["Total", "Urgencias"])),
    "Hospitalizaciones": hosp["registros"],
    "Registros de persona-procedimiento": total_proc,
    "Codigos CUPS distintos": int(h2["cups"].nunique()),
    "Edad consulta y urgencias": (amb["mediana"], amb["p25"], amb["p75"], amb["min"], amb["max"]),
    "Grupos de edad consulta y urgencias": amb["grupos"],
    "Mujeres / hombres": (amb["mujeres"], amb["hombres"]),
    "Departamentos / municipios / sin territorio": (amb["departamentos"], amb["municipios"], amb["sin_territorio"]),
    "Edad hospitalizacion (mediana)": hosp["mediana"],
    "Hospitalizacion: hombres / mujeres / departamentos / municipios": (hosp["hombres"], hosp["mujeres"], hosp["departamentos"], hosp["municipios"]),
    "Laboratorio clinico": (int(tabla3.loc["Laboratorio clínico", "registros"]), float(tabla3.loc["Laboratorio clínico", "pct"])),
    "Diez codigos mas frecuentes (%)": pct(top10.sum(), total_proc),
    "Marcadores de crisis metabolica": (sum(marc.values()), pct(sum(marc.values()), total_proc)),
    "Contractura / biopsia / electromiografia": (susc["Prueba de contractura in vitro"], susc["Biopsia muscular"], susc["Electromiografía"]),
    "Estudios moleculares": susc["Estudio molecular, gen no especificado"],
    "Cadenas (total / de mas de un anio)": (len(todas), len(largas)),
    "Cadenas esperadas por azar": round(float(nulo.mean()), 1),
}

articulo = {
    "Certificados examinados": 4049944,
    "Certificados 2008-2018 / 2019-2024": (2310207, 1739737),
    "Apariciones de T88.3": 12,
    "Defunciones con T88.3": 11,
    "T88.3 desde 2019": 0,
    "T88.3 como causa basica": 0,
    "Causa basica Y48.4 entre las de T88.3": 3,
    "Mujeres entre las de T88.3": 7,
    "Defunciones con causa externa": 17,
    "Causa externa por periodo": (13, 4),
    "Solapamiento / union": (3, 25),
    "Captacion T88.3 / causa externa (%)": (44.0, 68.0),
    "Esperadas de causa externa 2019-2024": 9.8,
    "Codigos por certificado 2018 / 2019": (4.32, 4.60),
    "Codigos por certificado por periodo": (4.24, 4.93),
    "Familia T88, n": (1929, 572),
    "Familia T88, por 100.000": (83.5, 32.9),
    "Anestesicas sin T88.3, n": (31, 64),
    "Residuales, n": (1869, 493),
    "Residuales sobre la familia, primer periodo (%)": 96.9,
    "T70-T89 por 100.000": (8722, 7501),
    "Esperados de T88.3 sin ajustar": 8.3,
    "P(0) sin ajustar": 2.5e-4,
    "Esperados, intervalo": (4.1, 14.8),
    "P(0) maxima": 0.016,
    "Esperados ajustados": 22.7,
    "Consulta externa / urgencias": (134, 4),
    "Hospitalizaciones": 14,
    "Registros de persona-procedimiento": 467,
    "Codigos CUPS distintos": 161,
    "Edad consulta y urgencias": (36.0, 16, 51, 0, 90),
    "Grupos de edad consulta y urgencias": [15, 17, 5, 56, 30, 15],
    "Mujeres / hombres": (82, 56),
    "Departamentos / municipios / sin territorio": (20, 63, 4),
    "Edad hospitalizacion (mediana)": 26.5,
    "Hospitalizacion: hombres / mujeres / departamentos / municipios": (8, 6, 9, 12),
    "Laboratorio clinico": (336, 71.9),
    "Diez codigos mas frecuentes (%)": 31.5,
    "Marcadores de crisis metabolica": (32, 6.9),
    "Contractura / biopsia / electromiografia": (0, 0, 0),
    "Estudios moleculares": 2,
    "Cadenas (total / de mas de un anio)": (131, 5),
    "Cadenas esperadas por azar": 3.2,
}

contraste = pd.DataFrame({"obtenido": pd.Series(obtenido, dtype=object),
                          "articulo": pd.Series(articulo, dtype=object)})
contraste["coincide"] = [obtenido[k] == articulo[k] for k in contraste.index]
print("\nContraste con las cifras del articulo")
print(contraste.to_string())
# la permutacion depende de la semilla: con 5.000 replicas el error es de +-0,01
print(f"Permutacion: p = {p_perm:.2f} (articulo 0,18; entre 0,16 y 0,20 es concordante)")
print(f"Cifras que no coinciden: {(~contraste.coincide).sum()}")


# ------------------------------------------------------------------ salidas

with pd.ExcelWriter(os.path.join(SALIDA, "resultados_replicacion.xlsx")) as w:
    contraste.to_excel(w, sheet_name="contraste")
    traza.to_excel(w, sheet_name="mortalidad_por_anio", index=False)
    tabla4.to_excel(w, sheet_name="defunciones_T883", index=False)
    tabla_ext.to_excel(w, sheet_name="causa_externa", index=False)
    tabla5.to_excel(w, sheet_name="familia_T88", index=False)
    faltantes.to_excel(w, sheet_name="faltantes_por_anio", index=False)
    falt_periodo.to_excel(w, sheet_name="faltantes_por_periodo")
    tabla1.to_excel(w, sheet_name="rips_por_anio")
    tabla3.to_excel(w, sheet_name="cups_categorias")
    correspondencia.to_excel(w, sheet_name="cups_correspondencia", index=False)

print(f"\nListo. Resultados en {SALIDA}/resultados_replicacion.xlsx")
