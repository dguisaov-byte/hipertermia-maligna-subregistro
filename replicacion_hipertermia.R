# Hipertermia maligna en Colombia: subregistro o falta de consciencia en su reporte
# Replicacion en R, independiente de la rutina de Python.
# Guisao-Villa DA, Navarro-Vargas JR, Rojas JE.
#
# Entradas: datos/dane/ (17 archivos anuales de defunciones no fetales, .csv o .sav)
#           datos/RtaHipertermiaRIPS.xlsx (tabulados de Minsalud)
# Salidas:  resultados_R/
# Uso:      Rscript replicacion_hipertermia.R
# Paquetes: data.table, haven, readxl

library(data.table)
library(haven)
library(readxl)

RUTA_DANE <- "datos/dane"
RUTA_RIPS <- "datos/RtaHipertermiaRIPS.xlsx"
SALIDA    <- "resultados_R"
dir.create(SALIDA, showWarnings = FALSE, recursive = TRUE)

OBJETIVO    <- "T883"
EXTERNAS    <- c("Y480", "Y481", "Y482", "Y484", "Y653")   # sin Y48.3 ni Y48.5
ANESTESICAS <- c("T882", "T884", "T885")                   # sin T88.3
RESIDUALES  <- c("T887", "T888", "T889")
NO_SON_CAUSA <- c("CAUSA_666", "CAUSA_667", "CAU_HOMOL")

# En CAUSA_MULT los codigos se separan con barra, asterisco y espacio.
SEPARADOR <- "[/*,;+[:space:]]+"

GRUPO_EDAD <- c("00" = "Menor de 1 hora", "01" = "Menor de 1 dia", "02" = "1 a 6 dias",
  "03" = "7 a 27 dias", "04" = "28 a 29 dias", "05" = "1 a 5 meses", "06" = "6 a 11 meses",
  "07" = "1 año", "08" = "2 a 4 años", "09" = "5 a 9 años", "10" = "10 a 14 años",
  "11" = "15 a 19 años", "12" = "20 a 24 años", "13" = "25 a 29 años", "14" = "30 a 34 años",
  "15" = "35 a 39 años", "16" = "40 a 44 años", "17" = "45 a 49 años", "18" = "50 a 54 años",
  "19" = "55 a 59 años", "20" = "60 a 64 años", "21" = "65 a 69 años", "22" = "70 a 74 años",
  "23" = "75 a 79 años", "24" = "80 a 84 años", "25" = "85 a 89 años", "26" = "90 a 94 años",
  "27" = "95 a 99 años", "28" = "100 años o mas", "29" = "Edad desconocida")

## ---------------------------------------------------------------- funciones

dos_digitos <- function(x) {
  x <- trimws(x)
  ifelse(nchar(x) == 1, paste0("0", x), x)
}

leer_anio <- function(ruta) {
  if (grepl("\\.sav$", ruta, ignore.case = TRUE)) {
    d <- haven::read_sav(ruta)
    d <- as.data.table(lapply(d, function(v) as.character(haven::zap_labels(v))))
  } else {
    d <- fread(ruta, colClasses = "character", encoding = "Latin-1", showProgress = FALSE)
  }
  setnames(d, toupper(trimws(names(d))))
  for (col in names(d)) set(d, which(is.na(d[[col]])), col, "")
  for (col in intersect(c("COD_DPTO", "CODPTORE", "GRU_ED1"), names(d)))
    set(d, j = col, value = dos_digitos(d[[col]]))
  d
}

campos_de_causa <- function(d) {
  n <- names(d)
  n[(grepl("^C_(DIR|ANT|PAT|MCM|COMP|BAS)", n) | n == "CAUSA_MULT") & !(n %in% NO_SON_CAUSA)]
}

# Une los campos en una cadena por certificado, con los codigos separados por un
# espacio y con espacio al inicio y al final: asi " T883 " no se confunde con otro codigo.
cadena_de_codigos <- function(d, campos) {
  if (length(campos) == 0) return(rep(" ", nrow(d)))
  x <- do.call(paste, c(as.list(d[, campos, with = FALSE]), sep = " "))
  x <- gsub("[.-]", "", toupper(x))
  x <- gsub(SEPARADOR, " ", x)
  paste0(" ", trimws(x), " ")
}

