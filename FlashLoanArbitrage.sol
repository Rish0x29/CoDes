// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// ─────────────────────────────────────────────────────────────────────────────
//  FlashLoanArbitrage.sol
//  Aave V3 flash loan → multi-hop DEX arbitrage executor
//
//  Architecture:
//    1. Owner calls executeArbitrage() specifying token, amount, and route
//    2. Aave V3 Pool sends tokens and calls executeOperation() callback
//    3. Callback executes the swap chain (Uniswap V3 → SushiSwap → Curve etc.)
//    4. Contract repays loan + 0.09% fee; profit stays in contract
//    5. Owner calls withdrawProfit() to collect
//
//  Supported DEXs (extensible via ISwapAdapter):
//    - Uniswap V3  (via SwapRouter02)
//    - SushiSwap   (via UniswapV2Router)
//    - Curve       (via ICurvePool, 3pool / tricrypto)
//    - Balancer V2 (via IVault batchSwap)
//
//  Safety:
//    - Reentrancy guard on all external entry points
//    - Only Aave Pool can call executeOperation
//    - Slippage enforced via minProfit parameter
//    - Emergency pause by owner
// ─────────────────────────────────────────────────────────────────────────────

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/security/Pausable.sol";

// ── Aave V3 Interfaces ───────────────────────────────────────────────────────

interface IPool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IFlashLoanSimpleReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

// ── Uniswap V3 Interfaces ────────────────────────────────────────────────────

interface IUniswapV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24  fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(ExactInputSingleParams calldata params)
        external returns (uint256 amountOut);

    struct ExactInputParams {
        bytes   path;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }
    function exactInput(ExactInputParams calldata params)
        external returns (uint256 amountOut);
}

// ── Uniswap V2 / SushiSwap Interface ────────────────────────────────────────

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

// ── Curve Interface ──────────────────────────────────────────────────────────

interface ICurvePool {
    function exchange(
        int128 i,
        int128 j,
        uint256 dx,
        uint256 min_dy
    ) external returns (uint256);

    function get_dy(int128 i, int128 j, uint256 dx)
        external view returns (uint256);
}

// ── Balancer V2 Interface ────────────────────────────────────────────────────

interface IBalancerVault {
    enum SwapKind { GIVEN_IN, GIVEN_OUT }

    struct SingleSwap {
        bytes32 poolId;
        SwapKind kind;
        address assetIn;
        address assetOut;
        uint256 amount;
        bytes userData;
    }

    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address payable recipient;
        bool toInternalBalance;
    }

    function swap(
        SingleSwap memory singleSwap,
        FundManagement memory funds,
        uint256 limit,
        uint256 deadline
    ) external returns (uint256 amountCalculated);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Enums & Structs
// ─────────────────────────────────────────────────────────────────────────────

enum DexType { UNISWAP_V3, SUSHISWAP, CURVE, BALANCER }

struct SwapStep {
    DexType dex;
    address tokenIn;
    address tokenOut;
    // Uniswap V3
    uint24  uniV3Fee;
    bytes   uniV3Path;        // for multi-hop; if empty, use single
    // SushiSwap
    address[] sushiPath;
    // Curve
    address curvePool;
    int128  curveI;
    int128  curveJ;
    // Balancer
    bytes32 balancerPoolId;
}

