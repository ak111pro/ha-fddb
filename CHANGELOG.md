# Changelog

## 0.2.3 – 2026-10-26

### Fixed

- Days with fddb.info's optional **Alcohol column** in the diary table were read wrongly or not
  at all: six cells looked like the old layout, so values shifted (an empty alcohol cell "g"
  gave "Not a number: 'g'", which is why 2026-10-23 was not stored). Columns are now matched by
  their headers ("Calorific value", "Fat", "Carbohydrates", "Protein"); the cell-count rule only
  remains as a fallback for pages without a header row. Same approach as
  [fddb-exporter 2.6.3](https://github.com/itobey/fddb-exporter/releases/tag/2.6.3) by @itobey.

### Changed

- A fat, carbohydrate or protein cell that shows only a unit is unreadable again (as in 0.2.1),
  instead of counting as 0 as in 0.2.2: that cell was the alcohol column, not a missing value.

### Added

- Meal groups named "Morning", "Noon" or "Evening" count as breakfast, lunch and dinner.

## 0.2.2 – 2026-10-26

### Fixed

- The diary could no longer be read (the sensors went `unknown`): fddb.info redesigned the daily
  Details page. Both page versions are now read. On the new page the totals row has five cells
  instead of six and shows the energy as one cell "2749 kJ (657 kcal)", the meal rows as
  "2749 kJ / 657 kcal", and the bread units in a separate column; sugar and fibre are read from
  their dedicated totals row. Being logged out is detected from the logout link on the new page.
  Verified against the live redesigned page.
- Meal rows of the new page are recognised by their own marker (`myday-mealtotal`), and their
  kilocalories also when shown as plain text ("2749 kJ / 657 kcal").
- A product whose fat, carbohydrate or protein value fddb.info shows only as a unit or a dash
  (own foods without that value) counts as 0 instead of making the whole day unreadable. Any
  other unreadable value still stops the read, so a changed page never gives wrong numbers.

## 0.2.1 – 2026-10-21

### Fixed

- Meal sensors (breakfast, lunch, dinner, snacks, other) went `unknown` and the meal group rows
  ("Dinner: 4 products") were counted as products: since 2026-10-21 fddb.info no longer draws
  these rows in grey. Group rows are now also recognised by their "<meal>: n product(s)" label
  (rows without a food-database link); own foods without a link are still products.

## 0.2.0 – 2026-10-14

First release, tested on a live Home Assistant 2026.9.4 installation.

### Changed

- The sensors keep their last values while fddb.info cannot be reached, also across a restart,
  instead of becoming `unavailable` (#18). The last diary of today that was read in full is
  stored and shown; when what is stored is from an older day (for example a restart after
  midnight while fddb.info is down), today shows the values of a day without entries, never the
  previous day's numbers. Meanwhile the *Problem* binary sensor is on and its `error` attribute
  names the reason. A rejected login still starts re-authentication, and a first setup without
  any stored data still waits until fddb.info answers.

### Fixed

- The calories-per-meal sensors show `0` on a day without entries instead of `unknown` (the
  diary page has no meal rows at all then). `unknown` remains for a day with entries but no
  meal rows, i.e. an account that does not group its diary by meals.
- Days stored by an earlier version have no energy balance, so *energy balance yesterday* stayed
  `unknown`. Those days (within the backfill window) are read once more after the update.
- Removing the integration now also deletes its stored history; Home Assistant kept the file
  before.

- The device link ("Visit") now opens `https://fddb.mobi/notepad/` instead of
  `https://fddb.info/db/i18n/myday20/`. The old address answers with a server error unless the
  browser already has an FDDB session; the new one redirects to the login page and shows the
  diary after signing in (#5).
- The protein, carbohydrate and fat share sensors report `0` % on days without entries instead of
  `unknown` (#6).
- The diary window now ends one second before the next day's start instead of exactly 24 hours
  after its own start. On the two days a year when the clocks change (23 or 25 hours long) the
  old window left a one-hour gap or overlap with the neighbouring day (taken over from
  fddb-exporter 2.5.0, #13).
- An unexpected failure inside the diary parser is now reported as a parse error ("website
  probably changed") instead of an unhandled exception (fddb-exporter 2.5.0, #13).
- The history backfill carries on after a day whose page cannot be parsed and retries that day
  after the next restart; a connection error still stops it (fddb-exporter 2.5.0, #13).

### Added

- Calories per meal (#17): for accounts with *Grouping: By meals* there are sensors for
  *Breakfast*, *Snack 1*, *Lunch*, *Snack 2*, *Dinner* and *Snack 3* "calories today"
  (`calories_breakfast`, `calories_snack_1`, `calories_lunch`, `calories_snack_2`,
  `calories_dinner`, `calories_snack_3`; kcal, device class *energy*, state class `total` with
  `last_reset` at midnight German time, **enabled by default**). They show the subtotal of the
  group row of the diary page (a group row with unreadable figures is summed from its
  products), with the meal's `fat`, `carbs` and `protein` in grams as attributes. A meal
  without entries on a grouped day is `0`; a page without any group rows (account not grouped,
  or nothing logged yet) gives `unknown`. A group with another name goes into *Other meals
  calories today* (`calories_other`, **disabled by default**; a debug log line names the group)
  instead of being lost. The six names are an assumption based on FDDB's usual meal groups
  (Breakfast, Lunch, Dinner and Snack 2 and 3 were seen on real pages, Snack 1 was not). The
  `get_diary` response has a new key `meals` with the subtotals by meal.
- Meal and time per product (#16): every entry of the `products` attribute of *Calories today*
  (and of the `products` of the `get_diary` response) has two new keys, `meal` and `time`.
  `meal` is the group the entry is listed under on an account with *Grouping: By meals*
  ("Dinner" from the group row "Dinner: 2 products"); `time` is the time of day as `HH:MM` from
  the hidden time shown next to each entry. Both are `null` when the account does not group its
  diary or the page shows no time.
- Daily goal from the diary page (#15). The diary page shows the required energy of every day
  ("Required energy: 8368 kJ (2000 kcal) Required calories per day"); it is now read with every
  diary request and used as FDDB's goal for that day, stored with each day of the history and
  in the `goal` key of the `get_diary` response. The value of the settings page (#4) is the
  fallback for a page without the block. The **effective goal** is therefore: the number entity
  if above 0, else the diary goal, else the settings page goal. **The `goal_source` attribute
  of *Goal progress* has new values: `manual`, `fddb_diary` or `fddb_profile`** (the former
  `fddb` is now `fddb_profile`). *Daily calorie goal (FDDB)* shows the diary goal of today (or
  the settings page value) and has the same `goal_source` attribute (`fddb_diary` or
  `fddb_profile`).
- Energy balance sensors (#14): *Energy balance today* (`balance`) and *Energy balance yesterday*
  (`balance_yesterday`), in kcal, state class `measurement`, no device class (energy does not
  allow `measurement`). They carry FDDB's own *Balance* block of the diary page ("You consumed
  586 kJ (140 kcal) more energy than you require"): **positive = surplus, negative = deficit**,
  so consumed minus the energy you require including activities. The "less energy" wording of a
  deficit is an assumption (no real sample was available), as is a missing kcal figure being
  taken from kJ / 4.184. Both sensors are `unknown` when the page has no readable balance block.
  The balance is stored with each day, so yesterday's value survives a restart; days stored by
  an earlier version have none. It is also in the `balance` key of the `get_diary` response.
- Water sensor (#7): *Water from food and drinks today* (`water`, litres, device class *volume*,
  state class `total` with `last_reset` at midnight German time, **disabled by default**). It
  is FDDB's *Water* row of the diary page, the water content of everything logged (foods and
  drinks), **not** a drinking-intake tracker. FDDB shows no water intake and no water goal on
  the diary or the settings page, so there are no such sensors.
- Vitamin and mineral sensors from the diary page (#9), all **disabled by default** to keep the
  entity list short: *Vitamin C*, *Retinol (vitamin A)*, *Vitamin D*, *Vitamin E*, *Thiamine
  (vitamin B1)*, *Riboflavin (vitamin B2)*, *Vitamin B6*, *Vitamin B12*, *Iron*, *Zinc*,
  *Magnesium*, *Manganese*, *Fluorine*, *Chlorine*, *Copper*, *Potassium*, *Calcium*,
  *Phosphorus*, *Sulphur* and *Iodine*, each named "... today" (`vitamin_c`, `retinol`,
  `vitamin_d`, `vitamin_e`, `thiamine`, `riboflavin`, `vitamin_b6`, `vitamin_b12`, `iron`,
  `zinc`, `magnesium`, `manganese`, `fluorine`, `chlorine`, `copper`, `potassium`, `calcium`,
  `phosphorus`, `sulphur`, `iodine`). Device class *weight*, unit mg (retinol, vitamin D,
  vitamin B12 and iodine: µg), state class `total` with `last_reset` at midnight German time.
  FDDB switches the unit with the size of a value, so every value is converted from the unit
  the page shows. The page gives no share of the recommended daily amount, so there is no such
  attribute. Values are also in the `nutrients` key of the `get_diary` response.
- Further daily macronutrients from the diary page (#8): *Alcohol today* (`alcohol`, g),
  *Bread units today* (`bread_units`, BE, no device class), *Salt today* (`salt`, g, from the
  "Minerals" table) and *Cholesterol today* (`cholesterol`, mg, disabled by default). Same
  pattern as the other daily totals: state class `total`, `last_reset` at midnight German time,
  device class *weight* (not for BE). Alcohol, bread units and salt are enabled by default. The
  values are found by their label; a row a page does not show makes the sensor `unknown`, a day
  without entries gives `0`. Bread units are read from the "(x BE)" next to the carbohydrate
  total, or calculated as carbohydrates / 12 g if the page does not show them. The `get_diary`
  response has a new key `nutrients` with these values. FDDB does not show saturated fat or
  polyols (sugar alcohols) per day, so there are no sensors for them.
- The *Calories today* sensor has a `products` attribute with today's diary entries
  (`name`, `amount`, `calories`, `fat`, `carbs`, `protein`, `link`; `link` is the relative FDDB
  path, `null` for own foods and recipes). The attribute is excluded from the recorder, so it
  never counts against the 16 KB attribute limit and does not grow the database (#3).
- Daily calorie goal from FDDB (#4). There is a new sensor *Daily calorie goal (FDDB)*
  (`sensor.<user>_daily_calorie_goal_fddb`, kcal, state class `measurement`, no device class)
  with FDDB's *Required calories per day* from the settings page (the kcal figure, or kJ / 4.184
  if kcal is missing). *Calories remaining* and *Goal progress* now use the **effective goal**:
  the number entity *Daily calorie goal* when it is above 0, otherwise the FDDB goal; they are
  only `unknown` when both are missing. *Goal progress* has the attribute `goal_source`
  (`manual`, `fddb_diary` or `fddb_profile`, see #15).
- Profile sensors from the FDDB settings page (#10): *Weight* (kg, device class *weight*, state
  class `measurement`), *Body mass index* (state class `measurement`, attribute `category`, for
  example `Normal`), and the diagnostic sensors *Height* (cm, device class *distance*),
  *Occupation* (level such as `easy`, attribute `description`), *Sports*, *Profile goal* ("My
  goal", for example `Not specified`) and *Activity index* (%). Gender, birthday, first name,
  user name, country and e-mail settings are never read. The profile (and with it the calorie
  goal) costs one extra request at setup and then every 6 hours (a failed read is retried after
  1 hour and never fails the regular update); the values are stored and survive a restart. The
  diagnostics download includes the profile values (nothing personal).

- Diagnostic sensors (category *diagnostic*) for the update itself (#11):
  *Last fetch duration* (`fetch_duration`, s, device class *duration*, measurement, 2 decimals),
  *Consecutive fetch errors* (`consecutive_errors`, with the attributes `last_error` and
  `last_error_time`, not recorded), *Fetch errors total* (`total_errors`, state class
  `total_increasing`) and *Storage size* (`storage_size`, bytes shown as kB, device class
  *data size*). *Last update* now means "last successful read of today's diary" (it no longer
  moves when only yesterday is re-read at night), and together with the error totals it is
  stored and restored across restarts. The diagnostic sensors stay available while an update
  fails.

### Changed

- README: documented why HACS lists the integration without an icon (HACS limitation, tracked
  in hacs/integration#5171; the icon from `custom_components/fddb/brand/` is shown inside
  Home Assistant and the HACS brand check passes) (#2).
- Device classes, state classes and display precision for all sensors (#12):
  - Fat, carbohydrates, sugar, protein and fibre today: device class *weight* (unit g, was no
    class); Calories today, this week and this month: device class *energy* (unit kcal, was no
    class).
  - These sensors, and Products today, change state class from `measurement` to `total` and
    now report `last_reset` (midnight of the day, Monday of the week, first of the month, all
    in German time). Their values and units are unchanged.
  - Shares, yesterday, the 7- and 30-day averages, streak, remaining calories and goal progress
    stay `measurement` (no device class; the energy class does not allow `measurement`).
  - **What you might see:** because the state class of the changed sensors differs from the
    long-term statistics already recorded for them, Home Assistant can show a repair
    "The mean type of sensor.xxx has changed" under Settings > System > Repairs (or in
    Developer tools > Statistics). Use *Fix issue* and choose to delete the old statistics, or
    ignore it; the entities themselves keep working and history charts of the states are not
    affected. Sensors that are *weight* or *energy* can now also be shown in other units
    (for example oz or kJ) in the entity settings, and imperial unit systems show weights in
    ounces.
