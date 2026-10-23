// Comisiones con BNB: saldo mínimo, comisión cobrada en otro activo y la opción de la cuenta (solo mainnet).
import './setup-env';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BNB_MIN_USDT, BnbFeeMonitor, feeAssets } from '../src/api/bnb-fees';

const fill = (commissionAsset: string, commission = 0.001) => ({ price: 1, qty: 1, commission, commissionAsset });

class Rest {
    bnb = 0.01;            // 6 USDT a 600
    price = 600;
    burn: boolean | Error = true;
    balanceCalls = 0;
    async getFreeBalances() { this.balanceCalls++; return new Map([['BNB', this.bnb], ['USDT', 100]]); }
    async getPrice(symbol: string) { assert.equal(symbol, 'BNBUSDT'); return this.price; }
    async getBnbBurnStatus() { if (this.burn instanceof Error) throw this.burn; return { spotBNBBurn: this.burn }; }
}

function monitor(opts: { enabled?: boolean; market?: string } = {}) {
    const rest = new Rest();
    const alerts: string[] = [];
    const m = new BnbFeeMonitor(rest, msg => alerts.push(msg), { enabled: opts.enabled ?? true, market: opts.market ?? 'mainnet' });
    return { rest, alerts, m };
}

test('feeAssets: activos con comisión > 0, sin repetir', () => {
    assert.deepEqual(feeAssets({ fills: [fill('BNB'), fill('BNB'), fill('DOGE', 0)] }), ['BNB']);
    assert.deepEqual(feeAssets({ fills: [fill('BNB'), fill('USDT')] }), ['BNB', 'USDT']);
});

test('saldo de BNB bajo: un aviso, y otro solo después de reponerlo', async () => {
    const { rest, alerts, m } = monitor();
    assert.equal(await m.checkBalance(), 6);
    assert.equal(alerts.length, 0);
    rest.bnb = (BNB_MIN_USDT - 0.5) / 600;
    await m.checkBalance();
    await m.checkBalance();
    assert.equal(alerts.length, 1);
    assert.match(alerts[0]!, /BNB BAJO/);
    rest.bnb = 0.02;
    await m.checkBalance();
    rest.bnb = 0;
    assert.equal(await m.checkBalance(), 0);
    assert.equal(alerts.length, 2);
});

test('comisión cobrada en otro activo: aviso una vez hasta que vuelva a salir en BNB; siempre revisa el saldo', async () => {
    const { rest, alerts, m } = monitor({ market: 'testnet' });
    await m.afterTrade('DOGEUSDT', { fills: [fill('BNB')] });
    assert.equal(alerts.length, 0);
    await m.afterTrade('DOGEUSDT', { fills: [fill('DOGE')] });
    await m.afterTrade('SOLUSDT', { fills: [fill('USDT')] });
    assert.equal(alerts.length, 1);
    assert.match(alerts[0]!, /COMISIÓN SIN BNB: DOGEUSDT/);
    assert.match(alerts[0]!, /testnet/);
    await m.afterTrade('DOGEUSDT', { fills: [fill('BNB')] });
    await m.afterTrade('DOGEUSDT', { fills: [fill('DOGE')] });
    assert.equal(alerts.length, 2);
    assert.equal(rest.balanceCalls, 5);
});

test('opción de la cuenta: solo en mainnet; apagada -> aviso; error -> null sin aviso', async () => {
    const a = monitor();
    assert.equal(await a.m.checkAccountSetting(), true);
    a.rest.burn = false;
    assert.equal(await a.m.checkAccountSetting(), false);
    assert.match(a.alerts[0]!, /BNB DESACTIVADO/);
    a.rest.burn = new Error('sin red');
    assert.equal(await a.m.checkAccountSetting(), null);
    assert.equal(a.alerts.length, 1);
    assert.equal(await monitor({ market: 'testnet' }).m.checkAccountSetting(), null);
});

test('desactivado (PAY_FEES_WITH_BNB=0): no consulta ni avisa', async () => {
    const { rest, alerts, m } = monitor({ enabled: false });
    rest.bnb = 0;
    assert.equal(await m.checkBalance(), null);
    await m.afterTrade('DOGEUSDT', { fills: [fill('DOGE')] });
    assert.equal(await m.checkAccountSetting(), null);
    assert.equal(rest.balanceCalls, 0);
    assert.equal(alerts.length, 0);
});
