"""Parse FDDB diary pages (no Home Assistant imports, so it can be tested on its own)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import logging
import re

from bs4 import BeautifulSoup, Tag

_LOGGER = logging.getLogger(__name__)


class FddbError(Exception):
    """Base error."""


class FddbAuthError(FddbError):
    """Login failed or the session is no longer valid."""


class FddbConnectionError(FddbError):
    """fddb.info could not be reached."""


class FddbParseError(FddbError):
    """The page did not look like expected (website probably changed)."""


# Energy per gram, used to turn grams of macros into shares of energy.
KCAL_PER_GRAM = {"fat": 9.0, "carbs": 4.0, "protein": 4.0}


@dataclass(slots=True)
class Product:
    """One diary entry."""

    name: str
    amount: str | None
    calories: float
    fat: float
    carbs: float
    protein: float
    link: str | None
    time: str | None = None

    def as_attribute(self) -> dict[str, str | float | None]:
        """Compact form used for the ``products`` state attribute (no time of day)."""
        return {
            "name": self.name,
            "amount": self.amount,
            "calories": self.calories,
            "fat": self.fat,
            "carbs": self.carbs,
            "protein": self.protein,
            "link": self.link,
        }


@dataclass(slots=True)
class DiaryDay:
    """Totals and products of one diary day."""

    day: date
    calories: float = 0.0
    fat: float = 0.0
    carbs: float = 0.0
    sugar: float = 0.0
    protein: float = 0.0
    fibre: float = 0.0
    products: list[Product] = field(default_factory=list)
    # Further per-day values of the diary page by key (see ``NUTRIENTS`` and ``bread_units``),
    # in the unit of that key. A key is missing when the page does not show the value.
    nutrients: dict[str, float] = field(default_factory=dict)

    @property
    def has_entries(self) -> bool:
        return bool(self.products) or self.calories > 0

    def nutrient(self, key: str) -> float | None:
        """A value from ``nutrients``; 0 on a day without entries, None if the page lacks it."""
        value = self.nutrients.get(key)
        if value is None and not self.has_entries:
            return 0.0
        return value

    def product_attributes(self) -> list[dict[str, str | float | None]]:
        """The diary entries for the ``products`` attribute of the daily summary sensor."""
        return [product.as_attribute() for product in self.products]

    def macro_share(self, macro: str) -> float:
        """Share of ``fat``, ``carbs`` or ``protein`` in the energy of the three macros, in %.

        Returns 0.0 on a day without any macros (nothing logged) instead of dividing by zero.
        """
        energy = {key: getattr(self, key) * factor for key, factor in KCAL_PER_GRAM.items()}
        total = sum(energy.values())
        return round(energy[macro] / total * 100, 1) if total else 0.0

    def as_dict(self, with_products: bool = True) -> dict:
        data = asdict(self)
        data["day"] = self.day.isoformat()
        if not with_products:
            data.pop("products")
        return data


_NUMBER = re.compile(r"[^0-9.]")
# "150 g Pizza", "1 Scoop Whey", "0.5 Portion Salat": amount = number + unit, rest = name.
_AMOUNT = re.compile(r"^(\d[\d.,/]*\s+\S+)\s+(.+)$")
_SUGAR = re.compile(r"thereof\s+sugar", re.IGNORECASE)
_FIBRE = re.compile(r"dietary\s+fib(re|er)", re.IGNORECASE)
_LOGIN_TEXTS = {"login", "anmelden"}

# Per-day values of the nutrient tables below the diary (the summary table, "Vitamins" and
# "Minerals"), found by their English label: key -> (label, unit the value is converted to).
# FDDB switches the unit with the size of a value (Vitamin D as "2.5 μg" one day and as
# "0.0326 mg" the next), so every value is read with its own unit and converted.
NUTRIENTS: dict[str, tuple[str, str]] = {
    "alcohol": ("Alcohol", "g"),
    "cholesterol": ("Cholesterol", "mg"),
    "salt": ("Salt", "g"),
}
_LABEL_TO_NUTRIENT = {label.lower(): (key, unit) for key, (label, unit) in NUTRIENTS.items()}

# Bread units (BE) follow from the carbohydrates: FDDB shows 1 BE per 12 g.
GRAMS_PER_BREAD_UNIT = 12.0
_BREAD_UNITS = re.compile(r"\(\s*([\d.,]+)\s*BE\s*\)", re.IGNORECASE)
_VALUE_WITH_UNIT = re.compile(r"^\s*(\d[\d,]*(?:\.\d+)?|\.\d+)\s*([^\d\s(.,][^\s(]*)?")
# Factors to the smallest unit of each family (micrograms, millilitres). FDDB writes the Greek
# letter "μ", normalised to the micro sign "µ" before the lookup.
_MASS_UNITS = {"µg": 1.0, "ug": 1.0, "mcg": 1.0, "mg": 1_000.0, "g": 1_000_000.0}
_VOLUME_UNITS = {
    "ml": 1.0,
    "l": 1_000.0,
    "litre": 1_000.0,
    "litres": 1_000.0,
    "liter": 1_000.0,
    "liters": 1_000.0,
}


def _number(text: str) -> float:
    cleaned = _NUMBER.sub("", text)
    if not cleaned or cleaned == ".":
        raise FddbParseError(f"Not a number: {text!r}")
    try:
        return float(cleaned)
    except ValueError as err:
        raise FddbParseError(f"Not a number: {text!r}") from err


def _cell_value(cell: Tag) -> float:
    # Carbs cells can carry bread units in a second tag, e.g. "246.2 g (20.5 BE)".
    first = cell.find(["span", "b"])
    return _number((first or cell).get_text(" ", strip=True))


def _convert(text: str, target: str) -> float | None:
    """The number in ``text`` ("2.5 μg", "0.1 litres") in ``target`` ("µg", "mg", "g", "l").

    None if there is no number or the unit is missing, unknown or of another kind (mass versus
    volume), so a changed page never produces a wrong value.
    """
    match = _VALUE_WITH_UNIT.match(text)
    if match is None or match.group(2) is None:
        return None
    unit = match.group(2).lower().replace("μ", "µ")
    family = _VOLUME_UNITS if target == "l" else _MASS_UNITS
    if unit not in family:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return round(value * family[unit] / family[target], 6)


def _nutrients(soup: BeautifulSoup) -> dict[str, float]:
    """The values of ``NUTRIENTS`` that the page shows, by label (first match per key)."""
    found: dict[str, float] = {}
    for row in soup.select("table:not(.myday-table-std) tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label = _LABEL_TO_NUTRIENT.get(" ".join(cells[0].get_text(" ", strip=True).lower().split()))
        if label is None or label[0] in found:
            continue
        key, unit = label
        value = _convert(cells[1].get_text(" ", strip=True), unit)
        if value is None:
            _LOGGER.debug("Diary value %r missing or not readable", key)
            continue
        found[key] = value
    return found


def _bread_units(carbs_cell: Tag, carbs: float) -> float:
    """Bread units of the day: as shown next to the carbohydrate total, else carbs / 12 g."""
    match = _BREAD_UNITS.search(carbs_cell.get_text(" ", strip=True))
    if match is not None:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            pass
    return round(carbs / GRAMS_PER_BREAD_UNIT, 1)


def is_logged_out(soup: BeautifulSoup) -> bool:
    """True if the page shows the login link instead of a logged-in session."""
    for link in soup.select("div.quicklinks a.v2hdlnk"):
        if link.get_text(strip=True).lower() in _LOGIN_TEXTS:
            return True
    return False


def _is_category_row(cells: list[Tag]) -> bool:
    for cell in cells:
        for span in cell.select("span[style]"):
            if "color:#aaaaaa" in span["style"].replace(" ", "").lower():
                return True
    return False


def _parse_product(cells: list[Tag]) -> Product:
    first = cells[0]
    time_span = first.select_one("span.mydayshowtime")
    link = first.find("a")
    if link is not None:
        text = link.get_text(" ", strip=True)
    else:
        # Own foods and recipes have no link to the food database, only plain text.
        text = " ".join(
            s.strip()
            for s in first.find_all(string=True)
            if not (time_span and s.parent is time_span)
        ).strip()
    if not text:
        raise FddbParseError("Product row without a name")
    match = _AMOUNT.match(text)
    amount, name = (match.group(1), match.group(2)) if match else (None, text)
    return Product(
        name=name.strip(),
        amount=amount,
        calories=_cell_value(cells[2]),
        fat=_cell_value(cells[3]),
        carbs=_cell_value(cells[4]),
        protein=_cell_value(cells[5]),
        link=link.get("href") if link is not None else None,
        time=time_span.get_text(strip=True) if time_span else None,
    )


def _labelled_value(soup: BeautifulSoup, label: re.Pattern[str]) -> float:
    for row in soup.select("table:not(.myday-table-std) tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) >= 2 and label.fullmatch(cells[0].get_text(" ", strip=True)):
            return _cell_value(cells[1])
    raise FddbParseError(f"Row {label.pattern!r} not found")


def parse_diary(html: str, day: date) -> DiaryDay:
    """Parse a diary page. Returns an empty DiaryDay if nothing was logged that day.

    Only ``FddbError`` subclasses escape: an unexpected failure inside the parser (a changed page
    layout can trip almost anything) is reported as ``FddbParseError`` so callers can treat it
    like any other "website changed" problem instead of crashing.
    """
    try:
        return _parse_diary(html, day)
    except FddbError:
        raise
    except Exception as err:
        raise FddbParseError(f"Could not parse the diary page: {err!r}") from err


def _parse_diary(html: str, day: date) -> DiaryDay:
    soup = BeautifulSoup(html, "html.parser")
    if is_logged_out(soup):
        raise FddbAuthError("Not logged in")

    table = soup.select_one("table.myday-table-std")
    if table is None:
        return DiaryDay(day=day)

    rows = [r for r in table.find_all("tr") if r.find_all("td", recursive=False)]
    if not rows:
        return DiaryDay(day=day)

    footer, product_rows = rows[-1], rows[:-1]
    footer_cells = footer.find_all("td", recursive=False)
    if len(footer_cells) < 6:
        raise FddbParseError("Unexpected totals row")

    products = []
    for row in product_rows:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 6 or _is_category_row(cells):
            continue
        products.append(_parse_product(cells))

    carbs = _cell_value(footer_cells[4])
    nutrients = _nutrients(soup)
    nutrients["bread_units"] = _bread_units(footer_cells[4], carbs)
    return DiaryDay(
        day=day,
        calories=_cell_value(footer_cells[2]),
        fat=_cell_value(footer_cells[3]),
        carbs=carbs,
        protein=_cell_value(footer_cells[5]),
        sugar=_labelled_value(soup, _SUGAR),
        fibre=_labelled_value(soup, _FIBRE),
        products=products,
        nutrients=nutrients,
    )


# --- profile page (settings) -----------------------------------------------------------------

# One kilocalorie is 4.184 kilojoules.
KJ_PER_KCAL = 4.184

_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
_KCAL = re.compile(r"([\d.,]+)\s*kcal", re.IGNORECASE)
_KJ = re.compile(r"([\d.,]+)\s*kj", re.IGNORECASE)
_LINE = re.compile(r"^([^:]+?)\s*:\s*(.*)$")

# Labels on the English settings page. Rows are found by their label text, not by position, so
# a reordered page still parses. Every other line on the page (gender, birthday, first name,
# country, e-mail and account settings) is deliberately never looked at.
_PROFILE_LABELS = {
    "height": "height",
    "weight": "weight",
    "body mass index": "bmi",
    "occupation": "occupation",
    "sports": "sports",
    "my goal": "goal",
    "required calories per day": "calories",
    "activity index": "activity",
}


@dataclass(slots=True)
class Profile:
    """The profile values of the FDDB settings page that are useful in Home Assistant.

    Only these values are ever read from the page. Personal details (name, user name, birthday,
    gender, country, e-mail settings) are not parsed, so they cannot end up in storage, logs or
    diagnostics. A value the page does not show is ``None``.
    """

    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    # Text under the BMI line, for example "Normal".
    bmi_category: str | None = None
    # Level and description exactly as FDDB shows it, e.g. "easy - Example: Student, ...".
    occupation: str | None = None
    sports: str | None = None
    # The weight goal text, e.g. "Not specified".
    goal: str | None = None
    activity_index: float | None = None
    # Required energy per day in kcal (what FDDB calls "Required calories per day").
    calorie_goal: float | None = None

    def as_dict(self) -> dict[str, str | float | None]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> Profile:
        """Rebuild from stored data, ignoring unknown keys and wrongly typed values."""
        profile = cls()
        if not isinstance(data, dict):
            return profile
        for key in cls.__slots__:
            value = data.get(key)
            if key in _TEXT_FIELDS:
                if isinstance(value, str):
                    setattr(profile, key, value)
            elif isinstance(value, int | float) and not isinstance(value, bool):
                setattr(profile, key, float(value))
        return profile


_TEXT_FIELDS = frozenset({"bmi_category", "occupation", "sports", "goal"})


def _decimal(text: str) -> float | None:
    """The first number in ``text``; "1,600" is a thousands separator, "78,5" a decimal comma."""
    match = re.search(r"\d[\d.,]*", text)
    if match is None:
        return None
    raw = match.group(0).rstrip(".,")
    raw = raw.replace(",", "") if _THOUSANDS.match(raw) else raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _required_kcal(text: str) -> float | None:
    """kcal from "8368 kJ (2000 kcal)": the kcal figure if there is one, else kJ / 4.184."""
    if (match := _KCAL.search(text)) is not None:
        value = _decimal(match.group(1))
    elif (match := _KJ.search(text)) is not None:
        kilojoules = _decimal(match.group(1))
        value = round(kilojoules / KJ_PER_KCAL) if kilojoules is not None else None
    else:
        return None
    return value if value and value > 0 else None


def _cell_lines(cell: Tag) -> list[str]:
    """The text of a cell split at its ``<br>`` tags, whitespace (also &nbsp;) normalised."""
    lines: list[list[str]] = [[]]
    for node in cell.descendants:
        if isinstance(node, Tag):
            if node.name == "br":
                lines.append([])
        elif node.parent is not None and node.parent.name not in ("script", "style"):
            lines[-1].append(str(node))
    return [" ".join("".join(parts).split()) for parts in lines if "".join(parts).strip()]


def _profile_fields(soup: BeautifulSoup) -> dict[str, str]:
    """Raw value text per known label, plus ``bmi_category`` (the line after the BMI)."""
    found: dict[str, str] = {}
    for cell in soup.select("td.profiletabletop, td.profiletable"):
        lines = _cell_lines(cell)
        for index, line in enumerate(lines):
            match = _LINE.match(line)
            if match is None:
                continue
            field_name = _PROFILE_LABELS.get(match.group(1).strip().lower())
            if field_name is None or field_name in found:
                continue
            found[field_name] = match.group(2).strip()
            if field_name == "bmi" and index + 1 < len(lines) and ":" not in lines[index + 1]:
                found["bmi_category"] = lines[index + 1]
    return found


def parse_profile(html: str) -> Profile:
    """Parse the settings page. Missing or changed labels give ``None`` for that value.

    Raises ``FddbAuthError`` when the page shows the login link, and ``FddbParseError`` when it
    contains none of the known labels at all (not the settings page, or it changed completely).
    Only ``FddbError`` subclasses escape, as in ``parse_diary``.
    """
    try:
        return _parse_profile(html)
    except FddbError:
        raise
    except Exception as err:
        raise FddbParseError(f"Could not parse the profile page: {err!r}") from err


def _parse_profile(html: str) -> Profile:
    soup = BeautifulSoup(html, "html.parser")
    if is_logged_out(soup):
        raise FddbAuthError("Not logged in")

    found = _profile_fields(soup)
    if not found:
        raise FddbParseError("No profile data found on the settings page")

    def number(field_name: str) -> float | None:
        text = found.get(field_name)
        value = _decimal(text) if text is not None else None
        if value is None:
            _LOGGER.debug("Profile value %r missing or not a number", field_name)
        return value

    calories = _required_kcal(found["calories"]) if "calories" in found else None
    if calories is None:
        _LOGGER.debug("Profile value 'required calories per day' missing or not readable")

    def text(field_name: str) -> str | None:
        value = found.get(field_name) or None
        if value is None:
            _LOGGER.debug("Profile value %r missing", field_name)
        return value

    return Profile(
        height_cm=number("height"),
        weight_kg=number("weight"),
        bmi=number("bmi"),
        bmi_category=found.get("bmi_category"),
        occupation=text("occupation"),
        sports=text("sports"),
        goal=text("goal"),
        activity_index=number("activity"),
        calorie_goal=calories,
    )
