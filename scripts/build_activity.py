import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets"
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
WEEKDAY_NAMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
FONT = "'Segoe UI', Inter, -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif"

THEMES = {
    "dark": {
        "surface": "#0d1117",
        "border": "#30363d",
        "ink": "#f0f6fc",
        "ink_secondary": "#9198a1",
        "ink_muted": "#6e7681",
        "ramp": ["#1b2129", "#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
        "bar": "#2a78d6",
        "bar_peak": "#6da7ec",
        "highlight": "#f0f6fc",
    },
    "light": {
        "surface": "#ffffff",
        "border": "#d1d9e0",
        "ink": "#1f2328",
        "ink_secondary": "#59636e",
        "ink_muted": "#818b98",
        "ramp": ["#eff2f5", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
        "bar": "#3987e5",
        "bar_peak": "#184f95",
        "highlight": "#1f2328",
    },
}

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def run_query(token, variables):
    payload = json.dumps({"query": CALENDAR_QUERY, "variables": variables}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]["user"]


def fetch_calendar(token, login, today):
    first_page = run_query(token, {"login": login, "from": f"{today.year}-01-01T00:00:00Z", "to": f"{today.isoformat()}T23:59:59Z"})
    created_year = int(first_page["createdAt"][:4])
    counts_by_day = {}
    pages = [first_page] + [
        run_query(token, {"login": login, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"})
        for year in range(created_year, today.year)
    ]
    for page in pages:
        for week in page["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                counts_by_day[dt.date.fromisoformat(day["date"])] = day["contributionCount"]
    return counts_by_day


def longest_streak(counts_by_day):
    best = current = 0
    previous_day = None
    for day in sorted(day for day, count in counts_by_day.items() if count > 0):
        current = current + 1 if previous_day and (day - previous_day).days == 1 else 1
        best = max(best, current)
        previous_day = day
    return best


def current_streak(counts_by_day, today):
    cursor = today if counts_by_day.get(today, 0) > 0 else today - dt.timedelta(days=1)
    streak = 0
    while counts_by_day.get(cursor, 0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak


def summarize(counts_by_day, today):
    year_start = today - dt.timedelta(days=364)
    last_year = {day: count for day, count in counts_by_day.items() if year_start <= day <= today}
    best_day, best_count = max(last_year.items(), key=lambda item: (item[1], item[0]))
    weekday_totals = [0] * 7
    for day, count in last_year.items():
        weekday_totals[day.weekday()] += count
    return {
        "last_year": last_year,
        "total": sum(last_year.values()),
        "active_days": sum(1 for count in last_year.values() if count > 0),
        "best_day": best_day,
        "best_count": best_count,
        "current_streak": current_streak(counts_by_day, today),
        "longest_streak": longest_streak(counts_by_day),
        "weekday_totals": weekday_totals,
    }


def format_number(value):
    return f"{value:,}".replace(",", ".")


def intensity_thresholds(values):
    positive = sorted(value for value in values if value > 0)
    if not positive:
        return [1] * 6
    return [positive[min(len(positive) - 1, int(len(positive) * share))] for share in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)]


def ramp_color(ramp, count, thresholds):
    if count == 0:
        return ramp[0]
    for level, limit in enumerate(thresholds):
        if count <= limit:
            return ramp[level + 1]
    return ramp[-1]


def text(x, y, content, size, fill, weight=400, anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{content}</text>'


def render(summary, today, theme):
    colors = THEMES[theme]
    width, height = 840, 452
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">',
        f'<title>Atividade no GitHub: {format_number(summary["total"])} contribuições no último ano</title>',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{colors["surface"]}" stroke="{colors["border"]}"/>',
        text(28, 42, "Atividade no GitHub", 18, colors["ink"], 600),
        text(width - 28, 42, f"últimos 12 meses, atualizado em {today.strftime('%d/%m/%Y')}", 12, colors["ink_muted"], anchor="end"),
    ]

    metrics = [
        (format_number(summary["total"]), "contribuições"),
        (format_number(summary["best_count"]), f"no melhor dia ({summary['best_day'].strftime('%d/%m/%y')})"),
        (f"{summary['current_streak']} dias", "de sequência atual"),
        (f"{summary['longest_streak']} dias", "de maior sequência"),
        (f"{summary['active_days']}", "dias ativos em 365"),
    ]
    metric_width = (width - 56) / len(metrics)
    for index, (value, label) in enumerate(metrics):
        x = 28 + index * metric_width
        parts.append(text(x, 92, value, 28, colors["ink"], 700))
        parts.append(text(x, 114, label, 12, colors["ink_secondary"]))

    cell, gap = 11, 3
    grid_left, grid_top = 58, 166
    first_sunday = today - dt.timedelta(days=364)
    first_sunday -= dt.timedelta(days=(first_sunday.weekday() + 1) % 7)
    thresholds = intensity_thresholds(summary["last_year"].values())
    day = first_sunday
    column = 0
    labeled_month = None
    while day <= today:
        row = (day.weekday() + 1) % 7
        x = grid_left + column * (cell + gap)
        y = grid_top + row * (cell + gap)
        count = summary["last_year"].get(day, 0)
        outline = f' stroke="{colors["highlight"]}" stroke-width="1.5"' if day == summary["best_day"] else ""
        parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{ramp_color(colors["ramp"], count, thresholds)}"{outline}/>')
        if row == 0 and day.day <= 7 and day.month != labeled_month and column < 51:
            parts.append(text(x, grid_top - 10, MONTHS[day.month - 1], 11, colors["ink_muted"]))
            labeled_month = day.month
        if row == 6:
            column += 1
        day += dt.timedelta(days=1)
    for row, label in [(1, "seg"), (3, "qua"), (5, "sex")]:
        parts.append(text(28, grid_top + row * (cell + gap) + 9, label, 11, colors["ink_muted"]))

    legend_y = grid_top + 7 * (cell + gap) + 18
    legend_x = width - 28 - len(colors["ramp"]) * (cell + gap) - 30
    parts.append(text(legend_x - 6, legend_y + 9, "menos", 11, colors["ink_muted"], anchor="end"))
    for level, color in enumerate(colors["ramp"]):
        parts.append(f'<rect x="{legend_x + level * (cell + gap)}" y="{legend_y}" width="{cell}" height="{cell}" rx="2" fill="{color}"/>')
    parts.append(text(legend_x + len(colors["ramp"]) * (cell + gap) + 3, legend_y + 9, "mais", 11, colors["ink_muted"]))

    section_top = legend_y + 44
    strongest = WEEKDAY_NAMES[summary["weekday_totals"].index(max(summary["weekday_totals"]))]
    parts.append(text(28, section_top, f"Por dia da semana: {strongest} é o mais forte", 13, colors["ink_secondary"], 600))
    bar_area = 56
    bars_top = section_top + 28
    slot_width = (width - 56) / 7
    bar_width = min(64, slot_width - 16)
    peak = max(summary["weekday_totals"]) or 1
    for index, total in enumerate(summary["weekday_totals"]):
        bar_height = max(total / peak * bar_area, 2)
        center = 28 + slot_width * index + slot_width / 2
        x = center - bar_width / 2
        y = bars_top + bar_area - bar_height
        fill = colors["bar_peak"] if total == peak else colors["bar"]
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="3" fill="{fill}"/>')
        parts.append(text(f"{center:.1f}", f"{y - 6:.1f}", format_number(total), 11, colors["ink_secondary"], 600, "middle"))
        parts.append(text(f"{center:.1f}", bars_top + bar_area + 16, WEEKDAYS[index], 11, colors["ink_muted"], anchor="middle"))

    parts.append("</svg>")
    return "".join(parts)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("PROFILE_LOGIN", "DevGabrielSouza")
    if not token:
        sys.exit("GITHUB_TOKEN is required")
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
    summary = summarize(fetch_calendar(token, login, today), today)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUTPUT_DIR / f"activity-{theme}.svg").write_text(render(summary, today, theme), encoding="utf-8")


if __name__ == "__main__":
    main()
