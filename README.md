# Club Aguirre · Infantil Femenino 26/27

Web estática (carpeta `docs/`) para que padres y entrenadora consulten los partidos, marquen la disponibilidad de las jugadoras y la entrenadora publique la convocatoria.

- Datos de la liga: `docs/datos-liga.js` (partidos del Aguirre con resultado y camisetas, más la clasificación del grupo). Está **generado** desde los CSV de `source/` con `python3 scripts/generar_datos.py` (o con la skill `/actualizar-datos-liga` de Claude Code). No se edita a mano.
- Datos manuales: `docs/data.js` (plantilla de jugadoras y PIN).
- Firestore solo guarda disponibilidad y convocatoria por jornada; los datos de la liga nunca se escriben ahí.
- Las listas se guardan en Firestore (Firebase) y se sincronizan en tiempo real entre dispositivos.
- Sin `FIREBASE_CONFIG`, funciona en **modo local** (solo se guarda en el navegador): sirve para probar.

## Probar en local

```
cd docs && python3 -m http.server 8000
```
y abre http://localhost:8000

## 1. Crear Firebase (gratis)

1. Entra en https://console.firebase.google.com → **Añadir proyecto** (sin Analytics).
2. **Compilación → Firestore Database → Crear base de datos** (modo producción, región `eur3` o `europe-southwest1`).
3. Pestaña **Reglas**, pega esto y publica:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /partidos/{id} {
      allow read: if true;
      allow write: if request.resource.data.keys().hasOnly(['noDisp', 'conv'])
                   && request.resource.data.get('noDisp', []).size() <= 30
                   && request.resource.data.get('conv', []).size() <= 30;
    }
  }
}
```

4. **Configuración del proyecto (engranaje) → Tus apps → Web (`</>`)** → registra la app y copia el objeto `firebaseConfig`.
5. Pégalo en `docs/firebase-config.js` como `window.FIREBASE_CONFIG = { ... }`.

La `apiKey` de Firebase web no es un secreto; la seguridad la dan las reglas.

## 2. Publicar en GitHub Pages

Sube el repositorio a GitHub y en **Settings → Pages** elige *Deploy from a branch*, rama `main`, carpeta `/docs`.

## Límites a tener en cuenta

- No hay usuarios: cualquiera con el enlace puede cambiar la disponibilidad (es lo pedido).
- El PIN de la entrenadora (`window.PIN_ENTRENADORA` en `docs/data.js`) se comprueba en el navegador, así que es un candado de cortesía, no seguridad real: alguien con conocimientos podría verlo en el código o escribir directamente en la base de datos.
