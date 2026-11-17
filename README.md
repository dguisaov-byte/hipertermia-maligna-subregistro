# Hipertermia maligna en Colombia: subregistro o falta de consciencia en su reporte

Rutinas de análisis del artículo de Guisao-Villa DA, Navarro-Vargas JR y Rojas JE
(Revista Colombiana de Anestesiología). El análisis se hizo en Python y se replicó de
forma independiente en R; las dos rutinas deben dar las mismas cifras.

## Archivos

| Archivo | Qué hace |
|---|---|
| `replicacion_hipertermia.py` | Rutina principal: mortalidad (DANE) y atenciones (RIPS) |
| `lectura_dane.py` | Lectura de los archivos anuales del DANE (.csv o .sav) |
| `replicacion_hipertermia.R` | Réplica independiente en R |
| `lectura_campo_consolidado.py` | Compara la lectura preliminar y la corregida del campo `CAUSA_MULT` |

## Datos

Los datos no se incluyen en el repositorio.

- **Defunciones no fetales 2008-2024.** Microdatos públicos del DANE, Archivo Nacional de
  Datos: https://microdatos.dane.gov.co/index.php/catalog. Se descarga un archivo por año
  (.csv o .sav) y se guardan los 17 en `datos/dane/`. El nombre de cada archivo debe
  conservar el año (por ejemplo `nofetal2015.csv`).
- **Tabulados de RIPS 2015-2025.** Los entregó el Ministerio de Salud y Protección Social
  en respuesta a un derecho de petición (radicado 202642403014702, oficio
  2026220002989181 del 18 de agosto de 2026). Quien quiera replicar esta parte debe
  repetir la solicitud y guardar el archivo como `datos/RtaHipertermiaRIPS.xlsx`
  (tres hojas: consulta externa y urgencias, procedimientos, hospitalización).

## Cómo ejecutar

Python 3.10 o posterior:

```
pip install -r requirements.txt
python replicacion_hipertermia.py
python lectura_campo_consolidado.py
```

R 4.3 o posterior, con los paquetes `data.table`, `haven` y `readxl`:

```
Rscript replicacion_hipertermia.R
```

Las dos rutinas se ejecutan desde la carpeta del repositorio.

## Qué se obtiene

Cada rutina imprime los resultados y termina con una tabla de contraste que compara cada
cifra obtenida con la reportada en el artículo (columna `coincide`). Las tablas quedan en
`resultados/` (Python, un libro de Excel) y `resultados_R/` (R, archivos .csv):
mortalidad por año, defunciones con T88.3, defunciones con causa externa anestésica,
familia T88 por período, datos faltantes en los campos de causa, registros de RIPS por
año y correspondencia de los 161 códigos de procedimiento con su categoría.

La prueba de permutación de las cadenas depende de la semilla: con 5.000 réplicas el
valor de p varía en ±0,01, de modo que resultados entre 0,16 y 0,20 son concordantes con
el 0,18 del artículo.

## Notas sobre los datos

- Hasta 2018 los códigos del certificado vienen en campos separados (`C_DIR1`, `C_ANT1`,
  `C_PAT1`, etc.). Desde 2019 están en un solo campo, `CAUSA_MULT`, separados por barra,
  asterisco y espacio. Si el espacio no se trata como separador se cuentan menos códigos
  por certificado; `lectura_campo_consolidado.py` muestra la diferencia.
- `CAUSA_666`, `CAUSA_667` y `CAU_HOMOL` son agrupaciones del DANE y no se usan en la
  búsqueda.
- Un campo de causa vacío se trata como ausencia de código. No se imputa nada y no se
  excluye ningún certificado.
