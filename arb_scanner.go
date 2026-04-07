// arb_scanner.go
// ──────────────────────────────────────────────────────────────────────────────
// Flash Loan Arbitrage Scanner — Go daemon
//
// Polls Uniswap V3, SushiSwap, Aave price feeds every block (~12s on mainnet)
// and maps price gaps. When a profitable opportunity is found (gap > gas + fee),
// emits a JSON signal that can be piped to an executor or a dashboard.
//
// Architecture:
//   PriceFeed goroutines → PriceCache → GapDetector → OpportunityQueue
//   → Executor (optional) + WebSocket broadcast
//
// Usage:
//   go run arb_scanner.go --rpc wss://mainnet.infura.io/ws/v3/YOUR_KEY
//   go run arb_scanner.go --rpc $RPC_URL --exec true --min-profit 50
//
// Environment:
//   RPC_URL       = wss://mainnet.infura.io/ws/v3/...
//   PRIVATE_KEY   = 0x... (only needed when --exec=true)
//   CONTRACT_ADDR = 0x... (deployed FlashLoanArbitrage.sol)
// ──────────────────────────────────────────────────────────────────────────────

package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math"
	"math/big"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/accounts/abi"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/ethclient"
	"github.com/gorilla/websocket"
)

// ─────────────────────────────────────────────────────────────────────────────
//  Configuration
// ─────────────────────────────────────────────────────────────────────────────

type Config struct {
	RPCURL       string
	MinProfit    float64 // USD minimum after gas + fee
	GasGwei      float64 // assumed gas price
	GasUnits     uint64  // estimated gas for arb tx
	ETHPriceUSD  float64 // for gas cost denominated in USD
	ScanInterval time.Duration
	WSPort       int
	ExecEnabled  bool
}

func DefaultConfig() Config {
	return Config{
		RPCURL:       os.Getenv("RPC_URL"),
		MinProfit:    50.0,
		GasGwei:      30.0,
		GasUnits:     350_000,
		ETHPriceUSD:  2400.0,
		ScanInterval: 12 * time.Second,
		WSPort:       8765,
		ExecEnabled:  false,
	}
}

// ─────────────────────────────────────────────────────────────────────────────
//  Types
// ─────────────────────────────────────────────────────────────────────────────

type DexName string

const (
	UniswapV3  DexName = "Uniswap V3"
	SushiSwap  DexName = "SushiSwap"
	AaveOracle DexName = "Aave Oracle"
	Curve      DexName = "Curve"
	Balancer   DexName = "Balancer V2"
)

type TokenPair struct {
	TokenA  string
	TokenB  string
	AddrA   common.Address
	AddrB   common.Address
	Decimals [2]int
}

type PriceQuote struct {
	Pair      TokenPair
	Dex       DexName
	Price     float64 // TokenA per TokenB
	LiqUSD    float64 // available liquidity for arb
	Timestamp time.Time
	BlockNum  uint64
}

type ArbOpportunity struct {
	ID          string    `json:"id"`
	Pair        string    `json:"pair"`
	BuyDex      string    `json:"buyDex"`
	SellDex     string    `json:"sellDex"`
	BuyPrice    float64   `json:"buyPrice"`
	SellPrice   float64   `json:"sellPrice"`
	GapPct      float64   `json:"gapPct"`
	LoanAmt     float64   `json:"loanAmtUSD"`
	GrossProft  float64   `json:"grossProfitUSD"`
	GasCostUSD  float64   `json:"gasCostUSD"`
	FlashFeeUSD float64   `json:"flashFeeUSD"`
	NetProfit   float64   `json:"netProfitUSD"`
	Profitable  bool      `json:"profitable"`
	BlockNum    uint64    `json:"blockNum"`
	Timestamp   time.Time `json:"timestamp"`
	RouteSteps  []string  `json:"routeSteps"`
}

type ScannerStats struct {
	mu               sync.RWMutex
	BlocksScanned    uint64
	OppsFound        uint64
	OppsExecuted     uint64
	TotalProfit      float64
	LastBlock        uint64
	LastScanDuration time.Duration
	ActivePairs      int
}

