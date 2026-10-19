# Binance Quant Trading Bot 🚀

Sistema algorítmico de trading cuantitativo de alto rendimiento. Diseñado con una arquitectura de doble motor que separa la ejecución instantánea en el mercado (Node.js) del procesamiento matemático y Machine Learning pesado (Python). 

Incluye notificaciones ejecutivas en tiempo real vía Telegram. El mercado (Testnet o real) lo decide una sola variable, `BINANCE_MARKET`, en el archivo `.env`.

## 🏗️ Arquitectura del Sistema

El bot opera bajo una estructura modular comunicada internamente mediante **ZeroMQ (ZMQ)**:
*   **Motor de Ejecución (Node.js / TypeScript):** Mantiene la conexión WebSocket con Binance, gestiona el libro de órdenes, administra el riesgo en milisegundos y despacha alertas a Telegram.
*   **Cerebro Cuantitativo (Python 3.12):** Alberga las estrategias matemáticas (Mean Reversion, Trend Following, VWAP, Volatility Squeeze), que deciden con cada vela **cerrada** de 15 minutos, y la selección *walk-forward* que decide qué estrategia usa cada moneda (o si no opera). También entrena un modelo XGBoost experimental que hoy no filtra ninguna operación.
*   **Ledger Local:** Registro CSV transaccional inmutable que asegura la persistencia de las operaciones abiertas/cerradas ante reinicios inesperados. Cada compra se anota como `PENDING` (con su `client_order_id`) **antes** de enviarse y pasa a `OPEN`/`CLOSED`, o a `CANCELLED` si Binance no la tiene: si el proceso muere con la compra en vuelo, al arrancar se busca en Binance y se adopta. Una orden que Binance tarda en mostrar se vuelve a consultar a los 10, 30 y 90 s antes de darla por inexistente (sin bloquear el resto del bot). El PnL de cada operación es neto de comisiones y valora al precio de venta el residuo que queda por debajo del `stepSize` de Binance.

---

## 📋 Requisitos Previos

Para desplegar este proyecto en un entorno local o servidor, necesitas:
*   **Node.js** (v22 o superior; `npm test` usa `node --test` con patrones *glob* y `mock.timers`, que no existen en v18)
*   **Python 3.12** (⚠️ *Estrictamente v3.12 o v3.11*. Versiones más recientes como 3.14 fallarán al compilar las librerías C++ de Machine Learning en Windows).
*   Cuenta en **Binance Testnet** (API Keys).
*   Un Bot de **Telegram** (Token provisto por BotFather).

