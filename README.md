# Btech Guru — questions out, answers in

Use this only if the site and your school allow it.

## Flow

1. **Pull questions** — Chrome on port **9222**, mock test open → run `python mocktest_pipeline.py` → you get `output/questions.json`.
2. **Get answers elsewhere** — e.g. paste `questions.json` into **Google Gemini** (or any AI) and ask for a JSON list in **`ans.json` format** (see below).
3. **Apply on the site** — same Chrome/test tab → `python apply_ans_from_json.py --answers ans.json`.

## `ans.json` shape

```json
[
  { "number": 1, "option": 3 },
  { "number": 2, "option": 1 }
]
```

`number` = question id (same as in `questions.json`). `option` = **1-based** choice (first choice = 1).

## Setup

- Python 3.10+
- `pip install playwright beautifulsoup4`
- Chrome with remote debugging **9222** (or use `--launch-chrome` where the script supports it)

## Scripts

| Command | What it does |
|--------|----------------|
| `python mocktest_pipeline.py` | Export mock HTML → `output/questions.json` |
| `python apply_ans_from_json.py --answers ans.json` | Clicks each answer, then NEXT |

Details: `python mocktest_pipeline.py -h` and `python apply_ans_from_json.py -h`.
