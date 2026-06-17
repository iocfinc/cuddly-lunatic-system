# WTF: Long Single-Leg Weekly Lane

## What

Turn the weekly screen into a better resale-first options lane instead of a generic options list.

## Why

The user does not currently want hedging or exercise-dependent trades. The useful workflow is identifying contracts that can be bought now and sold later if the thesis or repricing develops.

## The Fix

- keep stock-first directional gating
- prefer contracts that are realistic to exit
- treat event timing as an explicit input, not a hidden assumption
- make packet outputs distinguish cleaner swing candidates from flagged event names
