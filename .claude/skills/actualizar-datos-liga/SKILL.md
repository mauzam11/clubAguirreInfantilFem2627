---
name: actualizar-datos-liga
description: Actualiza partidos, resultados, camisetas y clasificación de la web del Club Aguirre Infantil Femenino a partir de los últimos CSV subidos a source/. Úsala cuando el usuario diga que ha subido ficheros nuevos, o pida actualizar la liga, los resultados o la clasificación.
---

# Actualizar datos de la liga

Regenera `docs/datos-liga.js` (partidos del Club Aguirre + clasificación del grupo) desde los CSV más recientes de `source/`.

## Pasos

1. Comprueba qué hay en `source/` con `ls -lt source/`. Los CSV vienen del volcado de Juegos Deportivos Municipales de Madrid: uno de **partidos** (cabecera con `Codigo_equipo1`) y otro de **clasificación** (cabecera con `Puntos`). El script los reconoce por la cabecera, no por el nombre, y usa el más reciente de cada tipo. Si el usuario subió solo uno de los dos, el otro se reutiliza tal cual está: dilo en el resumen.
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