tiene <- function(cadena, conjunto) {
  Reduce(`|`, lapply(conjunto, function(p) grepl(paste0(" ", p, " "), cadena, fixed = TRUE)))
}

veces <- function(cadena, codigo) {
  lengths(regmatches(cadena, gregexpr(paste0("(?<= )", codigo, "(?= )"), cadena, perl = TRUE)))
}

## ---------------------------------------------------------------- mortalidad

archivos <- list.files(RUTA_DANE, pattern = "\\.(csv|sav)$", full.names = TRUE,
                       ignore.case = TRUE, recursive = TRUE)
anio_de <- function(f) as.integer(regmatches(basename(f), regexpr("(19|20)[0-9]{2}", basename(f))))
archivos <- archivos[order(sapply(archivos, anio_de))]
archivos <- archivos[!duplicated(sapply(archivos, anio_de))]
cat("Archivos de defunciones:", length(archivos), "\n")

traza <- list(); familia <- list(); faltantes <- list()
casos_t883 <- list(); casos_ext <- list()

for (f in archivos) {
  anio <- anio_de(f)
  d <- leer_anio(f)
  cc <- campos_de_causa(d)
  cadena <- cadena_de_codigos(d, cc)
  n_cod <- lengths(strsplit(trimws(cadena), " ", fixed = TRUE))

  es_t883 <- tiene(cadena, OBJETIVO)
  es_ext  <- tiene(cadena, EXTERNAS)

  traza[[length(traza) + 1]] <- data.table(
    anio = anio, certificados = nrow(d), campos_causa = length(cc),
    apariciones_T883 = sum(veces(cadena, OBJETIVO)),
    cert_T883 = sum(es_t883), cert_externa = sum(es_ext), ambos = sum(es_t883 & es_ext),
    codigos_por_certificado = round(mean(n_cod), 6))

  fila <- data.table(anio = anio, certificados = nrow(d))
  for (k in sprintf("T88%d", 0:9)) fila[, (k) := sum(tiene(cadena, k))]
  fila[, `:=`(anestesicas_sin_T883 = sum(tiene(cadena, ANESTESICAS)),
              anestesicas_con_T883 = sum(tiene(cadena, c(ANESTESICAS, OBJETIVO))),
              residuales  = sum(tiene(cadena, RESIDUALES)),
              familia_T88 = sum(grepl(" T88", cadena, fixed = TRUE)),
              T70_T89     = sum(grepl(" T[78]", cadena)))]
  familia[[length(familia) + 1]] <- fila

  # datos faltantes: se quitan los codigos con forma valida y se mira si queda algo
  asociadas <- cadena_de_codigos(d, setdiff(cc, "C_BAS1"))
  resto <- gsub(" [A-Z][0-9]{2}[0-9A-Z]?(?= )", "", cadena, perl = TRUE)
  faltantes[[length(faltantes) + 1]] <- data.table(
    anio = anio, certificados = nrow(d),
    sin_causa_basica     = sum(trimws(d[["C_BAS1"]]) == ""),
    sin_causas_asociadas = sum(trimws(asociadas) == ""),
    sin_ningun_codigo    = sum(n_cod == 0),
    con_codigo_no_valido = sum(nchar(trimws(resto)) > 0))

  if (any(es_t883)) {
    h <- copy(d[es_t883])
    en_campo <- sapply(cc, function(c0) tiene(cadena_de_codigos(h, c0), OBJETIVO))
    if (is.null(dim(en_campo))) en_campo <- matrix(en_campo, nrow = 1, dimnames = list(NULL, cc))
    h[, `:=`(anio = anio,
             campos_T883 = apply(en_campo, 1, function(z) paste(cc[z], collapse = ", ")),
             tambien_externa = es_ext[es_t883])]
    casos_t883[[length(casos_t883) + 1]] <- h
  }
  if (any(es_ext)) {
    h <- copy(d[es_ext])
    cad <- cadena[es_ext]
    h[, `:=`(anio = anio,
             codigo_externa = sapply(cad, function(z) paste(EXTERNAS[sapply(EXTERNAS, function(p)
               grepl(paste0(" ", p, " "), z, fixed = TRUE))], collapse = ", ")),
             tambien_T883 = es_t883[es_ext])]
    casos_ext[[length(casos_ext) + 1]] <- h
  }
  cat(sprintf("  %d: %7d certificados | T88.3 %d | causa externa %d\n",
              anio, nrow(d), sum(es_t883), sum(es_ext)))
  rm(d, cadena); gc(verbose = FALSE)
}

