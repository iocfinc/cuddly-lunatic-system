# Quant Researcher Desk — Product Requirements Document (PRD)

## 1. Overview

**Product Name:** Quant Researcher Desk
**Type:** Personal Quantitative Research System
**Primary Mode:** Daily Batch Analysis + Report Generation
**User:** Individual retail investor (learning-focused, non-automated trading)

---

## 2. Objective

To build a structured, repeatable system that:

* Analyzes options markets daily
* Applies quantitative pricing models
* Generates scenario-based insights
* Produces a disciplined research report
* Reinforces learning through journaling

---

## 3. Problem Statement

Retail traders:

* Lack structured workflows
* Rely on fragmented tools
* Do not understand pricing mechanics
* Do not track thesis vs outcomes

Existing platforms optimize for **execution**, not **understanding**.

---

## 4. Value Proposition

> “A personal quant research desk that transforms raw options data into structured insight, disciplined thinking, and repeatable learning.”

---

## 5. Key Features (MVP)

### 5.1 Data Ingestion

* Pull options chain (via Moomoo API)
* Fetch underlying price
* Store snapshot locally

---

### 5.2 Pricing Engine

* Black-Scholes pricing
* Implied volatility calculation
* Greeks:

  * Delta
  * Gamma
  * Theta
  * Vega
  * Rho

---

### 5.3 Volatility Analysis

* Historical volatility (HV)
* Implied volatility (IV)
* IV Rank / Percentile

---

### 5.4 Strategy Identification

* Long Call / Put
* Vertical Spreads
* Cash-Secured Put
* Covered Call

---

### 5.5 Scenario Engine

Simulate:

* Price ±5%, ±10%
* IV expansion / contraction
* Time decay

Output:

* P/L matrix
* Breakeven
* Max loss / gain

---

### 5.6 Thesis Generator (LLM-assisted)

Structured output:

* Market expectation
* Model interpretation
* Opportunity framing
* Risk analysis
* Verdict

---

### 5.7 Report Generator

* Markdown → PDF
* Telegram / Email delivery

---

### 5.8 Journal System

* Store thesis
* Track outcomes
* Compare predicted vs actual

---

## 6. Non-Goals (Critical Constraints)

* ❌ Automated trading
* ❌ High-frequency execution
* ❌ Real-time system (MVP is batch)
* ❌ Social sharing / signal selling

---

## 7. User Flow

1. Scheduler triggers daily run
2. Data is fetched
3. Pricing + analysis executed
4. Strategies evaluated
5. Thesis generated
6. Report compiled
7. Report delivered
8. Thesis stored in journal

---

## 8. Success Metrics

### Functional

* Daily report generated without failure
* Accurate pricing outputs (validated vs market)

### Learning

* User reviews report daily
* Journal entries created

### System

* Runtime < 5 minutes per run
* Stable data ingestion

---

## 9. Risks

* Data quality inconsistencies
* Model misinterpretation
* Overfitting to theoretical pricing
* Ignoring liquidity constraints

---

## 10. Future Extensions

* Backtesting engine
* Strategy optimization
* Portfolio-level risk aggregation
* Multi-asset support (stocks, ETFs, futures)

---

## 11. Tech Stack

* Python
* TOML config
* QuantLib (pricing)
* Pandas / NumPy
* ReportLab (PDF)
* Telegram API

---

## 12. Guiding Principle

> “We are not predicting markets. We are building understanding.”

