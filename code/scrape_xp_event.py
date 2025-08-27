#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from jinja2 import Template


# Helper to parse "3500 XP" or "×3500" → 3500
def parse_xp(text: str) -> int:
    if not text:
        return 0
    # Keep digits and commas only
    nums = re.findall(r'[\d,]+', text.replace('\xa0', ' '))
    if not nums:
        return 0
    n = int(nums[0].replace(',', ''))
    return n


def get_text(el):
    return el.get_text(strip=True) if el else ""


def scrape(url: str, timeout=20):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "xp-scraper/1.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    steps = []
    overall_total = 0

    # Assumption: each "step" is a container that has one .step-name, several .task-reward, and one .page-reward-wrapper
    # Typically the .step-name and .task-reward share the same parent container.
    for step_name_el in soup.select(".step-name"):
        step_container = step_name_el.parent  # in your snippet, tasks are siblings in this parent

        step_title = get_text(step_name_el)

        # Sum XP on each task within this step
        task_items = []
        task_xp_total = 0
        for tr in step_container.find_all("div", class_="task-reward", recursive=False):
            task_text = get_text(tr.select_one(".task-text"))
            # Prefer reward-label text like "3500 XP"
            label_el = tr.select_one(".reward-label span")
            xp = 0
            if label_el and "xp" in get_text(label_el).lower():
                xp = parse_xp(label_el.text)
            else:
                # fallback to ×3500 if present
                qty = tr.select_one(".item-quantity")
                if qty:
                    xp = parse_xp(qty.text)
            task_xp_total += xp
            task_items.append({"task": task_text, "xp": xp})

        # Sum page-level rewards that are XP
        page_reward_total = 0
        page_wrapper = step_container.find("div", class_="page-reward-wrapper")
        if page_wrapper:
            for lab in page_wrapper.select(".reward-label span"):
                txt = get_text(lab)
                if "xp" in txt.lower():
                    page_reward_total += parse_xp(txt)

        step_total = task_xp_total + page_reward_total

        if step_total == 0:
            break

        overall_total += step_total

        steps.append({
            "title": step_title,
            "task_count": len(task_items),
            "tasks": task_items,
            "task_xp_total": task_xp_total,
            "page_xp_total": page_reward_total,
            "step_total": step_total,
        })

    return {
        "url": url,
        "scraped_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "steps": steps,
        "overall_total": overall_total,
    }

