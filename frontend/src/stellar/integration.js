// Stellar Soroban Testnet — Analysis Hash Logger
// Logs the SHA-256 hash of the pipeline result on-chain and returns the tx hash

import * as StellarSdk from '@stellar/stellar-sdk';

const HORIZON_URL = 'https://horizon-testnet.stellar.org';
const NETWORK_PASSPHRASE = StellarSdk.Networks.TESTNET;

// Generate or retrieve a keypair for the demo
// In production this should be stored securely — for hackathon we derive from a fixed seed
const DEMO_SECRET = 'SCZANGBA5AKIA5ZA4JBZE6TGQBZXS7FBKTU4WUOVHXZM7NVXB44DLLV';

async function getSHA256(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Logs the analysis hash on Stellar testnet via a memo field on a self-payment tx.
 * @param {object} pipelineResult - Full API response from /api/pipeline
 * @returns {{ txHash: string, explorerUrl: string, analysisHash: string }}
 */
export async function logAnalysisOnChain(pipelineResult) {
  try {
    // 1. Create a deterministic hash of the analysis result
    const resultString = JSON.stringify({
      walls: pipelineResult?.geometry?.stats,
      materials: pipelineResult?.materials?.cost_summary,
      timestamp: new Date().toISOString().split('T')[0], // date-level granularity
    });
    const analysisHash = await getSHA256(resultString);
    const memoText = analysisHash.substring(0, 28); // Stellar memo max 28 bytes

    // 2. Load keypair & account
    const keypair = StellarSdk.Keypair.fromSecret(DEMO_SECRET);
    const server = new StellarSdk.Horizon.Server(HORIZON_URL);
    const account = await server.loadAccount(keypair.publicKey());

    // 3. Build transaction — self-payment of 1 XLM, hash in memo
    const transaction = new StellarSdk.TransactionBuilder(account, {
      fee: StellarSdk.BASE_FEE,
      networkPassphrase: NETWORK_PASSPHRASE,
    })
      .addOperation(
        StellarSdk.Operation.payment({
          destination: keypair.publicKey(),
          asset: StellarSdk.Asset.native(),
          amount: '0.0000001',
        })
      )
      .addMemo(StellarSdk.Memo.text(memoText))
      .setTimeout(30)
      .build();

    // 4. Sign & submit
    transaction.sign(keypair);
    const result = await server.submitTransaction(transaction);

    const txHash = result.hash;
    const explorerUrl = `https://stellar.expert/explorer/testnet/tx/${txHash}`;

    return { txHash, explorerUrl, analysisHash };
  } catch (err) {
    console.error('Stellar logging error:', err);
    // Return a fallback so UI doesn't break
    const fallbackHash = await getSHA256(JSON.stringify(pipelineResult)).catch(() => 'error');
    return {
      txHash: null,
      explorerUrl: null,
      analysisHash: fallbackHash,
      error: err.message,
    };
  }
}

/**
 * Fund the demo account from Stellar Friendbot (testnet only)
 * Call once if account doesn't exist yet
 */
export async function fundTestnetAccount() {
  const keypair = StellarSdk.Keypair.fromSecret(DEMO_SECRET);
  const res = await fetch(
    `https://friendbot.stellar.org?addr=${keypair.publicKey()}`
  );
  return res.json();
}

export function getDemoPublicKey() {
  return StellarSdk.Keypair.fromSecret(DEMO_SECRET).publicKey();
}
