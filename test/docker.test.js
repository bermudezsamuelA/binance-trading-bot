"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
// Dockerfile y .dockerignore (sin Docker): imagen de Node >= 22 que arranca con tsx como `npm run start:node`.
require("./setup-env");
const node_test_1 = require("node:test");
const strict_1 = __importDefault(require("node:assert/strict"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const root = path.join(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
(0, node_test_1.test)('Dockerfile: Node >= 22 (glibc), npm ci con el lock, arranque con tsx y sin dist/', () => {
    const lines = read('Dockerfile').split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    const from = lines.find(l => l.startsWith('FROM '));
    const major = Number(/^FROM node:(\d+)/.exec(from)?.[1]);
    strict_1.default.ok(major >= 22, `imagen base ${from}`);
    strict_1.default.doesNotMatch(from, /alpine/); // zeromq trae binarios para glibc
    strict_1.default.ok(lines.includes('COPY package.json package-lock.json ./'));
    strict_1.default.ok(lines.some(l => /^RUN npm ci\b/.test(l)));
    strict_1.default.ok(lines.includes('COPY src ./src'));
    strict_1.default.ok(lines.includes('STOPSIGNAL SIGINT')); // index.ts se apaga ordenadamente con SIGINT
    const cmd = JSON.parse(lines.find(l => l.startsWith('CMD ')).slice(4));
    strict_1.default.deepEqual(cmd, ['node', '--import', 'tsx', 'src/index.ts']);
    strict_1.default.doesNotMatch(lines.join('\n'), /dist\//); // en las instrucciones (no en los comentarios)
    // Lo que usa la imagen existe: tsx como dependencia instalada por npm ci y el punto de entrada
    const pkg = JSON.parse(read('package.json'));
    strict_1.default.ok(pkg.devDependencies?.tsx || pkg.dependencies?.tsx);
    strict_1.default.ok(fs.existsSync(path.join(root, 'src', 'index.ts')));
    strict_1.default.ok(JSON.parse(read('package-lock.json')).packages['node_modules/tsx']);
});
(0, node_test_1.test)('.dockerignore: nunca el .env; ni node_modules ni el cerebro Python', () => {
    const entries = read('.dockerignore').split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    for (const entry of ['.env', 'node_modules', 'binance-research', '.git'])
        strict_1.default.ok(entries.includes(entry), entry);
    strict_1.default.ok(!entries.includes('src') && !entries.includes('package.json') && !entries.includes('package-lock.json'));
});
//# sourceMappingURL=docker.test.js.map