# Old style
"""
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Helvetica,Arial,sans-serif;margin:20px;line-height:1.5}
h1,h2{margin:0.2em 0}
small{color:#666}
code{background:#f6f8fa;padding:2px 4px;border-radius:4px}
ul{margin:0.3em 0 0.8em 1.2em}
"""


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>XP Celebration Totals</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    .step{border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0; text-align: left;}
    .total{font-weight:bold}
    text { fill: #facc15; }
    body {
        background-color: #000000;
        color: #00FF00;
        font-family: 'Courier New', Courier, monospace;
        text-align: center;
        margin: 0;
        padding: 20px;
    }
    h1 {
        font-size: 50px;
        text-shadow: 2px 2px #FF0000;
    }
    h2 {
        font-size: 30px;
    }
    .button {
        background-color: #FF00FF;
        color: #000000;
        padding: 10px 20px;
        text-decoration: none;
        font-weight: bold;
        border: 2px dashed #FFFF00;
        display: inline-block;
        margin: 10px;
    }
    .footer {
        margin-top: 50px;
        font-size: 12px;
        color: #FFFFFF;
    }
</style>
</head>
<body>
<h1>XP Totals</h1>
<p>Source: <a href="{{ data.url }}">{{ data.url }}</a><br>
Last updated: {{ data.scraped_at }}</p>

<h2>Overall total: {{ "{:,}".format(data.overall_total) }} XP</h2>

<!-- Add this at the top of the BODY, before rendering the steps loop -->

{% set n = data.steps|length %}
{% set ml = 80 %}
{% set mr = 20 %}
{% set mt = 20 %}
{% set mb = 40 %}
{% set step_dx = 28 %}
{% set inner_w = (step_dx * (n - 1)) if n > 1 else 0 %}
{% set width = ml + inner_w + mr %}
{% set height = mt + 220 + mb %}
{% set inner_h = height - mt - mb %}
{% set raw_max = (data.steps | map(attribute='step_total') | max) if n > 0 else 1 %}
{% set max_total = raw_max if raw_max > 0 else 1 %}
<section id="xp-chart"> <h2>XP per Step</h2> {% if n == 0 %} <p>No steps to display.</p> {% else %} <svg width="{{ width }}" height="{{ height }}" role="img" aria-labelledby="xpChartTitle xpChartDesc"> <title id="xpChartTitle">XP Totals by Step</title> <desc id="xpChartDesc">Line chart showing XP total on the Y axis and step number on the X axis</desc>

  <!-- Axes -->
  <line x1="{{ ml }}" y1="{{ mt }}" x2="{{ ml }}" y2="{{ mt + inner_h }}" stroke="#555" stroke-width="1"/>
  <line x1="{{ ml }}" y1="{{ mt + inner_h }}" x2="{{ ml + inner_w }}" y2="{{ mt + inner_h }}" stroke="#555" stroke-width="1"/>

  <!-- Y-axis ticks, grid, and labels -->
  {% for t in [0, 0.25, 0.5, 0.75, 1] %}
    {% set y = mt + inner_h - t*inner_h %}
    <line x1="{{ ml - 4 }}" y1="{{ y }}" x2="{{ ml }}" y2="{{ y }}" stroke="#555" stroke-width="1"/>
    <text x="{{ ml - 8 }}" y="{{ y + 3 }}" font-size="10" text-anchor="end">{{ (t*max_total)|int | string }}</text>
    <line x1="{{ ml }}" y1="{{ y }}" x2="{{ ml + inner_w }}" y2="{{ y }}" stroke="#ddd" stroke-width="1"/>
  {% endfor %}

  <!-- Line path (polyline) -->
  <polyline fill="none" stroke="#2563eb" stroke-width="2" points="
    {% for s in data.steps %}
      {{ ml + (loop.index0)*step_dx }},{{ mt + inner_h - (s.step_total * inner_h / max_total) }}{% if not loop.last %} {% endif %}
    {% endfor %}
  " />

  <!-- Point markers and tooltips -->
  {% for s in data.steps %}
    {% set x = ml + (loop.index0)*step_dx %}
    {% set y = mt + inner_h - (s.step_total * inner_h / max_total) %}
    <circle cx="{{ x }}" cy="{{ y }}" r="3" fill="#1d4ed8">
      <title>Step {{ loop.index }}: {{ "{:,}".format(s.step_total) }} XP</title>
    </circle>
  {% endfor %}

  <!-- X-axis labels -->
  {% for s in data.steps %}
    <text x="{{ ml + (loop.index0)*step_dx }}" y="{{ mt + inner_h + 14 }}" font-size="10" text-anchor="middle">#{{ loop.index }}</text>
  {% endfor %}

  <!-- Axis labels -->
  <text x="{{ ml + inner_w/2 }}" y="{{ height - 6 }}" text-anchor="middle" font-size="11">Step</text>
  <text x="12" y="{{ mt + inner_h/2 }}" text-anchor="middle" font-size="11" transform="rotate(-90 12 {{ mt + inner_h/2 }})">XP Total</text>
</svg>

{% endif %}
</section>

{% set n = data.steps|length %}
{% for s in data.steps | reverse %}
{% set orig_index = n - loop.index0 %}
<details class="step">
<summary>Step {{ orig_index }} — {{ "{:,}".format(s.step_total) }} XP</summary>
<p>Tasks: {{ s.task_count }}</p>
<ul> 
    {% for t in s.tasks %}
    <li>{{ t.task }} — {{ "{:,}".format(t.xp) }} XP</li>
    {% endfor %}
</ul>
<p>Task XP total: <span class="total">{{ "{:,}".format(s.task_xp_total) }}</span> XP</p>
<p>Page reward XP: <span class="total">{{ "{:,}".format(s.page_xp_total) }}</span> XP</p>
<p>Step total: <span class="total">{{ "{:,}".format(s.step_total) }}</span> XP</p>
</details>
{% endfor %}

<p><small>Generated by your local b00ster.</small></p>
<div class="footer">
    <p>Disclaimer: b00sting may result in bans from ur mom! Use at your own risk!</p>
    <p>&copy; 2025 b00stingIsFun, All Rights Reserved. RGR is a Trademark.</p>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Scrape XP totals from a page and render a static report.")
    ap.add_argument("--url", required=True, help="URL to scrape")
    ap.add_argument("--out-dir", default="output", help="Directory to write index.html and data.json")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # output_data_path = out_dir / "data.json"

    data = scrape(args.url)

    # Write JSON for machine use
    # (out_dir / "data.json").write_text(__import__("json").dumps(data, indent=2), encoding="utf-8")

    # Write HTML report
    html = Template(HTML_TEMPLATE).render(data=data)
    (out_dir / "xp_celebration.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