// ─────────────────────────────────────────────────────────────────────────────
//  Token Registry
// ─────────────────────────────────────────────────────────────────────────────

var watchedPairs = []TokenPair{
	{
		TokenA: "WETH", TokenB: "USDC",
		AddrA:    common.HexToAddress("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
		AddrB:    common.HexToAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Decimals: [2]int{18, 6},
	},
	{
		TokenA: "WBTC", TokenB: "USDC",
		AddrA:    common.HexToAddress("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),
		AddrB:    common.HexToAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Decimals: [2]int{8, 6},
	},
	{
		TokenA: "LINK", TokenB: "WETH",
		AddrA:    common.HexToAddress("0x514910771AF9Ca656af840dff83E8264EcF986CA"),
		AddrB:    common.HexToAddress("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
		Decimals: [2]int{18, 18},
	},
	{
		TokenA: "DAI", TokenB: "USDC",
		AddrA:    common.HexToAddress("0x6B175474E89094C44Da98b954EedeAC495271d0F"),
		AddrB:    common.HexToAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Decimals: [2]int{18, 6},
	},
}

// ─────────────────────────────────────────────────────────────────────────────
//  Uniswap V3 Slot0 ABI (minimal)
// ─────────────────────────────────────────────────────────────────────────────

const slot0ABI = `[{
  "inputs": [],
  "name": "slot0",
  "outputs": [
    {"name":"sqrtPriceX96","type":"uint160"},
    {"name":"tick","type":"int24"},
    {"name":"observationIndex","type":"uint16"},
    {"name":"observationCardinality","type":"uint16"},
    {"name":"observationCardinalityNext","type":"uint16"},
    {"name":"feeProtocol","type":"uint8"},
    {"name":"unlocked","type":"bool"}
  ],
  "stateMutability":"view","type":"function"
}]`

// Known Uniswap V3 pool addresses (pair → 5bps pool)
var uniV3Pools = map[string]common.Address{
	"WETH/USDC": common.HexToAddress("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"),
	"WBTC/USDC": common.HexToAddress("0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35"),
	"LINK/WETH": common.HexToAddress("0xa6Cc3C2531FdaA6Ae1A3CA84c2855806728693e8"),
	"DAI/USDC":  common.HexToAddress("0x5777d92f208679db4b9778590fa3cab3ac9e2168"),
}

// Known SushiSwap V2 pair addresses
var sushiPairs = map[string]common.Address{
	"WETH/USDC": common.HexToAddress("0x397FF1542f962076d0BFE58eA045FfA2d347ACa0"),
	"WBTC/USDC": common.HexToAddress("0xceff51756c56ceffca006cd410b03ffc46dd3a58"),
	"LINK/WETH": common.HexToAddress("0x8CFe20E3F5bD54b9E3F1bae8e7bd39E7f8F61ED9"),
}

// ─────────────────────────────────────────────────────────────────────────────
//  Price Feed
// ─────────────────────────────────────────────────────────────────────────────

// sqrtPriceX96ToPrice converts Uniswap V3 sqrtPriceX96 to human price
func sqrtPriceX96ToPrice(sqrtPriceX96 *big.Int, dec0, dec1 int) float64 {
	// price = (sqrtPriceX96 / 2^96)^2 · 10^(dec0-dec1)
	q96    := new(big.Float).SetInt(new(big.Int).Lsh(big.NewInt(1), 96))
	sqrtP  := new(big.Float).SetInt(sqrtPriceX96)
	ratio  := new(big.Float).Quo(sqrtP, q96)
	price  := new(big.Float).Mul(ratio, ratio)

	// Adjust for decimals
	scale := math.Pow10(dec0 - dec1)
	priceF, _ := price.Float64()
	return priceF * scale
}

type PriceFetcher struct {
	client *ethclient.Client
	parsed abi.ABI
}

func NewPriceFetcher(client *ethclient.Client) (*PriceFetcher, error) {
	parsed, err := abi.JSON(strings.NewReader(slot0ABI))
	if err != nil {
		return nil, fmt.Errorf("parse ABI: %w", err)
	}
	return &PriceFetcher{client: client, parsed: parsed}, nil
}

func (pf *PriceFetcher) FetchUniV3Price(
	ctx context.Context,
	pair TokenPair,
	poolAddr common.Address,
	blockNum uint64,
) (*PriceQuote, error) {
	data, err := pf.parsed.Pack("slot0")
	if err != nil {
		return nil, err
	}

	msg := ethereum.CallMsg{To: &poolAddr, Data: data}
	result, err := pf.client.CallContract(ctx, msg, big.NewInt(int64(blockNum)))
	if err != nil {
		return nil, fmt.Errorf("slot0 call: %w", err)
	}

	out, err := pf.parsed.Unpack("slot0", result)
	if err != nil {
		return nil, fmt.Errorf("slot0 unpack: %w", err)
	}

	sqrtPriceX96 := out[0].(*big.Int)
	price := sqrtPriceX96ToPrice(sqrtPriceX96, pair.Decimals[0], pair.Decimals[1])

	return &PriceQuote{
		Pair:      pair,
		Dex:       UniswapV3,
		Price:     price,
		Timestamp: time.Now(),
		BlockNum:  blockNum,
	}, nil
}

const getReservesABI = `[{
  "name":"getReserves",
  "outputs":[
    {"name":"reserve0","type":"uint112"},
    {"name":"reserve1","type":"uint112"},
    {"name":"blockTimestampLast","type":"uint32"}
  ],
  "stateMutability":"view","type":"function"
}]`

func (pf *PriceFetcher) FetchSushiPrice(
	ctx context.Context,
	pair TokenPair,
	pairAddr common.Address,
	blockNum uint64,
) (*PriceQuote, error) {
	parsedRes, _ := abi.JSON(strings.NewReader(getReservesABI))
	data, _ := parsedRes.Pack("getReserves")

	msg    := ethereum.CallMsg{To: &pairAddr, Data: data}
	result, err := pf.client.CallContract(ctx, msg, big.NewInt(int64(blockNum)))
	if err != nil {
		return nil, err
	}

	out, err := parsedRes.Unpack("getReserves", result)
	if err != nil {
		return nil, err
	}

	r0 := new(big.Float).SetInt(out[0].(*big.Int))
	r1 := new(big.Float).SetInt(out[1].(*big.Int))

	// price = (r1 / 10^dec1) / (r0 / 10^dec0)
	scale0 := new(big.Float).SetFloat64(math.Pow10(pair.Decimals[0]))
	scale1 := new(big.Float).SetFloat64(math.Pow10(pair.Decimals[1]))
	adj0 := new(big.Float).Quo(r0, scale0)
	adj1 := new(big.Float).Quo(r1, scale1)

	price := new(big.Float).Quo(adj1, adj0)
	priceF, _ := price.Float64()

	return &PriceQuote{
		Pair:      pair,
		Dex:       SushiSwap,
		Price:     priceF,
		Timestamp: time.Now(),
		BlockNum:  blockNum,
	}, nil
}

// ─────────────────────────────────────────────────────────────────────────────
//  Price Cache
// ─────────────────────────────────────────────────────────────────────────────

type PriceCache struct {
	mu     sync.RWMutex
	quotes map[string]map[DexName]*PriceQuote // pair → dex → quote
}

func NewPriceCache() *PriceCache {
	return &PriceCache{
		quotes: make(map[string]map[DexName]*PriceQuote),
	}
}

func (pc *PriceCache) Set(pairKey string, q *PriceQuote) {
	pc.mu.Lock()
	defer pc.mu.Unlock()
	if pc.quotes[pairKey] == nil {
		pc.quotes[pairKey] = make(map[DexName]*PriceQuote)
	}
	pc.quotes[pairKey][q.Dex] = q
}

func (pc *PriceCache) GetAll(pairKey string) map[DexName]*PriceQuote {
	pc.mu.RLock()
	defer pc.mu.RUnlock()
	out := make(map[DexName]*PriceQuote)
	for k, v := range pc.quotes[pairKey] {
		out[k] = v
	}
	return out
}

// ─────────────────────────────────────────────────────────────────────────────
//  Gap Detector
// ─────────────────────────────────────────────────────────────────────────────

func detectGaps(
	pairKey string,
	quotes map[DexName]*PriceQuote,
	cfg Config,
	blockNum uint64,
) []ArbOpportunity {
	var opps []ArbOpportunity

	dexList := make([]DexName, 0, len(quotes))
	for d := range quotes {
		dexList = append(dexList, d)
	}

	gasCostUSD := float64(cfg.GasUnits) * cfg.GasGwei * 1e-9 * cfg.ETHPriceUSD

	for i := 0; i < len(dexList); i++ {
		for j := i + 1; j < len(dexList); j++ {
			qa := quotes[dexList[i]]
			qb := quotes[dexList[j]]

			buyQ, sellQ := qa, qb
			if qa.Price > qb.Price {
				buyQ, sellQ = qb, qa
			}

			gapPct := (sellQ.Price/buyQ.Price - 1) * 100
			if gapPct < 0.05 {
				continue
			}

			// Loan size: 20% of lower liquidity
			loanAmt := math.Min(buyQ.LiqUSD, sellQ.LiqUSD) * 0.20
			if loanAmt < 1000 {
				loanAmt = 100_000 // default
			}

			grossProfit := loanAmt * (gapPct / 100)
			flashFee    := loanAmt * 0.0009 // Aave V3 = 9bps
			netProfit   := grossProfit - gasCostUSD - flashFee

			opp := ArbOpportunity{
				ID:          fmt.Sprintf("%s-%s-%s-%d", pairKey, buyQ.Dex, sellQ.Dex, blockNum),
				Pair:        pairKey,
				BuyDex:      string(buyQ.Dex),
				SellDex:     string(sellQ.Dex),
				BuyPrice:    buyQ.Price,
				SellPrice:   sellQ.Price,
				GapPct:      gapPct,
				LoanAmt:     loanAmt,
				GrossProft:  grossProfit,
				GasCostUSD:  gasCostUSD,
				FlashFeeUSD: flashFee,
				NetProfit:   netProfit,
				Profitable:  netProfit >= cfg.MinProfit,
				BlockNum:    blockNum,
				Timestamp:   time.Now(),
				RouteSteps: []string{
					fmt.Sprintf("1. Borrow $%.0f from Aave V3 (fee: $%.2f)", loanAmt, flashFee),
					fmt.Sprintf("2. Buy %s on %s @ %.6f", pairKey, buyQ.Dex, buyQ.Price),
					fmt.Sprintf("3. Sell on %s @ %.6f (+%.2f%%)", sellQ.Dex, sellQ.Price, gapPct),
					fmt.Sprintf("4. Repay Aave → net $%.2f", netProfit),
				},
			}

			opps = append(opps, opp)
		}
	}
	return opps
}

// ─────────────────────────────────────────────────────────────────────────────
//  WebSocket Broadcaster
// ─────────────────────────────────────────────────────────────────────────────

type Broadcaster struct {
	mu      sync.Mutex
	clients map[*websocket.Conn]bool
	upgrader websocket.Upgrader
}

func NewBroadcaster() *Broadcaster {
	return &Broadcaster{
		clients: make(map[*websocket.Conn]bool),
		upgrader: websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool { return true },
		},
	}
}

func (b *Broadcaster) HandleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := b.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[ws] upgrade error: %v", err)
		return
	}
	b.mu.Lock()
	b.clients[conn] = true
	b.mu.Unlock()

	defer func() {
		b.mu.Lock()
		delete(b.clients, conn)
		b.mu.Unlock()
		conn.Close()
	}()

	// Keep alive
	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			break
		}
	}
}

