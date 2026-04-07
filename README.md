# defi-toolkit

Three-part DeFi operations system: flash loan arb scanner, LVR tracker, and unified dashboard.

```
defi-toolkit/
├── contracts/
│   └── FlashLoanArbitrage.sol   # Aave V3 flash loan → multi-DEX arb executor
├── lvr_tracker/
│   └── lvr_tracker.py           # Uniswap V3 LP vs buy-and-hold backtester
├── arb_scanner/
│   ├── arb_scanner.go           # Go daemon: polls DEX prices, finds gaps, WS broadcast
│   └── go.mod
└── dashboard/
    └── index.html               # Unified ops dashboard (open in browser)
```

---

## 1. Flash Loan Arbitrage Contract

**Stack:** Solidity 0.8.20, Aave V3, Uniswap V3, SushiSwap, Curve, Balancer V2

### Deploy (Foundry)
```bash
cd contracts
forge install OpenZeppelin/openzeppelin-contracts

forge create \
  --rpc-url $RPC_URL \
  --constructor-args \
    0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2 \
    0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45 \
    0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F \
    0xBA12222222228d8Ba445958a75a0704d566BF2C8 \
  --private-key $PRIVATE_KEY \
  FlashLoanArbitrage.sol:FlashLoanArbitrage
```

### Approve tokens before first use
```solidity
contract.setTokenApproval(WETH_ADDR, true);
contract.setTokenApproval(USDC_ADDR, true);
```

### Execute an arb (ethers.js)
```js
const params = {
  route: [{
    dex: 0,                          // UNISWAP_V3
    tokenIn: WETH, tokenOut: USDC,
    uniV3Fee: 500,
    uniV3Path: '0x',
    sushiPath: [], curvePool: ZeroAddr, curveI: 0, curveJ: 0,
    balancerPoolId: ZeroBytes32
  }],
  minProfit: ethers.parseUnits('50', 6),  // $50 USDC minimum
  deadline: Math.floor(Date.now()/1000) + 60
};

await contract.executeArbitrage(USDC_ADDR, parseUnits('500000', 6), params);
```

---

## 2. LVR Tracker (Python)

**Stack:** Python 3.11+, numpy, pandas, matplotlib

### Install
```bash
cd lvr_tracker
pip install numpy pandas matplotlib requests python-dotenv tqdm
```

### Run
```bash
# Synthetic GBM data (no API key needed)
python lvr_tracker.py --synthetic --capital 10000 --lower 1600 --upper 2800

# Live Uniswap V3 Subgraph data
python lvr_tracker.py --pool ETH/USDC --start 2024-01-01 --end 2024-06-30

# Your own CSV (columns: date, price, [volumeUSD])
python lvr_tracker.py --csv mydata.csv --lower 55000 --upper 75000 --entry 65000
```

### Output
- Console: full P&L breakdown (fees, IL, LVR, net alpha, APR)
- `lvr_report.png`: 6-panel dark-mode dashboard

### Key formulas implemented
| Metric | Formula |
|--------|---------|
| IL (V3) | `2√(p/p₀)/(1+p/p₀) - 1 × inRangeFraction` |
| LVR | `½ · σ² · γ(p) · V · dt` per tick |
| γ(p) | `1 / (2√p · (√Pb − √Pa))` |
| Fee income | `vol × feeBps × (LP_liq/TVL) × inRangeDays` |

---

## 3. Arb Scanner (Go)

**Stack:** Go 1.21, go-ethereum, gorilla/websocket

### Install & run
```bash
cd arb_scanner
go mod tidy
go run arb_scanner.go --rpc wss://mainnet.infura.io/ws/v3/YOUR_KEY --min-profit 50
```

### CLI flags
| Flag | Default | Description |
|------|---------|-------------|
| `--rpc` | $RPC_URL | Ethereum WebSocket RPC |
| `--min-profit` | 50 | Minimum net profit in USD |
| `--gas-gwei` | 30 | Assumed gas price |
| `--eth-price` | 2400 | ETH price for gas cost calc |
| `--port` | 8765 | WebSocket server port |
| `--exec` | false | Auto-execute profitable opps |

### WebSocket output
Connect to `ws://localhost:8765/ws` to receive real-time JSON:
```json
{ "type": "opportunity", "data": {
    "pair": "WETH/USDC",
    "buyDex": "SushiSwap", "sellDex": "Uniswap V3",
    "gapPct": 0.75,
    "netProfitUSD": 2848.5,
    "profitable": true,
    "routeSteps": [...]
}}
```

### HTTP endpoints
- `GET /stats` — scanner statistics JSON
- `GET /health` — `{"status":"ok"}`
- `WS  /ws` — live opportunity stream

---

## 4. Dashboard

Open `dashboard/index.html` in any browser. In production, connect it to the Go scanner's WebSocket:

```js
// In dashboard/index.html, replace simulated data with:
const ws = new WebSocket('ws://localhost:8765/ws');
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'opportunity') updateOppTable(msg.data);
  if (msg.type === 'stats') updateStats(msg.data);
};
```

---

## Security checklist

- [ ] Audit contract with Slither / Aderyn before mainnet
- [ ] Test on Tenderly fork with realistic amounts
- [ ] Set conservative `minProfit` (≥ 2× typical gas cost)
- [ ] Use private mempool (Flashbots) to avoid front-running
- [ ] Monitor for oracle manipulation (use TWAP, not spot)
- [ ] Keep `PRIVATE_KEY` in `.env`, never commit
