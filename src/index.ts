import { BinanceRestClient } from './api/rest-client';

async function main() {
    const client = new BinanceRestClient();
    console.log("Conectando a Binance Spot Testnet...");
    
    try {
        const accountData = await client.getAccountBalance();
        console.log("¡Conexión exitosa! Estos son tus activos asignados en la Testnet:");
        
        // Filtramos para mostrar solo las monedas donde Binance te asignó saldo ficticio
        const activeBalances = accountData.balances.filter(
            (asset: any) => parseFloat(asset.free) > 0 || parseFloat(asset.locked) > 0
        );
        
        console.table(activeBalances);
    } catch (error) {
        console.error("Fallo en la ejecución principal.");
    }
}

main();