traza <- rbindlist(traza); familia <- rbindlist(familia); faltantes <- rbindlist(faltantes)
t883 <- rbindlist(casos_t883, fill = TRUE)
ext  <- rbindlist(casos_ext, fill = TRUE)

posicion <- function(campos) {
  sapply(strsplit(campos, ", "), function(z) {
    e <- character(0)
    if (any(grepl("^C_DIR", z))) e <- c(e, "directa")
    if (any(grepl("^C_ANT", z))) e <- c(e, "antecedente")
    if (any(grepl("^C_PAT", z))) e <- c(e, "contribuyente")
    e <- paste(e, collapse = " y ")
    paste0(toupper(substr(e, 1, 1)), substr(e, 2, nchar(e)))
  })
}

tabla4 <- t883[, .(anio, departamento = COD_DPTO,
                   sexo = fifelse(trimws(SEXO) == "1", "Hombre", "Mujer"),
                   grupo_edad = GRUPO_EDAD[GRU_ED1],
                   posicion = posicion(campos_T883), campos_T883,
                   causa_basica = C_BAS1,
                   manera = c("1" = "Natural", "2" = "Violenta", "3" = "En estudio")[trimws(PMAN_MUER)],
                   tambien_externa)]
tabla_ext <- ext[, .(anio, departamento = COD_DPTO,
                     sexo = fifelse(trimws(SEXO) == "1", "Hombre", "Mujer"),
                     grupo_edad = GRUPO_EDAD[GRU_ED1], codigo_externa,
                     causa_basica = C_BAS1, tambien_T883)]

p1 <- traza[anio <= 2018]; p2 <- traza[anio >= 2019]
N1 <- sum(p1$certificados); N2 <- sum(p2$certificados)
tasa <- function(k, n) 1e5 * k / n
union <- sum(traza$cert_T883) + sum(traza$cert_externa) - sum(traza$ambos)

conj <- c(sprintf("T88%d", 0:9), "anestesicas_sin_T883", "anestesicas_con_T883",
          "residuales", "familia_T88", "T70_T89")
f1 <- colSums(familia[anio <= 2018, ..conj]); f2 <- colSums(familia[anio >= 2019, ..conj])
tabla5 <- data.table(conjunto = conj, n_2008_2018 = f1, tasa_2008_2018 = round(tasa(f1, N1), 2),
                     n_2019_2024 = f2, tasa_2019_2024 = round(tasa(f2, N2), 2))
tabla5[, cambio_pct := round(100 * (tasa(n_2019_2024, N2) / tasa(n_2008_2018, N1) - 1))]
# no se reporta variacion con conteos menores de cinco, salvo el cero de T88.3
tabla5[(pmin(n_2008_2018, n_2019_2024) < 5) & conjunto != OBJETIVO, cambio_pct := NA]

n_previo <- sum(p1$cert_T883)
esp      <- n_previo / N1 * N2
factor   <- tasa(f2[["anestesicas_sin_T883"]], N2) / tasa(f1[["anestesicas_sin_T883"]], N1)
esp_aj   <- esp * factor
ic       <- poisson.test(n_previo)$conf.int        # intervalo exacto
esp_li   <- ic[1] / N1 * N2; esp_ls <- ic[2] / N1 * N2

prof1 <- weighted.mean(p1$codigos_por_certificado, p1$certificados)
prof2 <- weighted.mean(p2$codigos_por_certificado, p2$certificados)
ext1 <- sum(p1$cert_externa); ext2 <- sum(p2$cert_externa)

faltantes[, periodo := fifelse(anio <= 2018, "2008-2018", "2019-2024")]
falt_periodo <- faltantes[, lapply(.SD, sum), by = periodo, .SDcols = -"anio"]
for (v in c("sin_causa_basica", "sin_causas_asociadas", "sin_ningun_codigo", "con_codigo_no_valido"))
  falt_periodo[, paste0(v, "_pct") := round(100 * get(v) / certificados, 3)]

cat("\nMortalidad\n"); print(traza)
cat("\nDefunciones con T88.3\n"); print(tabla4)
cat("\nCausa externa, por codigo\n"); print(tabla_ext[, .N, by = codigo_externa][order(-N)])
cat("\nFamilia T88 (tabla 5)\n"); print(tabla5)
cat("\nDatos faltantes en los campos de causa\n"); print(t(falt_periodo))

