# Guilherme Molina — Financial Data & BI

[Live portfolio](https://guilherme-molina-portfolio.guilhermemolinasolan.chatgpt.site/) · [Português](README.pt-BR.md) · [LinkedIn](https://www.linkedin.com/in/guilhermesolano/)

A bilingual portfolio for Data Analyst and BI Analyst opportunities, connecting financial context with reproducible analysis. English is the default; [Portuguese](https://guilherme-molina-portfolio.guilhermemolinasolan.chatgpt.site/pt.html) has equivalent case-study content.

## Start with the evidence

| Case study | Focus | Explore |
| --- | --- | --- |
| Olist E-commerce Analytics | Delivery performance, metric definitions, Power BI and Python data preparation | [Case study](https://guilherme-molina-portfolio.guilhermemolinasolan.chatgpt.site/#olist-case) · [Interactive dashboard, in Portuguese](https://guilherme-molina-portfolio.guilhermemolinasolan.chatgpt.site/olist/) · [Repository](https://github.com/MolinaGG/olist-ecommerce-analytics) |
| Market Lens BR | Coupon-adjusted returns, public data and temporal model validation | [Case study](https://guilherme-molina-portfolio.guilhermemolinasolan.chatgpt.site/#market-case) · [Research demo, in Portuguese](https://market-lens-br-web.onrender.com/) · [Repository](https://github.com/MolinaGG/market-lens-br) |

The site is public, as confirmed through its hosting configuration on 20 November 2026. The research API may take about a minute to wake after inactivity. See each project's methodology before interpreting results.

## What is in this repository

- `index.html` and `pt.html`: English and Portuguese presentation, business questions, findings, limitations and evidence links.
- `finance.css`: responsive styles for the analytical portfolio; no JavaScript is required for the new landing pages.
- `creative.html`, `styles.css` and `app.js`: preserved complementary gallery and project dialogs.
- `olist/`: existing interactive dashboard; analytical logic and data preserved, with the return link updated.
- `docs/github-profile/README.md`: bilingual profile introduction, also published in the [MolinaGG/MolinaGG profile repository](https://github.com/MolinaGG/MolinaGG).
- `assets/`: project images and portrait.

## Run locally

Requires Python 3. No package installation or build is needed.

```bash
python -m http.server 8000
```

Open http://localhost:8000. Use HTTP rather than opening files directly so the Olist dashboard can load its JSON data.

## Context and attribution

Independent studies do not imply a relationship with Olist or other organizations represented in public data. Historical dataset values are not client-impact metrics, recognized revenue or proven losses. Market Lens is exploratory research, not investment advice or a causal model.

The complementary gallery retains project-specific AI-use disclosures. AI-assisted presentation work should not be confused with demonstrated professional experience. Images and third-party brands do not receive a blanket reuse license through this repository.

## Check navigation

```bash
node --test tests/navigation.test.cjs
```
