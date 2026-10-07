# FDDB for Home Assistant

[![Validate](https://github.com/ak111pro/ha-fddb/actions/workflows/validate.yml/badge.svg)](https://github.com/ak111pro/ha-fddb/actions/workflows/validate.yml)
[![Tests](https://github.com/ak111pro/ha-fddb/actions/workflows/tests.yml/badge.svg)](https://github.com/ak111pro/ha-fddb/actions/workflows/tests.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

> [!WARNING]
> **Experimental, AI-generated, not yet tested in Home Assistant.**
>
> This integration was written by an AI assistant (Claude, by Anthropic) for its owner
> [@ak111pro](https://github.com/ak111pro), based on what the excellent
> [itobey/fddb-exporter](https://github.com/itobey/fddb-exporter) by
> [@itobey](https://github.com/itobey) does. The diary parser has been checked against
> real fddb.info pages, but the integration as a whole has **not yet run in a real Home
> Assistant installation**. Expect bugs, do not rely on it for anything important, and
> please report problems as issues. This notice will be updated once it has been tested.

A Home Assistant integration that reads your food diary from [fddb.info](https://fddb.info)
(the German food and calorie diary) and turns it into sensors: today's
calories and macros, weekly and monthly totals, averages, a logging streak and progress
towards a daily calorie goal.

It works by logging in with your account and reading the diary page, because FDDB offers
no public API. Everything is configured in the UI.

## Features

- Today's calories, fat, carbohydrates, sugar, protein, fibre and number of products
- Macro shares of today's energy (protein, carbohydrates, fat)
- Yesterday, this week (Monday to today), this month, 7-day and 30-day averages
- Logging streak (consecutive days with at least one entry)
- Daily calorie goal with remaining calories and goal progress
- Problem sensor that tells you when FDDB could not be read
- Actions to refresh on demand and to fetch the full diary (all products) of any day
- English and German translations, diagnostics download with credentials redacted
- Supports several FDDB accounts

## Entities

All entities belong to one service device named `FDDB <account>`. Names are shown here
in English with the German name in parentheses.

| Entity | Type | Unit | Description |
| --- | --- | --- | --- |
| Calories today (Kalorien heute) | sensor | kcal | Total energy logged today |
| Fat today (Fett heute) | sensor | g | |
| Carbohydrates today (Kohlenhydrate heute) | sensor | g | |
| Sugar today (Zucker heute) | sensor | g | Part of the carbohydrates |
| Protein today (Eiweiß heute) | sensor | g | |
| Fibre today (Ballaststoffe heute) | sensor | g | |
| Products today (Produkte heute) | sensor | | Number of diary entries |
| Protein share (Eiweißanteil) | sensor | % | Share of energy (protein 4, carbs 4, fat 9 kcal/g) |
| Carbohydrate share (Kohlenhydratanteil) | sensor | % | |
| Fat share (Fettanteil) | sensor | % | |
| Calories yesterday (Kalorien gestern) | sensor | kcal | Needs stored history, see below |
| Calories this week (Kalorien diese Woche) | sensor | kcal | Monday to today |
| Calories this month (Kalorien diesen Monat) | sensor | kcal | 1st of the month to today |
| Average calories 7 days (Durchschnitt Kalorien 7 Tage) | sensor | kcal | Mean of the last 7 days before today, only days with entries |
| Average calories 30 days (Durchschnitt Kalorien 30 Tage) | sensor | kcal | Same for 30 days |
| Logging streak (Erfassungsserie) | sensor | d | Consecutive days with entries; today counts once it has entries |
| Calories remaining (Verbleibende Kalorien) | sensor | kcal | Goal minus today; unknown while no goal is set |
| Goal progress (Zielerreichung) | sensor | % | Today as percentage of the goal |
| Last update (Letzte Aktualisierung) | sensor (diagnostic) | | Time of the last successful read |
| Daily calorie goal (Tägliches Kalorienziel) | number (config) | kcal | 0 = no goal. Stored by the integration |
| Problem (Problem) | binary sensor (diagnostic) | | On when the last update failed; attribute `error` has the reason |

## Installation

### HACS (custom repository)

1. In HACS open the three-dot menu, choose **Custom repositories**.
2. Add `https://github.com/ak111pro/ha-fddb` with category **Integration**.
3. Search for **FDDB** in HACS, download it and restart Home Assistant.

### Manual

Copy the folder `custom_components/fddb` of this repository into the
`custom_components` folder of your Home Assistant configuration and restart Home Assistant.

Requires Home Assistant 2025.8.0 or newer.

## Configuration

1. Go to **Settings > Devices & services > Add integration** and search for **FDDB**.
2. Enter your fddb.info user name (or e-mail) and password. The login is tested right away.
3. Optional: set a daily calorie goal through the number entity *Daily calorie goal*.

**Options** (integration card > Configure):

| Option | Default | Allowed | Description |
| --- | --- | --- | --- |
| Update interval | 30 min | 10 to 1440 min | How often today's diary is read |

If the password changes, Home Assistant asks you to sign in again (re-authentication).

## Actions

### `fddb.refresh`

Reads today's diary now instead of waiting for the next poll.
`config_entry_id` is optional; without it every set-up account is refreshed.

```yaml
action: fddb.refresh
```

### `fddb.get_diary`

Returns the totals and all products of one day as response data. `date` defaults to
today and must not be in the future. If several accounts are set up, `config_entry_id`
is required.

```yaml
action: fddb.get_diary
data:
  date: "2026-10-07"
response_variable: diary
```

Response shape:

```yaml
day: "2026-10-07"
calories: 1850.0
fat: 62.0
carbs: 210.5
sugar: 48.0
protein: 95.0
fibre: 24.0
products:
  - name: Oatmeal
    amount: 150 g
    calories: 146.0
    fat: 2.5
    carbs: 246.2
    protein: 5.1
    link: /db/en/food/.../index.html
    time: "08:15"
```

Example script that sends yesterday's products as a notification:

```yaml
script:
  fddb_yesterday_report:
    alias: FDDB yesterday report
    sequence:
      - action: fddb.get_diary
        data:
          date: "{{ (now() - timedelta(days=1)).date() }}"
        response_variable: diary
      - action: notify.notify
        data:
          title: "Food diary {{ diary.day }}"
          message: >-
            {{ diary.calories | round(0) }} kcal,
            {{ diary.protein | round(0) }} g protein.
            {% for p in diary.products -%}
            {{ p.time or '--:--' }} {{ p.amount or '' }} {{ p.name }}: {{ p.calories | round(0) }} kcal
            {% endfor %}
```

## Days and time zone

FDDB diary days follow **German local time (Europe/Berlin)**, regardless of the time zone
configured in Home Assistant. "Today", "yesterday", the week and the month are all
calculated in that time zone. The week starts on Monday. Yesterday is read once more at
03:15 so its values are final.

## Data storage

- The integration keeps a small local history of daily totals (calories, macros, number of
  products) in Home Assistant's storage. Product lists are not stored.
- Right after setup, the previous **31 days** are fetched once in the background (one
  request every 1.5 seconds) so averages, week and month sums have data immediately.
- History is kept for **400 days**.
- The calorie goal is stored there too. Removing the integration removes this data.

## Limitations

- **This is web scraping.** FDDB has no public API, so the integration logs in and parses
  the diary page. It may stop working whenever fddb.info changes its pages. The *Problem*
  binary sensor turns on and the log shows the reason; please open an issue then.
- The diary is requested in English because the parser relies on English labels
  (for example "thereof Sugar"). Your FDDB account language is not changed.
- Please do not poll aggressively. The default of 30 minutes is plenty; the minimum is 10.
- Values are whatever FDDB shows. Days you edit later are re-read only when they are
  today, yesterday (nightly) or fetched with `fddb.get_diary`.

## Privacy

Your credentials are stored only in your Home Assistant config entries. The integration
contacts **only fddb.info**; there are no third-party services, telemetry or analytics.
Diagnostics downloads redact user name and password.

## Development

Parser and day-window tests run without Home Assistant:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The fixtures in `tests/fixtures` are synthetic and contain no real account data.

## Credits

A big thank you to [@itobey](https://github.com/itobey) for
[fddb-exporter](https://github.com/itobey/fddb-exporter). This integration would not exist
without it: its documentation and behaviour showed how fddb.info can be read reliably
(login, diary pages, where sugar and fibre live, how diary days are addressed). If you
want a standalone exporter with a web UI, statistics, MongoDB/InfluxDB storage and a REST
API, use fddb-exporter. This project is a lean, Home Assistant-only reimplementation of
the reading part, written in Python by an AI assistant. No code from fddb-exporter is
copied here.

## Disclaimer

This project is AI-generated and experimental (see the notice at the top). It is not
affiliated with, endorsed by or connected to FDDB / fddb.info or its operators, nor with
fddb-exporter or its author. FDDB is a trademark of its respective owner. Use at your own risk and respect
FDDB's terms of use.

## License

[MIT](LICENSE)
