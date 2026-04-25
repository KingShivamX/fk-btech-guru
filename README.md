# Btech Guru helper — save questions, fill answers later

**Only use this if the website and your school or rules say it is allowed.**

**You must do the mock test only in the Chrome window that opens from the special Win+R step below — the one this helper can talk to. Do not use another Chrome you opened from the taskbar, Start menu, or a desktop shortcut. If the test is in the wrong window, the commands will do nothing useful or will act on the wrong tab.**

---

## What you are doing (in plain words)

1. You **save a copy** of all the test questions to your computer.
2. You use **Gemini or another AI** to decide the answers and put them in a small list file (`ans.json`).
3. You run a second tool that **clicks those answers** on the real test page for you.

Steps 1 and 3 both use **the same Chrome window** where the test is open. You do not “connect” two programs to each other — you just **leave that test open** and run the tools one after the other.

---

## The two things you type (copy these)

**A — Save the questions** (test page must be open in Chrome, set up as below):

```bash
python mocktest_pipeline.py
```

You get a file: **`output/questions.json`**. Send that to Gemini (or any AI) and ask it to give you back a list like the example under “Answer file”.

**B — Click your answers on the site** (same test tab, usually starting from question 1):

```bash
python apply_ans_from_json.py --answers ans.json
```

---

## Answer file (`ans.json`)

Your AI should give you a list like this. Save it as **`ans.json`** next to these scripts (or pass the full path to the file).

```json
[
  { "number": 1, "option": 3 },
  { "number": 2, "option": 1 }
]
```

- **`number`** — which question (same numbering as in the questions file).
- **`option`** — which answer to pick: **1** = first choice, **2** = second, and so on.

---

## One-time setup on your computer

1. Install **Python** (a recent version is fine).
2. Open **Command Prompt** or **PowerShell** in this folder and run:

```bash
pip install playwright beautifulsoup4
```

3. Chrome needs to be started in a **special way** so these tools can “see” the test page. Normal double‑click on Chrome is not enough.

**On Windows — do this each time before you use the tools:**

1. Close **all** Chrome windows (check the tray icon too).
2. Press **Win + R**, paste this line, press Enter (you can copy from here):

```bat
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data"
```

3. Chrome opens like usual. **In this same window only:** log in and open the mock test. Then run **A** and later **B** above. **Do not switch to some other Chrome — stay in this one.**

If Chrome says the profile is busy, something is still running — close every Chrome completely and try again.

---

## If something goes wrong

Ask someone technical for help, or run:

```bash
python mocktest_pipeline.py -h
python apply_ans_from_json.py -h
```

Those show extra settings (not needed for the basic flow).
