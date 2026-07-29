# Weighted List Manager

A dark-themed web app for scoring and ranking items using
user-defined fields and weights. Runs entirely on your local machine.
This is an early practice project for agentic workflows.

## Requirements

- Python 3.8+
- Flask (`pip install flask`)

## Run

```
cd weighted_list_app
python app.py
```

Your browser will open automatically at http://localhost:5000

## How it works

1. **Create a list** — click New List in the sidebar
2. **Add fields** — click Manage Fields → define field names and weights
3. **Add items** — click Add Item → fill in values (0–10) for each field
4. **Score** — automatically calculated and normalized to 0–10
5. **Rank** — top N items highlighted in gold (configurable in toolbar)

## Scoring Formula

  Score = (Σ value_i × weight_i) / (10 × Σ active_weight_i) × 10

- Fields left blank or set to 0 are excluded from both numerator and denominator
- This ensures scores are always normalized to 0–10 regardless of which fields are filled

## Data

All data is saved automatically to `weighted_lists.db` (SQLite) in the same folder.
No manual saving required.
