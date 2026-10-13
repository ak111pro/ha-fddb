# Changelog

## Unreleased

### Fixed

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
  (`manual` or `fddb`). The settings page costs one extra request at setup and then every 6
  hours (a failed read is retried after 1 hour and never fails the regular update).

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
