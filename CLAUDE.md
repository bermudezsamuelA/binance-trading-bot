# Instrucciones del proyecto

## Git

- El comando de git de este usuario es `git2`, no `git`. Usa `git2` en todos los comandos de git que sugieras o ejecutes.
- El autor de los commits es `tlou520 <212600710+tlou520@users.noreply.github.com>`. Antes de hacer commit, verifica con `git2 config user.name` y `git2 config user.email` que coincidan con ese autor; si no, avisa al usuario.
- No hagas commit ni push sin que el usuario lo pida expresamente.
- La rama de trabajo actual es `Improvement-experiment-on-v1`. No cambies a `main` ni crees ramas sin confirmar.

## Ejecución del bot y VPN

- El usuario usa VPN. Mientras la VPN está activa, las llamadas a Binance (testnet incluida) pueden fallar, y el asistente no puede correr el bot ni probar conexiones con Binance.
- Para ejecutar el bot contra la testnet, el usuario debe desactivar la VPN y lanzarlo manualmente (`npm run dev` o `npm run start:python` y `npm run start:node`).
- Mientras el usuario lo corre así, el asistente no podrá usarse para esa parte: no pidas ni supongas que el asistente ejecutará el bot con Binance.
- Antes de sugerir comandos que llamen a Binance, recuerda al usuario que debe tener la VPN desactivada.
- Si un comando es necesario y el asistente no puede ejecutarlo (por ejemplo, porque requiere Binance o la VPN), no lo ejecutes: escríbelo como último paso de la respuesta, en un bloque de código, para que el usuario lo corra manualmente.

## Disco de instalación

- El disco C tiene poco espacio. Siempre que sugieras una descarga o instalación pesada, usa el disco E.
- Caché y temporales en E: pip (`PIP_CACHE_DIR=E:\pip-cache`), npm (`npm config set cache "E:\npm-cache" --global`), y `TMP`/`TEMP` apuntando a `E:\tmp`.
- Herramientas instaladas en E: Node.js en `E:\Programas\nodejs` (instalar con `winget install OpenJS.NodeJS.LTS --location "E:\Programas\nodejs"` o con el zip de nodejs.org si winget ignora la ruta).
- Las dependencias del proyecto (`node_modules`, `.venv`) están dentro de la carpeta del proyecto, que ya está en E.
- En WSL, las rutas del disco E son `/mnt/e/...`, nunca `/e/...`.

## Documentación

- Los documentos del proyecto están en `doc/` y están versionados en esta rama.
