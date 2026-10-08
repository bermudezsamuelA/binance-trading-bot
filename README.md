# Binance Quant Trading Bot 🚀

Sistema algorítmico de trading cuantitativo de alto rendimiento. Diseñado con una arquitectura de doble motor que separa la ejecución instantánea en el mercado (Node.js) del procesamiento matemático y Machine Learning pesado (Python). 

Incluye notificaciones ejecutivas en tiempo real vía Telegram y opera de forma segura a través de la Testnet de Binance.

## 🏗️ Arquitectura del Sistema

El bot opera bajo una estructura modular comunicada internamente mediante **ZeroMQ (ZMQ)**:
*   **Motor de Ejecución (Node.js / TypeScript):** Mantiene la conexión WebSocket con Binance, gestiona el libro de órdenes, administra el riesgo en milisegundos y despacha alertas a Telegram.
*   **Cerebro Cuantitativo (Python 3.12):** Alberga las estrategias matemáticas (Mean Reversion, VWAP, Volatility Squeeze) y el filtro táctico de Machine Learning (XGBoost).
*   **Ledger Local:** Registro CSV transaccional inmutable que asegura la persistencia de las operaciones abiertas/cerradas ante reinicios inesperados.

---

## 📋 Requisitos Previos

Para desplegar este proyecto en un entorno local o servidor, necesitas:
*   **Node.js** (v18 o superior)
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
    pip install pandas numpy pyzmq requests binance-historical-data xgboost hmmlearn scikit-learn stable-baselines3

Variables de Entorno
    Crea un archivo .env en la raíz del proyecto con la siguiente estructura. 
    Nunca subas este archivo al control de versiones.

    BINANCE_API_KEY="tu_api_key_de_testnet"
    BINANCE_API_SECRET="tu_api_secret_de_testnet"
    BINANCE_REST_URL="[https://testnet.binance.vision/api](https://testnet.binance.vision/api)"
    BINANCE_WS_URL="wss://stream.testnet.binance.vision/ws"
    TELEGRAM_BOT_TOKEN="tu_token_generado_por_botfather"
    TELEGRAM_CHAT_ID="tu_id_numerico_personal"

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


Entrenamiento del Modelo (XGBoost)
    Antes de encender el bot por primera vez, el sistema de Inteligencia Artificial debe aprender del comportamiento histórico del mercado para optimizar sus hiperparámetros.

    Asegúrate de tener tu entorno virtual de Python activado y ejecuta:

        python machine_learning_strategies/ml_evaluator.py

    Este script:
        Analizará los CSV de datos históricos.
        Evaluará cientos de combinaciones de estrategias (Grid Search).
        Entrenará un árbol de decisión institucional (XGBoost) para filtrar falsas rupturas.
        Generará un archivo ml_results.json con las configuraciones más rentables, listo para ser consumido por el motor en vivo.

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

dejando rastro a quien desee aportar y lograr un codigo que nos libre de ir a la oficina