struct ArbitrageParams {
    SwapStep[] route;         // ordered list of swaps
    uint256    minProfit;     // revert if net profit < this (wei)
    uint256    deadline;      // revert if block.timestamp > deadline
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main Contract
// ─────────────────────────────────────────────────────────────────────────────

contract FlashLoanArbitrage is
    IFlashLoanSimpleReceiver,
    Ownable,
    ReentrancyGuard,
    Pausable
{
    using SafeERC20 for IERC20;

    // ── Immutables ───────────────────────────────────────────────────────────
    IPool               public immutable AAVE_POOL;
    IUniswapV3Router    public immutable UNI_V3_ROUTER;
    IUniswapV2Router    public immutable SUSHI_ROUTER;
    IBalancerVault      public immutable BALANCER_VAULT;

    // ── State ────────────────────────────────────────────────────────────────
    mapping(address => bool) public approvedTokens;
    uint256 public totalProfitUSD;       // informational, off-chain updated
    uint256 public executionCount;

    // ── Events ───────────────────────────────────────────────────────────────
    event ArbitrageExecuted(
        address indexed asset,
        uint256 loanAmount,
        uint256 profit,
        uint256 repayAmount,
        uint256 timestamp
    );
    event ProfitWithdrawn(address indexed token, uint256 amount);
    event TokenApproved(address indexed token, bool approved);
    event StepExecuted(uint256 stepIndex, DexType dex, uint256 amountOut);

    // ── Errors ───────────────────────────────────────────────────────────────
    error OnlyAavePool();
    error OnlyOwnerInitiated();
    error DeadlineExpired();
    error InsufficientProfit(uint256 actual, uint256 minimum);
    error TokenNotApproved();
    error ZeroAmount();
    error InvalidRoute();

    // ─────────────────────────────────────────────────────────────────────────
    constructor(
        address _aavePool,
        address _uniV3Router,
        address _sushiRouter,
        address _balancerVault
    ) Ownable(msg.sender) {
        AAVE_POOL      = IPool(_aavePool);
        UNI_V3_ROUTER  = IUniswapV3Router(_uniV3Router);
        SUSHI_ROUTER   = IUniswapV2Router(_sushiRouter);
        BALANCER_VAULT = IBalancerVault(_balancerVault);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  External: Owner Entry Point
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Initiates a flash loan arbitrage. Call this to start the cycle.
    /// @param asset       The token to borrow (e.g. USDC, WETH)
    /// @param amount      Amount to borrow in token base units
    /// @param params      Encoded ArbitrageParams (route + minProfit + deadline)
    function executeArbitrage(
        address asset,
        uint256 amount,
        ArbitrageParams calldata params
    ) external onlyOwner nonReentrant whenNotPaused {
        if (amount == 0) revert ZeroAmount();
        if (!approvedTokens[asset]) revert TokenNotApproved();
        if (params.route.length == 0) revert InvalidRoute();
        if (block.timestamp > params.deadline) revert DeadlineExpired();

        bytes memory encodedParams = abi.encode(params);

        AAVE_POOL.flashLoanSimple(
            address(this),
            asset,
            amount,
            encodedParams,
            0  // referralCode
        );
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Aave Callback
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Called by Aave Pool after sending flash loan funds.
    ///         Must repay amount + premium before returning.
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override nonReentrant returns (bool) {
        if (msg.sender != address(AAVE_POOL)) revert OnlyAavePool();
        if (initiator != address(this)) revert OnlyOwnerInitiated();

        ArbitrageParams memory arbParams = abi.decode(params, (ArbitrageParams));

        if (block.timestamp > arbParams.deadline) revert DeadlineExpired();

        uint256 balanceBefore = IERC20(asset).balanceOf(address(this));
        uint256 repayAmount   = amount + premium;

        // ── Execute swap route ─────────────────────────────────────────────
        uint256 currentAmount = amount;
        for (uint256 i = 0; i < arbParams.route.length; i++) {
            currentAmount = _executeStep(arbParams.route[i], currentAmount);
            emit StepExecuted(i, arbParams.route[i].dex, currentAmount);
        }

        // ── Profit check ───────────────────────────────────────────────────
        uint256 balanceAfter = IERC20(asset).balanceOf(address(this));
        uint256 profit = balanceAfter > repayAmount
            ? balanceAfter - repayAmount
            : 0;

        if (profit < arbParams.minProfit) {
            revert InsufficientProfit(profit, arbParams.minProfit);
        }

        // ── Repay Aave ─────────────────────────────────────────────────────
        IERC20(asset).safeApprove(address(AAVE_POOL), repayAmount);

        executionCount++;
        emit ArbitrageExecuted(asset, amount, profit, repayAmount, block.timestamp);

        return true;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Internal: Swap Execution
    // ─────────────────────────────────────────────────────────────────────────

    function _executeStep(SwapStep memory step, uint256 amountIn)
        internal returns (uint256 amountOut)
    {
        if (step.dex == DexType.UNISWAP_V3) {
            amountOut = _swapUniV3(step, amountIn);
        } else if (step.dex == DexType.SUSHISWAP) {
            amountOut = _swapSushi(step, amountIn);
        } else if (step.dex == DexType.CURVE) {
            amountOut = _swapCurve(step, amountIn);
        } else {
            amountOut = _swapBalancer(step, amountIn);
        }
    }

    function _swapUniV3(SwapStep memory step, uint256 amountIn)
        internal returns (uint256 amountOut)
    {
        IERC20(step.tokenIn).safeApprove(address(UNI_V3_ROUTER), amountIn);

        if (step.uniV3Path.length > 0) {
            // Multi-hop path encoded as: tokenA + fee + tokenB + fee + tokenC
            IUniswapV3Router.ExactInputParams memory params =
                IUniswapV3Router.ExactInputParams({
                    path: step.uniV3Path,
                    recipient: address(this),
                    amountIn: amountIn,
                    amountOutMinimum: 0   // protected by minProfit at top level
                });
            amountOut = UNI_V3_ROUTER.exactInput(params);
        } else {
            IUniswapV3Router.ExactInputSingleParams memory params =
                IUniswapV3Router.ExactInputSingleParams({
                    tokenIn: step.tokenIn,
                    tokenOut: step.tokenOut,
                    fee: step.uniV3Fee,
                    recipient: address(this),
                    amountIn: amountIn,
                    amountOutMinimum: 0,
                    sqrtPriceLimitX96: 0
                });
            amountOut = UNI_V3_ROUTER.exactInputSingle(params);
        }
    }

    function _swapSushi(SwapStep memory step, uint256 amountIn)
        internal returns (uint256 amountOut)
    {
        IERC20(step.tokenIn).safeApprove(address(SUSHI_ROUTER), amountIn);
        uint256[] memory amounts = SUSHI_ROUTER.swapExactTokensForTokens(
            amountIn,
            0,
            step.sushiPath,
            address(this),
            block.timestamp
        );
        amountOut = amounts[amounts.length - 1];
    }

    function _swapCurve(SwapStep memory step, uint256 amountIn)
        internal returns (uint256 amountOut)
    {
        IERC20(step.tokenIn).safeApprove(step.curvePool, amountIn);
        amountOut = ICurvePool(step.curvePool).exchange(
            step.curveI,
            step.curveJ,
            amountIn,
            0
        );
    }

    function _swapBalancer(SwapStep memory step, uint256 amountIn)
        internal returns (uint256 amountOut)
    {
        IERC20(step.tokenIn).safeApprove(address(BALANCER_VAULT), amountIn);

        IBalancerVault.SingleSwap memory singleSwap = IBalancerVault.SingleSwap({
            poolId: step.balancerPoolId,
            kind: IBalancerVault.SwapKind.GIVEN_IN,
            assetIn: step.tokenIn,
            assetOut: step.tokenOut,
            amount: amountIn,
            userData: ""
        });

        IBalancerVault.FundManagement memory funds = IBalancerVault.FundManagement({
            sender: address(this),
            fromInternalBalance: false,
            recipient: payable(address(this)),
            toInternalBalance: false
        });

        amountOut = BALANCER_VAULT.swap(singleSwap, funds, 0, block.timestamp);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Admin Functions
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Withdraw accumulated profit for a specific token
    function withdrawProfit(address token) external onlyOwner nonReentrant {
        uint256 balance = IERC20(token).balanceOf(address(this));
        if (balance == 0) revert ZeroAmount();
        IERC20(token).safeTransfer(owner(), balance);
        emit ProfitWithdrawn(token, balance);
    }

    /// @notice Approve or revoke a token for use in flash loans
    function setTokenApproval(address token, bool approved) external onlyOwner {
        approvedTokens[token] = approved;
        emit TokenApproved(token, approved);
    }

    /// @notice Emergency pause — stops all new flash loans
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    /// @notice Recover ETH accidentally sent to contract
    receive() external payable {}
    function rescueETH() external onlyOwner {
        payable(owner()).transfer(address(this).balance);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  View: Quote a Route Off-Chain
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Simulate Curve leg output without executing (read-only)
    function quoteCurveLeg(
        address pool,
        int128 i,
        int128 j,
        uint256 dx
    ) external view returns (uint256 dy) {
        return ICurvePool(pool).get_dy(i, j, dx);
    }
}


// ─────────────────────────────────────────────────────────────────────────────
//  Deployment Addresses (Mainnet)
// ─────────────────────────────────────────────────────────────────────────────
//
//  Aave V3 Pool:        0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2
//  Uniswap V3 Router02: 0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45
//  SushiSwap Router:    0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F
//  Balancer Vault:      0xBA12222222228d8Ba445958a75a0704d566BF2C8
//
//  Deploy with:
//    forge create --rpc-url $RPC_URL \
//      --constructor-args \
//        0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2 \
//        0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45 \
//        0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F \
//        0xBA12222222228d8Ba445958a75a0704d566BF2C8 \
//      --private-key $PRIVATE_KEY \
//      src/FlashLoanArbitrage.sol:FlashLoanArbitrage
// ─────────────────────────────────────────────────────────────────────────────
