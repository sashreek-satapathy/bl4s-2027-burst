"""
Update the progress meter in the BURST tracker issue.

Reads every open or closed issue labelled `checklist`, counts the task boxes
("- [ ] **Due YYYY-MM-DD** ...") and rewrites the block between the progress
markers in the issue labelled `tracker`. Runs from .github/workflows/progress.yml.
Needs: GH_TOKEN, REPO (owner/name). Uses only the gh CLI and the standard library.
"""
import datetime as dt
import json
import os
import re
import subprocess

REPO = os.environ["REPO"]
DEADLINE = dt.date(2027, 3, 12)
TASK = re.compile(r"^\s*- \[( |x|X)\] \*\*Due (\d{4}-\d{2}-\d{2})\*\*\s*(.*)$", re.M)
START, END = "<!-- progress:start -->", "<!-- progress:end -->"


def gh(*args, stdin=None):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True,
                          input=stdin).stdout


def issues(label):
    out = gh("issue", "list", "--repo", REPO, "--label", label, "--state", "all",
             "--limit", "100", "--json", "number,title,body")
    return sorted(json.loads(out), key=lambda i: i["number"])


def bar(frac, width=20):
    n = round(frac * width)
    return "█" * n + "░" * (width - n)


def main():
    today = dt.date.today()
    rows, all_done, all_total, overdue, upcoming = [], 0, 0, [], []
    for iss in issues("checklist"):
        tasks = TASK.findall(iss["body"] or "")
        done = sum(t[0] != " " for t in tasks)
        all_done += done
        all_total += len(tasks)
        frac = done / len(tasks) if tasks else 0
        title = re.sub(r"^\d+ · ", "", iss["title"])
        rows.append(f"| #{iss['number']} {title} | {done} / {len(tasks)} | `{bar(frac, 10)}` {frac:.0%} |")
        for box, due, text in tasks:
            if box != " ":
                continue
            d = dt.date.fromisoformat(due)
            short = re.split(r"\. Done when", re.sub(r"^\([^)]*\)\s*", "", text))[0][:110]
            item = (d, f"- **{due}** · #{iss['number']} · {short}")
            (overdue if d < today else upcoming).append(item)
    frac = all_done / all_total if all_total else 0
    days_left = (DEADLINE - today).days
    lines = [START,
             f"### Overall: {all_done} of {all_total} tasks done",
             f"`{bar(frac)}` **{frac:.0%}**",
             "",
             f"**{days_left} days** to the deadline (12 March 2027, 23:59 CET). "
             f"**{len(overdue)}** tasks overdue. Updated {today.isoformat()}.",
             "",
             "| Work stream | Done | Progress |", "|---|---|---|", *rows, ""]
    if overdue:
        lines += ["#### Overdue", *[x[1] for x in sorted(overdue)], ""]
    lines += ["#### Due next", *[x[1] for x in sorted(upcoming)[:10]], END]
    block = "\n".join(lines)

    for tr in issues("tracker"):
        body = tr["body"] or ""
        if START in body and END in body:
            new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: block, body, flags=re.S)
        else:
            new = block + "\n\n" + body
        if new != body:                      # no edit when nothing changed (stops loops)
            gh("issue", "edit", str(tr["number"]), "--repo", REPO, "--body-file", "-", stdin=new)
            print(f"updated #{tr['number']}: {all_done}/{all_total}")
        else:
            print("no change")


if __name__ == "__main__":
    main()