---

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio
```bash
    git clone <tu-repositorio>
    cd binance-trading-bot

(10/08/26) construido con 
    node 24.19.0 usando nvm
    Python 3.12


 Entorno Node.js (Motor de Ejecución)
    Instala las dependencias de TypeScript y ejecución:
    npm install

Entorno Python (Machine Learning)
    Es crucial aislar las librerías matemáticas en un entorno virtual. Ejecuta los siguientes comandos desde la raíz del proyecto:
    cd binance-research
    py -3.12 -m venv .venv

    # Activar entorno virtual (Windows)
    .\.venv\Scripts\Activate

    # Instalar dependencias pesadas (utilizando ruedas pre-compiladas)
    pip install pandas numpy scipy pyzmq requests binance-historical-data xgboost hmmlearn scikit-learn stable-baselines3

Variables de Entorno
    Crea un archivo .env en la raíz del proyecto con la siguiente estructura. 
    Nunca subas este archivo al control de versiones.

    BINANCE_API_KEY="tu_api_key_de_testnet"
    BINANCE_API_SECRET="tu_api_secret_de_testnet"
    BINANCE_MARKET="testnet"
    TELEGRAM_BOT_TOKEN="tu_token_generado_por_botfather"
    TELEGRAM_CHAT_ID="tu_id_numerico_personal"
    # Opcional, solo en la testnet: carga estrategias NO validadas para ver al bot operar
    # ALLOW_UNVALIDATED_STRATEGIES=1

    BINANCE_MARKET elige el mercado de todo el bot: "testnet" (por defecto) o "mainnet". Con esa sola
    variable Node.js arma las URL del REST y del WebSocket, y Python precarga las velas del mismo mercado.
    BINANCE_REST_URL y BINANCE_WS_URL ya no se usan (si siguen en el .env, Node.js avisa y las ignora).
    ALLOW_UNVALIDATED_STRATEGIES=1 solo tiene efecto con BINANCE_MARKET="testnet" (ver "Selección de estrategias").
    BRAIN_ZMQ_BIND (Python) y BRAIN_ZMQ_URL (Node.js) son opcionales: dirección del canal ZMQ entre ambos motores
    (por defecto tcp://127.0.0.1:5555). Solo hacen falta si Node.js corre en Docker (ver más abajo).

### Obtener credenciales de Binance Testnet
A diferencia de la cuenta real, la red de pruebas no requiere KYC ni depósitos reales.
    1. Ingresa a [Binance Spot Test Network](https://testnet.binance.vision/).
    2. Inicia sesión vinculando tu cuenta de GitHub.
    3. Haz clic en el botón **Generate HMAC_SHA256 Key**.
    4. Nombra tu llave (ej. `quant-bot`) y haz clic en generar.
    5. Copia la `API Key` y la `Secret Key`. **Pégalas inmediatamente en tu archivo `.env`**, ya que por seguridad la plataforma no te volverá a mostrar la Secret Key si cierras la ventana.

Para obtener tu TELEGRAM_CHAT_ID numérico personal, sigue estos pasos en Telegram:
    Abre el buscador y escribe @userinfobot (o @getmyid_bot).
    Selecciona el bot y presiona Start (o envía el comando /start).
    El bot te responderá instantáneamente con la información de tu cuenta.
    Copia el número que aparece en la línea Id: (suele tener entre 8 y 10 dígitos, por ejemplo, 123456789).
    Pega ese número exacto en tu archivo .env.

Para obtener tu TELEGRAM_BOT_TOKEN Crea el Bot en Telegram (BotFather)
    Busca al creador: Abre Telegram y escribe @BotFather en el buscador (asegúrate de elegir la cuenta con la insignia de verificación azul).
    Inicia el proceso: Abre el chat, presiona "Start" y envía el comando /newbot.
    Bautiza a tu bot: Escribe el nombre visible que deseas que tenga.
    Crea el identificador (Username): Escribe un nombre de usuario único que termine obligatoriamente en la palabra "bot"
    Asegura el Token API: BotFather generará un mensaje de confirmación exitosa. Copia el texto largo que aparece debajo de Use this token to access the HTTP API (se verá similar a 123456789:ABCdefGHIjklmNOPQrsTUVwxyZ). Esta es la llave maestra para que el código controle al bot.


Selección de estrategias (walk-forward)
    Antes de encender el bot, hay que elegir qué estrategia y qué parámetros usa cada moneda. Las velas
    históricas de 15 minutos las descarga server.py al arrancar (o python download_data.py).

    Con el entorno virtual de Python activado, desde binance-research/ ejecuta (tarda unos 2 minutos):

        python machine_learning_strategies/ml_evaluator.py

    Este script:
        Comprueba que su simulación rápida da exactamente las mismas operaciones que el backtest de referencia.
        Simula las 4 estrategias con 299 combinaciones de parámetros sobre toda la historia descargada.
        Elige los parámetros mes a mes con los 6 meses anteriores y los prueba en el mes siguiente (walk-forward),
        y reserva el último mes completo y los días del mes en curso como validación final.
        Marca cada estrategia como "validada" o "rechazada" (ganancia fuera de muestra con significancia
        estadística) y guarda todo en machine_learning_strategies/ml_results.json.
        Entrena un modelo XGBoost con el último mes (experimental: no se usa en vivo).

    El bot en vivo solo carga estrategias validadas. Si ninguna lo está, no abre operaciones y explica por
    consola el motivo de cada moneda; es un resultado válido. Para ver al bot operar en la testnet de todos
    modos, ALLOW_UNVALIDATED_STRATEGIES=1 en el .env carga en cada moneda la mejor estrategia NO validada
    (lo esperable es que pierda dinero). Detalles en doc/matematica-del-bot.md (Parte 4, sección 14).

Ejecución del Bot

    El sistema requiere que ambos motores se ejecuten simultáneamente. 
    Abre dos terminales distintas:
        Terminal 1 (El Cerebro - Python):
            npm run start:python
    (Espera a que indique que el socket TCP está escuchando en el puerto 5555).
        Terminal 2 (El Ejecutor - Node.js):
            npm run start:node

### ⚡ Opcional: Ejecución Simultánea (Un solo comando)
Si prefieres automatizar el arranque y no lidiar con dos ventanas de consola, puedes iniciar el Cerebro (Python) y el Ejecutor (Node.js) al mismo tiempo utilizando `concurrently`. 

Ejecuta este comando desde la raíz del proyecto:
    ```bash
    npm run dev

    (Nota: Ambos procesos compartirán la misma terminal. Verás los logs de Node y Python intercalados y etiquetados por colores).

### 🐳 Opcional: Motor Node.js en Docker
La imagen (`Dockerfile`, Node 22 sobre Debian) contiene solo el motor de ejecución: `package*.json`, `tsconfig.json`
y `src/`. Se ejecuta con `tsx`, como `npm run start:node` (no hay `dist/`). El cerebro Python sigue fuera del
contenedor, con su `.venv`, y se arranca como siempre con `npm run start:python`.

1. Python tiene que aceptar la conexión del contenedor. Añade al `.env`:

        BRAIN_ZMQ_BIND="tcp://0.0.0.0:5555"

   (Por defecto escucha solo en `127.0.0.1`. Con `0.0.0.0` el puerto 5555 queda abierto a la red local: ciérralo en
   el firewall si la red no es de confianza.)

2. Construye la imagen y ejecútala (desde la raíz del proyecto; la VPN debe estar desactivada para llegar a Binance):

        docker build -t binance-bot-node .
        docker run --rm --init --env-file .env -e BRAIN_ZMQ_URL=tcp://host.docker.internal:5555 binance-bot-node

   - `--env-file .env`: credenciales y `BINANCE_MARKET`. El `.env` nunca entra en la imagen (`.dockerignore`).
   - `BRAIN_ZMQ_URL`: dónde está el cerebro Python. Con Docker Desktop (Windows/macOS) es `host.docker.internal`;
     en Linux añade `--add-host=host.docker.internal:host-gateway`, o usa `--network host` y deja los valores por
     defecto (`tcp://127.0.0.1:5555`) sin `BRAIN_ZMQ_BIND`.
   - `docker stop` envía SIGINT: el bot se apaga ordenadamente y avisa por Telegram.

### 🧪 Pruebas
Las pruebas no llaman a Binance. Desde la raíz del proyecto:
    ```bash
    npm test              # pruebas de Node.js (test/*.test.ts)
    npm run test:python   # pruebas de Python (ledger, resumen, servidor, carga de estrategias y walk-forward)
    ```
Para comprobar que la simulación rápida del selector coincide con el backtest de referencia (unos 3 minutos):
    ```bash
    cd binance-research
    .venv\Scripts\python fast_backtest.py
    ```

dejando rastro a quien desee aportar y lograr un codigo que nos libre de ir a la oficina
