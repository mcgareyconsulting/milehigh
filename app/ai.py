import json
import requests


def compare_rows_with_ai_ollama(old_row, new_row, model="mistral"):
    prompt = f"""
Compare the following two data records. You may infer:

- Date equivalence (e.g., "8/6/25" = "2025-08-06")
- Stage/field aliasing (e.g., "Fit Up Complete" = "Fitup comp")
- Name or label variations

DB version (old):
{json.dumps(old_row, indent=2)}

Excel version (new):
{json.dumps(new_row, indent=2)}

Return JSON:
{{
  "safe_to_apply": true/false,
  "changes": {{ "field": "new value", ... }},
  "reasoning": "Explain what changed"
}}

If the header values do not make sense, return:
{{
  "safe_to_apply": false,
  "changes": {{}},
  "reasoning": "Header values do not make sense"
}}
"""

    res = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
    )

    return res.json()["response"]
