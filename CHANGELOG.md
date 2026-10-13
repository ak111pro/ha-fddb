# Changelog

## Unreleased

### Fixed

- The device link ("Visit") now opens `https://fddb.mobi/notepad/` instead of
  `https://fddb.info/db/i18n/myday20/`. The old address answers with a server error unless the
  browser already has an FDDB session; the new one redirects to the login page and shows the
  diary after signing in (#5).
- The protein, carbohydrate and fat share sensors report `0` % on days without entries instead of
  `unknown` (#6).

### Added

- The *Calories today* sensor has a `products` attribute with today's diary entries
  (`name`, `amount`, `calories`, `fat`, `carbs`, `protein`, `link`; `link` is the relative FDDB
  path, `null` for own foods and recipes). The attribute is excluded from the recorder, so it
  never counts against the 16 KB attribute limit and does not grow the database (#3).