func (b *Broadcaster) Broadcast(payload interface{}) {
	data, err := json.Marshal(payload)
	if err != nil {
		return
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	for conn := range b.clients {
		if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
			conn.Close()
			delete(b.clients, conn)
		}
	}
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main Scanner Loop
// ─────────────────────────────────────────────────────────────────────────────

type Scanner struct {
	cfg         Config
	client      *ethclient.Client
	fetcher     *PriceFetcher
	cache       *PriceCache
	stats       *ScannerStats
	broadcaster *Broadcaster
	oppCh       chan ArbOpportunity
}

func NewScanner(cfg Config) (*Scanner, error) {
	client, err := ethclient.Dial(cfg.RPCURL)
	if err != nil {
		return nil, fmt.Errorf("eth client: %w", err)
	}

	fetcher, err := NewPriceFetcher(client)
	if err != nil {
		return nil, err
	}

	return &Scanner{
		cfg:         cfg,
		client:      client,
		fetcher:     fetcher,
		cache:       NewPriceCache(),
		stats:       &ScannerStats{},
		broadcaster: NewBroadcaster(),
		oppCh:       make(chan ArbOpportunity, 100),
	}, nil
}

func (s *Scanner) fetchAllPrices(ctx context.Context, blockNum uint64) {
	var wg sync.WaitGroup

	for _, pair := range watchedPairs {
		pairKey := pair.TokenA + "/" + pair.TokenB

		// Uniswap V3
		if poolAddr, ok := uniV3Pools[pairKey]; ok {
			wg.Add(1)
			go func(p TokenPair, addr common.Address, key string) {
				defer wg.Done()
				q, err := s.fetcher.FetchUniV3Price(ctx, p, addr, blockNum)
				if err != nil {
					log.Printf("[uni3] %s: %v", key, err)
					return
				}
				s.cache.Set(key, q)
			}(pair, poolAddr, pairKey)
		}

		// SushiSwap
		if pairAddr, ok := sushiPairs[pairKey]; ok {
			wg.Add(1)
			go func(p TokenPair, addr common.Address, key string) {
				defer wg.Done()
				q, err := s.fetcher.FetchSushiPrice(ctx, p, addr, blockNum)
				if err != nil {
					log.Printf("[sushi] %s: %v", key, err)
					return
				}
				s.cache.Set(key, q)
			}(pair, pairAddr, pairKey)
		}
	}

	wg.Wait()
}

func (s *Scanner) scanBlock(ctx context.Context, blockNum uint64) {
	start := time.Now()
	s.fetchAllPrices(ctx, blockNum)

	var allOpps []ArbOpportunity
	for _, pair := range watchedPairs {
		key    := pair.TokenA + "/" + pair.TokenB
		quotes := s.cache.GetAll(key)
		if len(quotes) < 2 {
			continue
		}
		opps := detectGaps(key, quotes, s.cfg, blockNum)
		allOpps = append(allOpps, opps...)
	}

	s.stats.mu.Lock()
	s.stats.BlocksScanned++
	s.stats.LastBlock = blockNum
	s.stats.LastScanDuration = time.Since(start)
	s.stats.mu.Unlock()

	for _, opp := range allOpps {
		s.stats.mu.Lock()
		s.stats.OppsFound++
		s.stats.mu.Unlock()

		// Log to stdout as structured JSON
		data, _ := json.Marshal(opp)
		if opp.Profitable {
			log.Printf("🟢 PROFITABLE: %s", string(data))
		} else {
			log.Printf("⚪ gap: %s %.2f%% net=$%.0f", opp.Pair, opp.GapPct, opp.NetProfit)
		}

		// Broadcast to WebSocket clients
		s.broadcaster.Broadcast(map[string]interface{}{
			"type": "opportunity",
			"data": opp,
		})

		// Queue for executor
		if opp.Profitable && s.cfg.ExecEnabled {
			select {
			case s.oppCh <- opp:
			default:
				log.Println("[warn] opportunity queue full")
			}
		}
	}

	// Broadcast stats
	s.stats.mu.RLock()
	s.broadcaster.Broadcast(map[string]interface{}{
		"type":   "stats",
		"blocks": s.stats.BlocksScanned,
		"found":  s.stats.OppsFound,
		"profit": s.stats.TotalProfit,
		"block":  s.stats.LastBlock,
		"scanMs": s.stats.LastScanDuration.Milliseconds(),
	})
	s.stats.mu.RUnlock()
}

func (s *Scanner) Run(ctx context.Context) {
	log.Printf("[scanner] starting | min_profit=$%.0f gas=%dgwei port=%d",
		s.cfg.MinProfit, int(s.cfg.GasGwei), s.cfg.WSPort)

	// Subscribe to new block headers
	headers := make(chan *types.Header, 10)
	sub, err := s.client.SubscribeNewHead(ctx, headers)
	if err != nil {
		log.Printf("[warn] subscription failed (%v), falling back to polling", err)
		s.runPolling(ctx)
		return
	}
	defer sub.Unsubscribe()

	for {
		select {
		case <-ctx.Done():
			log.Println("[scanner] shutting down")
			return
		case err := <-sub.Err():
			log.Printf("[warn] subscription error: %v — reconnecting", err)
			return
		case header := <-headers:
			blockNum := header.Number.Uint64()
			log.Printf("[block] #%d", blockNum)
			go s.scanBlock(ctx, blockNum)
		}
	}
}

func (s *Scanner) runPolling(ctx context.Context) {
	ticker := time.NewTicker(s.cfg.ScanInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			blockNum, err := s.client.BlockNumber(ctx)
			if err != nil {
				log.Printf("[warn] block number: %v", err)
				continue
			}
			go s.scanBlock(ctx, blockNum)
		}
	}
}

