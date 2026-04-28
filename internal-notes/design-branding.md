# Quant Researcher Desk — Design System

## 1. Design Philosophy

* Clean
* Analytical
* Institutional
* Minimal noise
* Data-first

Inspired by:

* Bloomberg Terminal
* Institutional research PDFs

---

## 2. Color Palette

Base:

* Dark Base (#191414) → Primary background and report chrome
* Soft White (#F7F4F2) → Primary text on dark surfaces
* Muted Gray (#A8A29E) → Secondary labels, table metadata, and footnotes

Accent:

* Tangerine (#FF4632) → Primary action, emphasis, and key finding highlight
* Emerald Green (#2ECC71) → Positive / Gain
* Crimson Red (#E74C3C) → Risk / Loss
* Amber (#F39C12) → Neutral / Watch

Use the dark base as the default visual environment. Avoid returning to the earlier navy/off-white identity except when referencing legacy drafts.

---

## 3. Typography

Headers:

* Poppins
* Bold, structured
* ALL CAPS or Title Case

Body:

* Inter
* Clean sans-serif
* Medium spacing

Code/Data:

* Monospace

---

## 4. Layout Structure

Each report follows:

1. Title Page
2. Market Summary
3. Options Snapshot
4. Strategy Analysis
5. Scenario Table
6. Risk Section
7. Final Verdict

---

## 5. Visual Elements

Charts:

* Simple line charts
* No unnecessary gradients

Tables:

* Clean borders
* Alternating row shading

Icons:

* Minimal
* Functional only

---

## 6. Writing Style (Critical)

Tone:

* Professional
* Direct
* No hype

Structure:

* Statement → Evidence → Interpretation → Risk

Example:

BAD:
“This looks bullish.”

GOOD:
“Implied volatility is below historical average, suggesting potential underpricing of optionality. However, liquidity remains thin, increasing execution risk.”

---

## 7. Report Identity

Each report should feel like:

> “A junior analyst memo from a disciplined fund.”

---

## 8. Automation Compatibility

Design must:

* Render cleanly in Markdown
* Convert to PDF without breakage
* Be parsable by agents

---

## 9. Guiding Principle

> “Clarity over cleverness. Discipline over decoration.”
