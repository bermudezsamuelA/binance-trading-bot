# Motor de ejecución (Node.js / TypeScript). El cerebro Python (binance-research/server.py, con su .venv) corre
# aparte, fuera del contenedor: ver "Docker" en README.md.
#
#   docker build -t binance-bot-node .
#   docker run --rm --init --env-file .env -e BRAIN_ZMQ_URL=tcp://host.docker.internal:5555 binance-bot-node
#
# Node 22 o superior (las pruebas usan node --test con patrones glob). Debian (glibc) y no Alpine: zeromq trae
# binarios precompilados para glibc.
FROM node:22-bookworm-slim

WORKDIR /usr/src/app

# Dependencias exactas del package-lock, incluidas las de desarrollo: tsx ejecuta el TypeScript sin compilar
# (igual que `npm run start:node`) y no hay carpeta dist/.
COPY package.json package-lock.json ./
RUN npm ci && npm cache clean --force

COPY tsconfig.json ./
COPY src ./src

ENV NODE_ENV=production
# index.ts cierra ordenadamente con SIGINT (aviso de Telegram incluido): docker stop envía SIGINT en vez de SIGTERM
STOPSIGNAL SIGINT
# node con el cargador de tsx (sin proceso intermedio): Node es quien recibe las señales
CMD ["node", "--import", "tsx", "src/index.ts"]