## ---------------------------------------------------------------- RIPS

leer_hoja <- function(hoja) {
  d <- as.data.table(read_excel(RUTA_RIPS, sheet = hoja, skip = 11))
  setnames(d, trimws(names(d)))
  d <- d[!is.na(get("Año"))]
  col_edad <- if ("Edades Simples DANE" %in% names(d)) "Edades Simples DANE" else "Edad"
  d[, edad := as.numeric(sub(".*?([0-9]+).*", "\\1", get(col_edad)))]
  d[, anio := as.integer(get("Año"))]
  d[, n    := as.numeric(get("Número de Personas Atendidas"))]
  d[, dpto := trimws(sub(" - .*$", "", Departamento))]    # "-1" es no definido
  d[, mun  := trimws(sub(" - .*$", "", Municipio))]
  d[, sexo := trimws(Sexo)]
  d[]
}

h1 <- leer_hoja("Hoja1")   # consulta externa y urgencias
h2 <- leer_hoja("Hoja2")   # procedimientos
h3 <- leer_hoja("Hoja3")   # hospitalizacion

describir <- function(d) {
  e <- rep(d$edad, d$n)
  ct <- d[dpto != "-1"]
  list(registros = sum(d$n), mediana = median(e),
       p25 = round(quantile(e, .25)[[1]]), p75 = round(quantile(e, .75)[[1]]),
       min = min(e), max = max(e),
       grupos = as.vector(table(cut(e, c(-1, 4, 14, 17, 44, 64, 200)))),
       mujeres = sum(d[sexo == "FEMENINO"]$n), hombres = sum(d[sexo == "MASCULINO"]$n),
       departamentos = uniqueN(ct$dpto), municipios = uniqueN(ct$mun),
       sin_territorio = sum(d[dpto == "-1"]$n))
}
amb <- describir(h1); hosp <- describir(h3)

tabla1 <- merge(merge(
  h1[, .(consulta = sum(n[!grepl("URGENCIAS", get("Tipo de Atención"))]),
         urgencias = sum(n[grepl("URGENCIAS", get("Tipo de Atención"))])), by = anio],
  h3[, .(hospitalizacion = sum(n)), by = anio], all = TRUE, by = "anio"),
  h2[, .(procedimientos = sum(n)), by = anio], all = TRUE, by = "anio")
setnafill(tabla1, fill = 0)

h2[, cups := trimws(sub(" - .*$", "", get("Procedimiento CUPS")))]
h2[, capitulo := substr(cups, 1, 2)]
h2[, categoria := fcase(
  capitulo %in% c("90", "91"), "Laboratorio clinico",
  capitulo %in% c("87", "88"), "Imagenologia",
  capitulo == "89", "Consulta, evaluacion y procedimientos diagnosticos",
  capitulo == "93", "Terapia y rehabilitacion",
  capitulo == "95", "Otros procedimientos diagnosticos especializados",
  capitulo == "97", "Extraccion de dispositivo intrauterino",
  capitulo == "99", "Otros servicios (educacion en salud, inyecciones, odontologia preventiva)",
  default = "Procedimientos quirurgicos e invasivos")]
total_proc <- sum(h2$n)
tabla3 <- h2[, .(registros = sum(n)), by = categoria][order(-registros)]
tabla3[, pct := round(100 * registros / total_proc, 1)]
correspondencia <- h2[, .(registros = sum(n)), by = .(cups, descripcion = get("Procedimiento CUPS"),
                                                      capitulo, categoria)][order(categoria, -registros)]
top10 <- h2[, .(n = sum(n)), by = cups][order(-n)][1:10]

h2[, txt := toupper(get("Procedimiento CUPS"))]
cuenta <- function(patron) sum(h2[grepl(patron, txt)]$n)
marc <- c(potasio = cuenta("POTASIO"), lactato = cuenta("LACTATO|ACIDO LACTICO"),
          creatinquinasa = cuenta("CREATIN.?QUINASA|CPK"), mioglobina = cuenta("MIOGLOBINA"),
          gases = cuenta("GASES ARTERIAL"))
susc <- c(contractura = cuenta("CONTRACTURA|HALOTANO|CAFEINA"), biopsia = cuenta("BIOPSIA"),
          electromiografia = cuenta("ELECTROMIOGRAF"))
