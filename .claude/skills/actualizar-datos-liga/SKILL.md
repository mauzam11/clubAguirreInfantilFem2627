---
name: actualizar-datos-liga
description: Actualiza partidos, resultados, camisetas y clasificación de la web del Club Aguirre Infantil Femenino. Descarga los últimos CSV de Datos Madrid (o usa los que el usuario haya subido a source/) y regenera docs/datos-liga.js. Úsala cuando el usuario pida actualizar la liga, los resultados o la clasificación, o diga que ha subido ficheros nuevos.
---

# Actualizar datos de la liga

Regenera `docs/datos-liga.js` (partidos del Club Aguirre + clasificación del grupo) desde los CSV más recientes de `source/`.

## Pasos

1. **Consigue los CSV.** Salvo que el usuario diga que ya los ha subido él a `source/`, descárgalos desde la raíz del proyecto:
   ```
   python3 -I scripts/descargar_csv.py
   ```
   Baja de Datos Madrid el CSV de partidos y el de clasificaciones vigentes (se publican cada miércoles) y los guarda en `source/` como `partidos_AAAAMMDD.csv` y `clasificaciones_AAAAMMDD.csv`. Si el contenido es idéntico al que ya hay, lo dice y no guarda nada: en ese caso informa al usuario de que no hay datos nuevos y para ahí (puedes mirar antes qué hay publicado con `--comprobar`). Si falla la descarga o la validación, no inventes ni reutilices nada: informa al usuario.
   Después comprueba `source/` con `ls -lt source/`. Los CSV son de **partidos** (cabecera con `Codigo_equipo1`) y de **clasificación** (cabecera con `Puntos`). El script de generación los reconoce por la cabecera, no por el nombre, y usa el más reciente de cada tipo. Si solo hay uno nuevo de los dos, el otro se reutiliza tal cual está: dilo en el resumen.
2. Ejecuta desde la raíz del proyecto:
   ```
   python3 scripts/generar_datos.py
   ```
   Si falla con «Se esperaba 1 grupo…», el CSV no contiene el grupo de Club Aguirre (INFANTIL FEMENINO, FUTBOL SALA). No inventes datos: informa al usuario.
3. Resume al usuario la sección «Cambios respecto a la versión anterior» que imprime el script: resultados nuevos, cambios de fecha, hora, instalación o camiseta, y movimientos en la clasificación. Destaca los cambios de fecha, hora o instalación, porque los padres tendrán que enterarse.
4. Avisa si algún partido sigue sin hora o instalación, y si la clasificación es «calculada» (el CSV de clasificación aún no trae el grupo) o viene del CSV.
5. **No hagas commit ni push.** Deja los cambios en el árbol de trabajo para que el usuario los revise y publique (GitHub Pages sirve `docs/`).

## Reglas del proyecto

- **No toques Firestore.** Ahí solo se guardan la disponibilidad y la convocatoria (`partidos/j{jornada}` con `noDisp` y `conv`), y las reglas de seguridad rechazan cualquier otro campo. Los datos de la liga viven solo en `docs/datos-liga.js`.
- Las marcas de las jugadoras en Firestore están ligadas al **número de jornada**. Por eso el script no renumera jornadas: respeta las del CSV.
- No edites `docs/datos-liga.js` a mano (se regenera). Las jugadoras y el PIN están en `docs/data.js`, que sí es manual.
- Los nombres del club (`Club Aguirre A`, `Club AGUIRRE`…) se normalizan a «Club Aguirre».
- Los colores de camiseta son texto libre del CSV. Si aparece uno que la web no reconoce (se ve sin color en la muestra), añade su palabra a la lista `COLORES` de `docs/app.js`.
- Si cambian el equipo, la categoría o el club, las constantes `CLUB`, `DEPORTE` y `CATEGORIA` están al principio de `scripts/generar_datos.py`.
