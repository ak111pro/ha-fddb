# Changelog

## Unreleased

### Fixed

- The device link ("Visit") now opens `https://fddb.mobi/notepad/` instead of
  `https://fddb.info/db/i18n/myday20/`. The old address answers with a server error unless the
  browser already has an FDDB session; the new one redirects to the login page and shows the
  diary after signing in (#5).
