// USDT ocioso en Simple Earn flexible: solo mainnet, deja libre la reserva, suscribe el resto y rescata antes de comprar.
import './setup-env';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EarnManager, FlexibleProduct, floorUsdt } from '../src/api/earn';

class Rest {
    free = 100;
    inEarn = 500;
    product: FlexibleProduct | null = { productId: 'USDT001', apr: 0.05, minPurchase: 0.1, canPurchase: true, canRedeem: true };
    subs: string[] = [];
    redeems: string[] = [];
    arriveAfterPolls = 1;      // el rescate llega al saldo libre tras n consultas
    failRedeem = false;
    private pending = 0;
    private polls = 0;
    async getFreeBalances() {
        if (this.pending && ++this.polls >= this.arriveAfterPolls) { this.free += this.pending; this.pending = 0; }
        return new Map([['USDT', this.free]]);
    }
    async getFlexibleProduct(asset: string) { assert.equal(asset, 'USDT'); return this.product; }
    async getFlexiblePosition() { return this.inEarn; }
    async subscribeFlexible(productId: string, amount: string) {
        assert.equal(productId, 'USDT001'); this.subs.push(amount); this.free -= parseFloat(amount); this.inEarn += parseFloat(amount);
    }
    async redeemFlexible(_p: string, amount: string) {
        if (this.failRedeem) throw new Error('rechazado');
        this.redeems.push(amount); this.inEarn -= parseFloat(amount); this.pending = parseFloat(amount); this.polls = 0;
    }
}

function make(opts: { market?: string; enabled?: boolean } = {}) {
    const rest = new Rest();
    const alerts: string[] = [];
    const sleeps: number[] = [];
    const earn = new EarnManager(rest, m => alerts.push(m), {
        enabled: opts.enabled ?? true, market: opts.market ?? 'mainnet', tradeQuoteUsdt: 15,
        sleep: async ms => { sleeps.push(ms); }
    });
    return { rest, alerts, earn, sleeps };
}

test('floorUsdt: 2 decimales hacia abajo, nunca negativo', () => {
    assert.equal(floorUsdt(69.4099), '69.40');
    assert.equal(floorUsdt(-3), '0.00');
});

test('apagado por defecto y en testnet; sin producto queda apagado', async () => {
    assert.equal(await make({ enabled: false }).earn.start(), null);
    const t = make({ market: 'testnet' });
    assert.match((await t.earn.start())!, /solo existe en mainnet/);
    assert.equal(t.earn.active, false);
    const n = make();
    n.rest.product = null;
    assert.match((await n.earn.start())!, /queda apagado/);
    assert.equal(n.rest.subs.length, 0);
});

test('al arrancar suscribe lo que pasa de la reserva (2 compras + 2 %)', async () => {
    const { rest, earn } = make();
    assert.match((await earn.start())!, /5\.00 % anual/);
    assert.equal(earn.active, true);
    assert.deepEqual(rest.subs, ['69.40']);            // 100 - 15 * 2 * 1.02 = 69.40
    assert.equal(await earn.sweep(), 0);               // ya no sobra nada
});

test('antes de comprar: con saldo no rescata; sin saldo rescata lo que falta + la reserva y espera a que llegue', async () => {
    const { rest, earn, sleeps } = make();
    await earn.start();                                 // quedan 30.60 libres
    assert.equal(await earn.ensureFunds(15), true);
    assert.equal(rest.redeems.length, 0);
    rest.free = 5;
    rest.arriveAfterPolls = 3;
    assert.equal(await earn.ensureFunds(15), true);
    assert.deepEqual(rest.redeems, ['40.90']);         // 15.30 - 5 + 30.60, con techo a 2 decimales
    assert.ok(sleeps.length >= 2);
});

test('rescate que no llega o que falla: no lanza y avisa si falla', async () => {
    const a = make();
    await a.earn.start();
    a.rest.free = 0;
    a.rest.arriveAfterPolls = 1000;
    assert.equal(await a.earn.ensureFunds(15), false);
    const b = make();
    await b.earn.start();
    b.rest.free = 0;
    b.rest.failRedeem = true;
    assert.equal(await b.earn.ensureFunds(15), false);
    assert.match(b.alerts[0]!, /SIMPLE EARN/);
});
