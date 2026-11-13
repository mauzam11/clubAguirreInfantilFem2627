# CLAUDE.md

Guía para trabajar en este repositorio. Idioma del proyecto (UI, comentarios, commits): **español**.

## Qué es

Web estática del **Club Aguirre · Infantil Femenino (fútbol sala) · temporada 2026-27**. Sirve para que:

- las familias vean los partidos del equipo (fecha, hora, instalación, camisetas, resultado) y marquen qué jugadoras **no están disponibles**;
- la entrenadora (con PIN) publique la **convocatoria** de cada jornada;
- todos consulten la **clasificación** del grupo.

Se publica con GitHub Pages desde la rama `main`, carpeta `/docs`. No hay build, bundler ni dependencias npm.

## Estructura

```
docs/                       Sitio publicado (GitHub Pages)
  index.html                Marcado: cabecera, pestañas Partidos/Clasificación, diálogo de PIN, toast
  app.js                    Toda la lógica de UI y almacenamiento (JS vanilla, sin módulos propios)
  styles.css                Estilos (fuentes Anton y Archivo; verde del club #066e50/#089369 y blanco, sin dorado; tema oscuro por defecto y claro con [data-theme="light"])
  data.js                   MANUAL: window.JUGADORAS (plantilla) y window.PIN_ENTRENADORA
  datos-liga.js             GENERADO: window.LIGA, window.PARTIDOS, window.CLASIFICACION
  firebase-config.js        window.FIREBASE_CONFIG (la apiKey web no es secreta)
  assets/                   logo.png, cabecera.jpg
scripts/generar_datos.py    Genera docs/datos-liga.js desde los CSV de source/
source/                     Entrada: CSV de la federación (ignorados por git, ~13 MB) y Calendario_Futbol_Sala_2026-27.xlsx
.claude/skills/actualizar-datos-liga/SKILL.md   Skill que automatiza la actualización de datos
README.md                   Guía de Firebase, reglas de Firestore y publicación
```

Orden de carga de scripts en `index.html`: `data.js` → `datos-liga.js` → `firebase-config.js` → `app.js`. Todo se comunica por variables globales de `window`.

## Flujo de datos (dos fuentes separadas)

1. **Datos de la liga** (partidos del Aguirre, resultados, camisetas, clasificación): viven **solo** en `docs/datos-liga.js`, generado por `scripts/generar_datos.py`. **No se edita a mano** ni se escribe nunca en Firestore.
2. **Datos de los usuarios** (disponibilidad y convocatoria): Firestore, colección `partidos`, un documento por jornada `j{N}` con los campos `noDisp` (array de nombres no disponibles) y `conv` (array de convocadas). Se sincroniza en tiempo real con `onSnapshot`.

Consecuencia importante: las marcas en Firestore están ligadas al **número de jornada**; por eso el script no renumera jornadas y respeta las del CSV.

### Actualizar datos de la liga

Cuando el usuario sube CSV nuevos a `source/` o pide actualizar resultados/clasificación, usar la skill `/actualizar-datos-liga` o ejecutar desde la raíz:

```
python3 scripts/generar_datos.py
```

- Detecta el CSV de **partidos** (cabecera con `Codigo_equipo1`) y el de **clasificación** (cabecera con `Puntos`) por su cabecera, no por nombre; usa el más reciente de cada tipo.
- Filtra por `CLUB`, `DEPORTE` y `CATEGORIA` (constantes al inicio del script: «Club Aguirre», «FUTBOL SALA», «INFANTIL FEMENINO»). Falla si no hay exactamente 1 grupo del club.
- Normaliza cualquier variante del club (`Club Aguirre A`, `Club AGUIRRE`…) a «Club Aguirre».
- Solo conserva los partidos del Aguirre, pero la clasificación es la del grupo entero. Si el CSV de clasificación aún no trae el grupo, la **calcula** con los partidos finalizados (3 pts victoria, 1 empate; desempate por diferencia de goles, goles a favor, nombre) y marca `origenClasificacion: "calculada"`.
- Imprime «Cambios respecto a la versión anterior» (resultados nuevos, cambios de fecha/hora/instalación/camiseta, movimientos en la tabla). Hay que resumirlos al usuario destacando cambios de fecha, hora o instalación.
- **No hacer commit ni push** tras regenerar: el usuario revisa y publica.

Estado actual: grupo «JDM SAL SABDOM FS INF FEM», datos generados el 2026-11-13, primera jornada el 2026-11-14.

## Cómo funciona `docs/app.js`

- `crearStore()`: usa Firestore (SDK 10.12.2 cargado por `import()` dinámico desde gstatic) si hay `FIREBASE_CONFIG`; si no o falla, `storeLocal()` (localStorage → **modo local**, útil para probar). Interfaz común: `suscribir(cb)`, `setDisponible(j, nombre, si)`, `setConvocadas(j, lista)`.
- `setDisponible` usa `arrayUnion/arrayRemove` para no pisar cambios simultáneos de varios padres.
- `estadoDe(j)` calcula disponibles/no disponibles/convocadas; una jugadora no disponible nunca cuenta como convocada.
- Modo entrenadora: botón de candado → diálogo de PIN comparado con `window.PIN_ENTRENADORA`; se recuerda en `sessionStorage` (`entrenadora`).
- Camisetas: `COLORES` (lista de palabras) y `colorCss()` traducen el texto libre del CSV a una muestra de color. Si aparece un color sin muestra, añadir su palabra a `COLORES`.
- `tarjeta(p)` pinta cada partido (desplegable); `proximo` es el primer partido con fecha ≥ hoy. `renderClasificacion()` pinta la tabla y resalta al Aguirre; `mostrarVista()` alterna pestañas.
- Todo texto dinámico pasa por `esc()` antes de insertarse en HTML.

## Firestore y seguridad

Reglas (ver README): lectura pública; escritura solo en `partidos/{id}` con claves `noDisp` y `conv` y máximo 30 elementos cada una. No hay usuarios: cualquiera con el enlace puede cambiar disponibilidad (es lo pedido). El PIN se comprueba en el navegador, es un candado de cortesía, **no seguridad real**.

## Probar en local

```
cd docs && python3 -m http.server 8000   # http://localhost:8000
```

Sin Firebase configurado funciona en modo local. No hay tests ni linter.

## Reglas para Claude

- No tocar Firestore ni sus reglas desde aquí.
- No editar `docs/datos-liga.js` a mano; regenerarlo con el script.
- Jugadoras y PIN se cambian en `docs/data.js`.
- Mantener el proyecto sin dependencias ni paso de build; JS vanilla y CSS plano.
- Textos de interfaz en español, accesibles (roles ARIA, `aria-live`, etiquetas) como ya están.
- No hacer commit/push sin que el usuario lo pida. Los commits llevan el mensaje en español.
- Los CSV de `source/` no se versionan (`.gitignore`); el `.xlsx` del calendario sí.
