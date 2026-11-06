// Dockerfile y .dockerignore (sin Docker): imagen de Node >= 22 que arranca con tsx como `npm run start:node`.
import './setup-env';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'fs';
import * as path from 'path';

const root = path.join(__dirname, '..');
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

test('Dockerfile: Node >= 22 (glibc), npm ci con el lock, arranque con tsx y sin dist/', () => {
    const lines = read('Dockerfile').split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    const from = lines.find(l => l.startsWith('FROM '))!;
    const major = Number(/^FROM node:(\d+)/.exec(from)?.[1]);
    assert.ok(major >= 22, `imagen base ${from}`);
    assert.doesNotMatch(from, /alpine/);                          // zeromq trae binarios para glibc
    assert.ok(lines.includes('COPY package.json package-lock.json ./'));
    assert.ok(lines.some(l => /^RUN npm ci\b/.test(l)));
    assert.ok(lines.includes('COPY src ./src'));
    assert.ok(lines.includes('STOPSIGNAL SIGINT'));               // index.ts se apaga ordenadamente con SIGINT
    const cmd = JSON.parse(lines.find(l => l.startsWith('CMD '))!.slice(4));
    assert.deepEqual(cmd, ['node', '--import', 'tsx', 'src/index.ts']);
    assert.doesNotMatch(lines.join('\n'), /dist\//);              // en las instrucciones (no en los comentarios)
    // Lo que usa la imagen existe: tsx como dependencia instalada por npm ci y el punto de entrada
    const pkg = JSON.parse(read('package.json'));
    assert.ok(pkg.devDependencies?.tsx || pkg.dependencies?.tsx);
    assert.ok(fs.existsSync(path.join(root, 'src', 'index.ts')));
    assert.ok(JSON.parse(read('package-lock.json')).packages['node_modules/tsx']);
});

test('.dockerignore: nunca el .env; ni node_modules ni el cerebro Python', () => {
    const entries = read('.dockerignore').split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    for (const entry of ['.env', 'node_modules', 'binance-research', '.git']) assert.ok(entries.includes(entry), entry);
    assert.ok(!entries.includes('src') && !entries.includes('package.json') && !entries.includes('package-lock.json'));
});