# estudios moleculares: se listan los candidatos y se descartan los dos de microbiologia
# (908890 virus del papiloma, 908859 panel de patogenos)
candidatos  <- h2[grepl("MOLECULAR|GENETIC|SECUENCIA|EXON|EXOMA", txt)]
moleculares <- candidatos[!(cups %in% c("908890", "908859"))]

# cadenas: mismo municipio y sexo, y la edad avanza igual que los anios
cadenas <- function(d) {
  r <- d[order(mun, sexo, edad, anio), .(anio, mun, sexo, edad)]
  usado <- rep(FALSE, nrow(r)); total <- 0L; largas <- list()
  for (i in seq_len(nrow(r))) {
    if (usado[i]) next
    usado[i] <- TRUE; total <- total + 1L
    act <- r[i]; miembros <- list(r[i])
    repeat {
      j <- which(!usado & r$mun == act$mun & r$sexo == act$sexo & r$anio > act$anio &
                   abs((r$edad - act$edad) - (r$anio - act$anio)) <= 0.5)
      if (length(j) == 0) break
      usado[j[1]] <- TRUE; act <- r[j[1]]; miembros[[length(miembros) + 1L]] <- act
    }
    if (length(miembros) > 1) largas[[length(largas) + 1L]] <- rbindlist(miembros)
  }
  list(total = total, largas = largas)
}
obs <- cadenas(h1)
set.seed(7)
nulo <- replicate(5000, { p <- copy(h1); p[, anio := sample(anio)]; length(cadenas(p)$largas) })
p_perm <- mean(nulo >= length(obs$largas))

cat("\nRIPS\n"); print(tabla1); print(tabla3)
cat("Marcadores:\n"); print(marc)
cat("Pruebas de susceptibilidad:\n"); print(susc)
print(moleculares[, .(anio, Municipio, edad, sexo, get("Procedimiento CUPS"))])
cat("Cadenas de mas de un anio:\n"); for (k in obs$largas) print(k)

## ---------------------------------------------------------------- contraste con el articulo

contraste <- data.table(resultado = character(), obtenido = character(), articulo = character())
comparar <- function(nombre, obtenido, articulo) {
  contraste <<- rbind(contraste, data.table(resultado = nombre,
    obtenido = paste(obtenido, collapse = " / "), articulo = paste(articulo, collapse = " / ")))
}
r1 <- function(x) round(x, 1)

comparar("Certificados examinados", sum(traza$certificados), 4049944)
comparar("Certificados 2008-2018 / 2019-2024", c(N1, N2), c(2310207, 1739737))
comparar("Apariciones de T88.3", sum(traza$apariciones_T883), 12)
comparar("Defunciones con T88.3", sum(traza$cert_T883), 11)
comparar("T88.3 desde 2019", sum(p2$cert_T883), 0)
comparar("T88.3 como causa basica", sum(t883$C_BAS1 == OBJETIVO), 0)
comparar("Causa basica Y48.4 entre las de T88.3", sum(t883$C_BAS1 == "Y484"), 3)
comparar("Mujeres entre las de T88.3", sum(trimws(t883$SEXO) == "2"), 7)
comparar("Defunciones con causa externa", sum(traza$cert_externa), 17)
comparar("Causa externa por periodo", c(ext1, ext2), c(13, 4))
comparar("Solapamiento / union", c(sum(traza$ambos), union), c(3, 25))
comparar("Captacion T88.3 / causa externa (%)",
         r1(100 * c(sum(traza$cert_T883), sum(traza$cert_externa)) / union), c(44, 68))
comparar("Esperadas de causa externa 2019-2024", r1(ext1 / N1 * N2), 9.8)
comparar("Codigos por certificado 2018 / 2019",
         round(c(traza[anio == 2018]$codigos_por_certificado, traza[anio == 2019]$codigos_por_certificado), 2),
         c(4.32, 4.6))
comparar("Codigos por certificado por periodo", round(c(prof1, prof2), 2), c(4.24, 4.93))
comparar("Familia T88, n", c(f1[["familia_T88"]], f2[["familia_T88"]]), c(1929, 572))
comparar("Familia T88, por 100.000",
         r1(c(tasa(f1[["familia_T88"]], N1), tasa(f2[["familia_T88"]], N2))), c(83.5, 32.9))
