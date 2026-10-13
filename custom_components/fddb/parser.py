"""Parse FDDB diary pages (no Home Assistant imports, so it can be tested on its own)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import re

from bs4 import BeautifulSoup, Tag


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
    # The daily calorie goal the page shows, or None when the page has none (or the integration
    # cannot read it yet, see GOAL_LABEL). Kept out of as_dict(): it is account state, not a
    # property of the day, and the get_diary action response should stay unchanged.
    calorie_goal: float | None = None

    @property
    def has_entries(self) -> bool:
        return bool(self.products) or self.calories > 0

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
        data.pop("calorie_goal")
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

# Label of the row (in the English diary page) that holds the daily calorie goal.
#
# ASSUMPTION / NOT CONFIRMED: none of the saved diary pages (the synthetic fixtures here and the
# real pages in itobey/fddb-exporter's tests) contains a goal anywhere, so the real label and
# position are unknown. Until a real page that shows the goal is available this stays None and
# the goal is never read; the rest of the goal handling (override logic, sensor) is in place and
# tested with synthetic HTML. To enable it, set this to a ``re.Pattern`` that matches the whole
# text of the first cell of the goal row, e.g. ``re.compile(r"daily\s+goal", re.IGNORECASE)``.
GOAL_LABEL: re.Pattern[str] | None = None


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


def _calorie_goal(soup: BeautifulSoup, label: re.Pattern[str] | None) -> float | None:
    """The daily calorie goal from the row with ``label``, None if unknown or not shown.

    A goal is only a goal if it is positive; "0" or an unreadable value means "no goal".
    """
    if label is None:
        return None
    try:
        value = _labelled_value(soup, label)
    except FddbParseError:
        return None
    return value if value > 0 else None


def parse_diary(html: str, day: date, goal_label: re.Pattern[str] | None = None) -> DiaryDay:
    """Parse a diary page. Returns an empty DiaryDay if nothing was logged that day.

    Only ``FddbError`` subclasses escape: an unexpected failure inside the parser (a changed page
    layout can trip almost anything) is reported as ``FddbParseError`` so callers can treat it
    like any other "website changed" problem instead of crashing.
    """
    try:
        return _parse_diary(html, day, GOAL_LABEL if goal_label is None else goal_label)
    except FddbError:
        raise
    except Exception as err:
        raise FddbParseError(f"Could not parse the diary page: {err!r}") from err


def _parse_diary(html: str, day: date, goal_label: re.Pattern[str] | None) -> DiaryDay:
    soup = BeautifulSoup(html, "html.parser")
    if is_logged_out(soup):
        raise FddbAuthError("Not logged in")

    goal = _calorie_goal(soup, goal_label)

    table = soup.select_one("table.myday-table-std")
    if table is None:
        return DiaryDay(day=day, calorie_goal=goal)

    rows = [r for r in table.find_all("tr") if r.find_all("td", recursive=False)]
    if not rows:
        return DiaryDay(day=day, calorie_goal=goal)

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

    return DiaryDay(
        day=day,
        calories=_cell_value(footer_cells[2]),
        fat=_cell_value(footer_cells[3]),
        carbs=_cell_value(footer_cells[4]),
        protein=_cell_value(footer_cells[5]),
        sugar=_labelled_value(soup, _SUGAR),
        fibre=_labelled_value(soup, _FIBRE),
        products=products,
        calorie_goal=goal,
    )
