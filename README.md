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
- Further values of the diary page: alcohol, bread units (BE), salt and cholesterol
- Vitamins and minerals of the diary page (20 sensors, disabled by default)
- Water content of the logged foods and drinks (not a drinking-intake tracker; FDDB has none)
- Macro shares of today's energy (protein, carbohydrates, fat)
- Yesterday, this week (Monday to today), this month, 7-day and 30-day averages
- Logging streak (consecutive days with at least one entry)
- Energy balance of the day as FDDB reports it (surplus positive, deficit negative), also for yesterday
- Daily calorie goal (the required energy FDDB shows on each diary day, with your FDDB profile as fallback, or set by hand) with remaining calories and goal progress
- Profile values from FDDB: height, weight, body mass index, occupation, sports, weight goal and activity index
- Problem sensor that tells you when FDDB could not be read
- Actions to refresh on demand and to fetch the full diary (all products) of any day
- English and German translations, diagnostics download with credentials redacted
- Supports several FDDB accounts

## Entities

All entities belong to one service device named `FDDB <account>`. Names are shown here
in English with the German name in parentheses.

| Entity | Type | Unit | Description |
| --- | --- | --- | --- |
| Calories today (Kalorien heute) | sensor | kcal | Total energy logged today. Attribute `products` lists today's diary entries (`name`, `amount`, `calories`, `fat`, `carbs`, `protein`, `link`, `meal`, `time`; `meal` is the meal group the entry is listed under, for example `Dinner`, and `time` the time of day as `HH:MM`, both `null` when the account does not group by meals or the page shows no time); it is not recorded in the history |
| Fat today (Fett heute) | sensor | g | |
| Carbohydrates today (Kohlenhydrate heute) | sensor | g | |
| Sugar today (Zucker heute) | sensor | g | Part of the carbohydrates |
| Protein today (Eiweiß heute) | sensor | g | |
| Fibre today (Ballaststoffe heute) | sensor | g | |
| Alcohol today (Alkohol heute) | sensor | g | |
| Bread units today (Broteinheiten heute) | sensor | BE | As shown next to the carbohydrate total of the diary, otherwise carbohydrates / 12 g |
| Cholesterol today (Cholesterin heute) | sensor | mg | Disabled by default |
| Salt today (Salz heute) | sensor | g | From the *Minerals* table of the diary |
| Water from food and drinks today (Wasser aus Speisen und Getränken heute) | sensor | L | The *Water* row of the diary page: the water content of everything you logged, foods and drinks. **Not** your drinking intake. Disabled by default |
| Vitamin C, Retinol (vitamin A), Vitamin D, Vitamin E, Thiamine (vitamin B1), Riboflavin (vitamin B2), Vitamin B6, Vitamin B12 *today* (Vitamin C ... Vitamin B12 heute) | 8 sensors | mg or µg | The vitamins of the diary page. **Disabled by default.** Retinol, vitamin D and vitamin B12 are in µg, the others in mg |
| Iron, Zinc, Magnesium, Manganese, Fluorine, Chlorine, Copper, Potassium, Calcium, Phosphorus, Sulphur, Iodine *today* (Eisen, Zink, Magnesium, Mangan, Fluor, Chlor, Kupfer, Kalium, Calcium, Phosphor, Schwefel, Jod heute) | 12 sensors | mg or µg | The minerals of the diary page. **Disabled by default.** Iodine is in µg, the others in mg |
| Products today (Produkte heute) | sensor | | Number of diary entries |
| Protein share (Eiweißanteil) | sensor | % | Share of energy (protein 4, carbs 4, fat 9 kcal/g) |
| Carbohydrate share (Kohlenhydratanteil) | sensor | % | |
| Fat share (Fettanteil) | sensor | % | |
| Calories yesterday (Kalorien gestern) | sensor | kcal | Needs stored history, see below |
| Energy balance today (Energiebilanz heute) | sensor | kcal | FDDB's *Balance* block of the diary page: energy consumed minus the energy you require (with activities). **Positive = surplus, negative = deficit.** State class `measurement`, no device class. Unknown when the page has no readable balance |
| Energy balance yesterday (Energiebilanz gestern) | sensor | kcal | The same value for yesterday (from the stored, finalised day); needs stored history, see below |
| Calories this week (Kalorien diese Woche) | sensor | kcal | Monday to today |
| Calories this month (Kalorien diesen Monat) | sensor | kcal | 1st of the month to today |
| Average calories 7 days (Durchschnitt Kalorien 7 Tage) | sensor | kcal | Mean of the last 7 days before today, only days with entries |
| Average calories 30 days (Durchschnitt Kalorien 30 Tage) | sensor | kcal | Same for 30 days |
| Logging streak (Erfassungsserie) | sensor | d | Consecutive days with entries; today counts once it has entries |
| Daily calorie goal (FDDB) (Tägliches Kalorienziel (FDDB)) | sensor | kcal | FDDB's goal for today: the *Required energy* of today's diary page, else *Required calories per day* from your settings page (see [Daily calorie goal](#daily-calorie-goal)). Attribute `goal_source` is `fddb_diary` or `fddb_profile` (`null` when unknown) |
| Calories remaining (Verbleibende Kalorien) | sensor | kcal | Effective goal minus today; unknown while there is no goal |
| Goal progress (Zielerreichung) | sensor | % | Today as percentage of the effective goal. Attribute `goal_source` is `manual`, `fddb_diary` or `fddb_profile` (`null` without a goal) |
| Weight (Gewicht) | sensor | kg | Your weight from the FDDB profile, state class `measurement`, device class *weight* |
| Body mass index (Body-Mass-Index) | sensor | | BMI from the FDDB profile. Attribute `category` has FDDB's text, for example `Normal` |
| Height (Körpergröße) | sensor (diagnostic) | cm | From the FDDB profile, device class *distance* |
| Occupation (Tätigkeit) | sensor (diagnostic) | | The activity level of your occupation, for example `easy`. Attribute `description` has FDDB's full text |
| Sports (Sport) | sensor (diagnostic) | | Your sports setting, for example `no sports` |
| Profile goal (Profilziel) | sensor (diagnostic) | | The goal setting of the FDDB profile ("My goal"), for example `Not specified` |
| Activity index (Aktivitätsindex) | sensor (diagnostic) | % | FDDB's activity index |
| Last update (Letzte Aktualisierung) | sensor (diagnostic) | | Time of the last successful read; kept across restarts |
| Last fetch duration (Dauer des letzten Abrufs) | sensor (diagnostic) | s | How long the last update took, including a failed one (for example a timeout) |
| Consecutive fetch errors (Aufeinanderfolgende Abruffehler) | sensor (diagnostic) | | Failed updates in a row, back to 0 after a success. Attributes `last_error` and `last_error_time` keep the most recent failure (also after it recovered) |
| Fetch errors total (Abruffehler gesamt) | sensor (diagnostic) | | Failed updates counted since the integration was set up (kept across restarts) |
| Storage size (Speichergröße) | sensor (diagnostic) | B (shown as kB) | Size of the integration's file in Home Assistant's `.storage` folder. Refreshed on every update, so it shows the file as the previous save left it |
| Daily calorie goal (Tägliches Kalorienziel) | number (config) | kcal | Optional override of the FDDB goal; 0 = use the FDDB goal. Stored by the integration |
| Problem (Problem) | binary sensor (diagnostic) | | On when the last update failed; attribute `error` has the reason |

The diagnostic sensors stay available while an update fails (all other sensors become
unavailable). Only the regular update counts for duration and errors; failures of the
background jobs (nightly yesterday read, history backfill) are only logged. Per-integration CPU
or memory use cannot be measured, because all integrations share the Home Assistant process.

The profile sensors are read from your FDDB settings page (see [Profile](#profile)), so they
are `unknown` until it was read once and `unknown` for a value your profile does not contain.

FDDB does not show saturated fat or sugar alcohols (polyols) per day, so there are no sensors for
them. It also has no water intake (drinks tracker) and no water goal on the diary or settings
page, so there are no such sensors; the water sensor above only reports the water content of the
foods and drinks you logged. The values of the diary page that are not part of every page (alcohol, salt, cholesterol)
are `unknown` when a page does not list them, and `0` on a day without entries. Sensors that
are disabled by default can be enabled under the device's entities (*Settings > Devices &
services > FDDB*).

The vitamin and mineral sensors are named `<nutrient> today` (for example *Vitamin C today*),
use the device class *weight* with the unit mg or µg and the same state class as the macros.
FDDB writes the same nutrient in µg one day and in mg the next; the integration converts every
value to the unit of its sensor. FDDB does not show the share of the recommended daily amount,
so the sensors have no such attribute. Note FDDB's own warning on the page: not every food has
vitamin and mineral data, so these totals can be too low.

Daily values (calories, macros, number of products) use state class `total` with
`last_reset` at midnight German time; weekly and monthly calories reset on Monday and on the
1st. Calories and macros have the device classes *energy* (kcal) and *weight* (g).

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
3. Optional: override the daily calorie goal through the number entity *Daily calorie goal*
   (see [Daily calorie goal](#daily-calorie-goal)).

**Options** (integration card > Configure):

| Option | Default | Allowed | Description |
| --- | --- | --- | --- |
| Update interval | 30 min | 10 to 1440 min | How often today's diary is read |

If the password changes, Home Assistant asks you to sign in again (re-authentication).

## Daily calorie goal

*Calories remaining* and *Goal progress* use an **effective goal**:

1. the number entity *Daily calorie goal*, if it is set to more than 0 (`goal_source: manual`),
2. otherwise the goal FDDB reports for today, shown by the sensor *Daily calorie goal (FDDB)*:
   the **Required energy** block of the diary page of that day (`goal_source: fddb_diary`),
3. otherwise the value of **Settings > Required calories per day** of your FDDB account
   (`goal_source: fddb_profile`),
4. otherwise both sensors are `unknown`.

The diary page shows the required energy of every day ("8368 kJ (2000 kcal) Required calories
per day"), so it is read with the normal diary request and is always the value of that day. It is
also stored with each day of the history (and is in the `goal` key of the `get_diary` response),
so a past day keeps the goal it had. The fallback is the settings page value, which is read
together with the profile (see [Profile](#profile)), not on every poll, so a change in FDDB shows
up after at most 6 hours (or after a reload of the integration). Both are shown in kJ and kcal by
FDDB; the integration uses the kcal figure and, if that is missing, converts the kJ value
(kJ / 4.184). The last settings page value is kept across restarts; if that page cannot be read,
the old value stays.

Setting the number entity back to 0 switches to the FDDB goal again.

## Profile

The profile values and the goal come from one extra request to your FDDB settings page
(`https://fddb.info/db/i18n/profile20/?lang=en`). It is made when the integration is set up
(also after re-authentication, which reloads it) and then **every 6 hours**, not on every poll; a
failed read is retried after 1 hour and never turns *Problem* on, the last known values stay.

Read are only: height, weight, body mass index (with its category), occupation, sports, the goal
setting, the activity index and the required calories per day. Gender, birthday, first name, user
name, country and the e-mail and account settings are **never read**, stored or logged. The
values are matched by their label text on the English page, so a changed label gives `unknown`
for that one value (and a debug log line) instead of an error.

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
nutrients:  # further values of the page, in g, mg or µg; keys the page does not show are missing
  alcohol: 0.0
  cholesterol: 179.0
  salt: 7.5809
  bread_units: 22.6
  water: 0.4  # litres, water content of the logged foods and drinks
  vitamin_c: 1.3
  vitamin_d: 2.5192
  iron: 11.8
  # ... all vitamins and minerals the page shows
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
- The calorie goal (the number entity and the last goal read from FDDB) and the last profile values are stored there too, as are the
  time of the last successful read and the error counters of the diagnostic sensors. Removing the
  integration removes this data.

## Limitations

- **This is web scraping.** FDDB has no public API, so the integration logs in and parses
  the diary page. It may stop working whenever fddb.info changes its pages. The *Problem*
  binary sensor turns on and the log shows the reason; please open an issue then.
- The diary and the settings page are requested in English because the parser relies on English
  labels (for example "thereof Sugar", "Required calories per day"). Your FDDB account language is not changed.
- **HACS shows a placeholder instead of the FDDB icon** in its own repository list. The icon is
  fine inside Home Assistant (Settings > Devices & services, the device page), where it is
  served from `custom_components/fddb/brand/` (Home Assistant 2026.3 and newer). HACS 2.0.5
  still loads its list icons only from the public `brands.home-assistant.io` CDN, and the
  `home-assistant/brands` repository no longer accepts images for custom integrations, so
  there is nothing this integration can do about it. It is a known HACS limitation
  ([hacs/integration#5171](https://github.com/hacs/integration/issues/5171)) and it does not
  affect HACS downloads or updates. The icon will appear once HACS reads the brand folder.
- Please do not poll aggressively. The default of 30 minutes is plenty; the minimum is 10.
- Values are whatever FDDB shows. Days you edit later are re-read only when they are
  today, yesterday (nightly) or fetched with `fddb.get_diary`.

## Privacy

Your credentials are stored only in your Home Assistant config entries. The integration
contacts **only fddb.info**; there are no third-party services, telemetry or analytics.
Diagnostics downloads redact user name and password and contain the profile values listed above (height, weight, ...), but no personal details like your name or birthday.

## Development

Parser and day-window tests run without Home Assistant:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt ruff
pytest
ruff check . && ruff format --check .
```

`tests/test_sensor_entities.py` needs Home Assistant itself and is skipped when it is not
installed; run it in an environment that has Home Assistant (for example `python3 -m pytest`
inside the Home Assistant container, on a copy of the repository).

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
