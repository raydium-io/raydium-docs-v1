# Raydium AMM v4 — OpenBook / Serum Removal / Upgrade Notes

---

# 1. Background

AMM v4 **stopped sharing liquidity to the OpenBook / Serum order book a long time ago**; the hybrid order-book market-making path has been dormant for years. This upgrade is the cleanup: it **removes the Serum/OpenBook dependency, all related CPIs, and the dead instructions** from the program, leaving AMM v4 as a pure constant-product (`x·y=k`) AMM.

This upgrade **does not change any live trading behavior** — there were no OpenBook orders left to stop placing.

# 2. TL;DR for integrators

- **Swap / Deposit / Withdraw keep working with no changes.** Transactions built with the old account layouts still execute — the removed Serum/market accounts are simply ignored (no validation, no CPI). You do **not** need to ship a client update to keep existing flows alive.
- **Migrate to the V2 swap instructions soon.** `SwapBaseInV2` / `SwapBaseOutV2` carry no market accounts, so transactions are smaller and cheaper. Routers/aggregators should switch to the V2 path.
- **`WithdrawPnl` is a hard breaking change (admin only).** Accounts drop from 17 (+1 optional) to 10 with **no compatibility parsing**. In the old layout account #5 was `amm_open_orders`; in the new layout that slot is `pool_coin_token_account`, so the old layout misaligns and fails validation. Admin tooling that calls `WithdrawPnl` must be updated.
- **`SetParams` is a hard breaking change (admin only).** Accounts shrink to `[amm, admin]`, the `param` enum is **renumbered** (see below), and the `AmmOwner`, `LastOrderDistance`, `UpdateOpenOrder` params are removed.
- **Several instructions are no longer callable.** `Initialize` (tag 0), `PreInitialize` (10), `MonitorStep` (2), `MigrateToOpenBook` (5), `WithdrawSrm` (8), `SimulateInfo` (12), and `AdminCancelOrders` (13) now revert (`unimplemented!` panic). Use `Initialize2` to create pools.
- **On-chain account data layout (`AmmInfo` / `StateData`) stays byte-compatible.** Old OpenBook fields are retained but marked deprecated/no-longer-updated; deserialization code needs no changes.
- **Error codes are stable.** The existing `AmmError` variant order/numbering is unchanged; only a new `NotAllowed` (#60) is appended.

# 3. Per-instruction changes

## 3.1 Still callable, layout unchanged (fully backward compatible)

| Instruction | tag | Account change | Notes |
|---|---|---|---|
| `Initialize2` | 1 | Unchanged (still takes `market_program`/`market`, read-only, no interaction) | Only pool-creation entrypoint. No initial order grid is posted. |
| `Deposit` | 3 | Unchanged (`amm_open_orders`, `market` still passed, ignored) | Deposit logic unchanged. |
| `Withdraw` | 4 | Unchanged (all market accounts still passed, ignored) | No more OpenBook settle step. |
| `SwapBaseIn` | 9 | Unchanged (17 or 18 accounts); market accounts read but ignored, no CPI, no validation | Reserves now computed vault-only (`calc_total_without_take_pnl_no_orderbook`). |
| `SwapBaseOut` | 11 | Same as above | Same. |
| `CreateConfigAccount` | 14 | Unchanged | Program-level config (admin). |
| `UpdateConfigAccount` | 15 | Unchanged | Admin. |

> On v1 swaps: the program still requires 17 or 18 accounts (otherwise `WrongAccountsNumber`). The market accounts may keep occupying their old positions as placeholders; their contents are no longer validated — but the **account count must still match**. This is a temporary compatibility shim.

## 3.2 Recommended V2 swaps (fewer accounts)

`SwapBaseInV2` (tag 16, exact-in) and `SwapBaseOutV2` (tag 17, exact-out) omit the market accounts **and `amm_open_orders`** — 8 accounts only (`token_program`, `amm`, `amm_authority`, the two pool vaults, the two user token accounts, `user_owner`). Quote math is identical to v1 (reserves are now vault balance minus pending PnL). **Use V2 for all new integrations.**

## 3.3 Breaking changes (admin only)

**`WithdrawPnl` (tag 7)** — accounts `17(+1) → 10`, no compatibility parsing:

| # | New-layout account |
|---|---|
| 1 | `token_program` |
| 2 | `amm` (W) |
| 3 | `amm_config` |
| 4 | `amm_authority` |
| 5 | `pool_coin_token_account` (W) |
| 6 | `pool_pc_token_account` (W) |
| 7 | `user_pnl_coin` (W) |
| 8 | `user_pnl_pc` (W) |
| 9 | `pnl_owner` (S) |
| 10 | `amm_target_orders` (W) |

`amm_open_orders` and all six market accounts are removed. Sending the old layout fails with misalignment errors (e.g. `InvalidCoinVault`).

**`SetParams` (tag 6)** — accounts shrink to `[amm (W), admin (S)]`; `param` enum renumbered:

| Param | Old value (master) | New value (branch) |
|---|---|---|
| `Status` | 0 | 0 |
| `State` | 1 | 1 |
| `Fees` | 9 | **2** |
| `SetOpenTime` | 11 | **3** |

Removed params: `OrderNum`, `Depth`, `AmountWave`, `MinPriceMultiplier`, `MaxPriceMultiplier`, `MinSize`, `VolMaxCutRatio`, `AmmOwner`, `LastOrderDistance`, `InitOrderDepth`, `SetSwitchTime`, `ClearOpenTime`, `Seperate`, `UpdateOpenOrder`. The `SetParamsInstruction` struct also drops `new_pubkey` and `last_order_distance`.

## 3.4 Removed / no-longer-callable instructions

These now `unimplemented!` panic at runtime, and their client builders were removed from `instruction.rs`:

| Instruction | tag | Replacement |
|---|---|---|
| `Initialize` | 0 | Use `Initialize2` |
| `MonitorStep` | 2 | None (order-book crank, retired) |
| `MigrateToOpenBook` | 5 | None |
| `WithdrawSrm` | 8 | None (SRM fee discount, retired) |
| `PreInitialize` | 10 | Use `Initialize2` |
| `SimulateInfo` | 12 | Use off-chain / SDK quoting |
| `AdminCancelOrders` | 13 | None |

# 4. Other changes

- **Dependency removed**: `program/Cargo.toml` drops `serum_dex`; the `no-entrypoint` / `program` / `client` features no longer pull in Serum.
- **CPIs removed**: `invokers.rs` deletes every Serum DEX CPI (`invoke_dex_new_order_v3`, `invoke_dex_cancel_order_v2`, `invoke_dex_settle_funds`, `invoke_dex_init_open_orders`, etc.); only SPL Token invokers remain.
- **Reserve calculation**: total pool assets for swap/withdraw are now `vault balances − pending PnL`; the always-zero OpenBook open-order term is dropped. **Quoting code can now use vault balances directly** (previously it had to add the open-order term).
- **State fields deprecated**: in `StateData`, the fields `total_pnl_pc`, `total_pnl_coin`, `orderbook_to_init_time`, `swap_coin_in_amount`, `swap_pc_out_amount`, `swap_acc_pc_fee`, `swap_pc_in_amount`, `swap_coin_out_amount`, `swap_acc_coin_fee` are marked deprecated and **no longer updated** (historical values on existing pools are frozen). Anyone reading these for volume stats should switch to trade logs / off-chain data.
- **`AmmInfo` init**: `coin_lot_size`, `pc_lot_size`, `min_size` are now initialized to 0.
- **Removed structs**: `LastOrderDistance`, `SimulateParams`, `RunCrankData`, `GetPoolData`, `GetSwapBaseInData`, `GetSwapBaseOutData`.
- **Entrypoint logging**: `entrypoint.rs` prints AMM errors manually via `msg!` + `FromPrimitive` and adds program-id / account-count logs.

# 5. Migration checklist

- [ ] Trading integrations: confirm existing v1 swaps still work; schedule migration to `SwapBaseInV2` / `SwapBaseOutV2`.
- [ ] Quoting / market making: switch reserve calc to vault-only (drop the open-order term if you added it).
- [ ] Volume stats: if you read `StateData.swap_*`, move to trade logs.
- [ ] Admin tooling: you **must** update the account lists and `param` values for `WithdrawPnl` and `SetParams`.
- [ ] Pool creation: ensure you use `Initialize2` (not `Initialize` / `PreInitialize`).
- [ ] Remove any calls to `MonitorStep` / `MigrateToOpenBook` / `WithdrawSrm` / `SimulateInfo` / `AdminCancelOrders`.