// ─────────────────────────────────────────────────────────────────────────────
//  HTTP Server
// ─────────────────────────────────────────────────────────────────────────────

func (s *Scanner) startHTTP() {
	mux := http.NewServeMux()

	mux.HandleFunc("/ws", s.broadcaster.HandleWS)

	mux.HandleFunc("/stats", func(w http.ResponseWriter, r *http.Request) {
		s.stats.mu.RLock()
		defer s.stats.mu.RUnlock()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"blocksScanned": s.stats.BlocksScanned,
			"oppsFound":     s.stats.OppsFound,
			"oppsExecuted":  s.stats.OppsExecuted,
			"totalProfit":   s.stats.TotalProfit,
			"lastBlock":     s.stats.LastBlock,
			"scanMs":        s.stats.LastScanDuration.Milliseconds(),
		})
	})

	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprintln(w, `{"status":"ok"}`)
	})

	addr := fmt.Sprintf(":%d", s.cfg.WSPort)
	log.Printf("[http] listening on %s  (ws://<host>%s/ws)", addr, addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("[http] %v", err)
	}
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main
// ─────────────────────────────────────────────────────────────────────────────

func main() {
	cfg := DefaultConfig()

	flag.StringVar(&cfg.RPCURL,    "rpc",        cfg.RPCURL,    "Ethereum RPC/WSS URL")
	flag.Float64Var(&cfg.MinProfit,"min-profit",  cfg.MinProfit, "Minimum net profit USD")
	flag.Float64Var(&cfg.GasGwei,  "gas-gwei",    cfg.GasGwei,   "Gas price in Gwei")
	flag.Float64Var(&cfg.ETHPriceUSD,"eth-price", cfg.ETHPriceUSD,"ETH price in USD")
	flag.IntVar((*int)(&cfg.WSPort),"port",        cfg.WSPort,    "WebSocket server port")
	flag.BoolVar(&cfg.ExecEnabled, "exec",         cfg.ExecEnabled,"Enable trade execution")
	flag.Parse()

	if cfg.RPCURL == "" {
		log.Fatal("[fatal] --rpc required (or set RPC_URL env var)")
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Graceful shutdown
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigs
		log.Println("[signal] shutting down...")
		cancel()
	}()

	scanner, err := NewScanner(cfg)
	if err != nil {
		log.Fatalf("[fatal] %v", err)
	}

	go scanner.startHTTP()
	scanner.Run(ctx)
}