comparar("Anestesicas sin T88.3, n", c(f1[["anestesicas_sin_T883"]], f2[["anestesicas_sin_T883"]]), c(31, 64))
comparar("Residuales, n", c(f1[["residuales"]], f2[["residuales"]]), c(1869, 493))
comparar("Residuales sobre la familia, primer periodo (%)", r1(100 * f1[["residuales"]] / f1[["familia_T88"]]), 96.9)
comparar("T70-T89 por 100.000", round(c(tasa(f1[["T70_T89"]], N1), tasa(f2[["T70_T89"]], N2))), c(8722, 7501))
comparar("Esperados de T88.3 sin ajustar", r1(esp), 8.3)
comparar("P(0) sin ajustar", signif(dpois(0, esp), 2), 0.00025)
comparar("Esperados, intervalo", r1(c(esp_li, esp_ls)), c(4.1, 14.8))
comparar("P(0) maxima", round(dpois(0, esp_li), 3), 0.016)
comparar("Esperados ajustados", r1(esp_aj), 22.7)
comparar("Consulta externa / urgencias", c(sum(tabla1$consulta), sum(tabla1$urgencias)), c(134, 4))
comparar("Hospitalizaciones", hosp$registros, 14)
comparar("Registros de persona-procedimiento", total_proc, 467)
comparar("Codigos CUPS distintos", uniqueN(h2$cups), 161)
comparar("Edad consulta y urgencias", c(amb$mediana, amb$p25, amb$p75, amb$min, amb$max), c(36, 16, 51, 0, 90))
comparar("Grupos de edad consulta y urgencias", amb$grupos, c(15, 17, 5, 56, 30, 15))
comparar("Mujeres / hombres", c(amb$mujeres, amb$hombres), c(82, 56))
comparar("Departamentos / municipios / sin territorio",
         c(amb$departamentos, amb$municipios, amb$sin_territorio), c(20, 63, 4))
comparar("Edad hospitalizacion (mediana)", hosp$mediana, 26.5)
comparar("Hospitalizacion: hombres / mujeres / departamentos / municipios",
         c(hosp$hombres, hosp$mujeres, hosp$departamentos, hosp$municipios), c(8, 6, 9, 12))
comparar("Laboratorio clinico", c(tabla3[categoria == "Laboratorio clinico"]$registros,
                                  tabla3[categoria == "Laboratorio clinico"]$pct), c(336, 71.9))
comparar("Diez codigos mas frecuentes (%)", r1(100 * sum(top10$n) / total_proc), 31.5)
comparar("Marcadores de crisis metabolica", c(sum(marc), r1(100 * sum(marc) / total_proc)), c(32, 6.9))
comparar("Contractura / biopsia / electromiografia", susc, c(0, 0, 0))
comparar("Estudios moleculares", sum(moleculares$n), 2)
comparar("Cadenas (total / de mas de un anio)", c(obs$total, length(obs$largas)), c(131, 5))
comparar("Cadenas esperadas por azar", r1(mean(nulo)), 3.2)
contraste[, coincide := obtenido == articulo]

options(width = 200)
cat("\nContraste con las cifras del articulo\n")
print(contraste, nrows = 100)
# la permutacion depende de la semilla; con 5.000 replicas el error es de +-0,01
cat(sprintf("Permutacion: p = %.2f (articulo 0,18; entre 0,16 y 0,20 es concordante)\n", p_perm))
cat("Cifras que no coinciden:", sum(!contraste$coincide), "\n")

fwrite(contraste, file.path(SALIDA, "contraste.csv"))
fwrite(traza, file.path(SALIDA, "mortalidad_por_anio.csv"))
fwrite(tabla4, file.path(SALIDA, "defunciones_T883.csv"))
fwrite(tabla_ext, file.path(SALIDA, "causa_externa.csv"))
fwrite(tabla5, file.path(SALIDA, "familia_T88.csv"))
fwrite(faltantes, file.path(SALIDA, "faltantes_por_anio.csv"))
fwrite(falt_periodo, file.path(SALIDA, "faltantes_por_periodo.csv"))
fwrite(tabla1, file.path(SALIDA, "rips_por_anio.csv"))
fwrite(correspondencia, file.path(SALIDA, "cups_correspondencia.csv"))
cat("\nListo. Resultados en", SALIDA, "\n")
