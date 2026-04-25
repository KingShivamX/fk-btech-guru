# Btech Guru — questions out, answers in

Use this only if the site and your school allow it.

## Commands

Export questions from the open mock test (Chrome **9222**, test tab visible):

```bash
python mocktest_pipeline.py
```

Apply answers from your AI-generated file (same tab):

```bash
python apply_ans_from_json.py --answers ans.json
```

---

## Flow

1. **Pull questions** — Run the first command → `output/questions.json`.
2. **Get answers elsewhere** — e.g. paste `questions.json` into **Google Gemini** (or any AI) and ask for JSON in **`ans.json` format** (see below).
3. **Apply on the site** — Run the second command.

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

More options: `python mocktest_pipeline.py -h` · `python apply_ans_from_json.py -h`
