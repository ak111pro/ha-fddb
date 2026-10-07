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

    @property
    def has_entries(self) -> bool:
        return bool(self.products) or self.calories > 0

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
    link = cells[0].find("a")
    if link is None:
        raise FddbParseError("Product row without a link")
    text = link.get_text(" ", strip=True)
    match = _AMOUNT.match(text)
    amount, name = (match.group(1), match.group(2)) if match else (None, text)
    time_span = cells[0].select_one("span.mydayshowtime")
    return Product(
        name=name.strip(),
        amount=amount,
        calories=_cell_value(cells[2]),
        fat=_cell_value(cells[3]),
        carbs=_cell_value(cells[4]),
        protein=_cell_value(cells[5]),
        link=link.get("href"),
        time=time_span.get_text(strip=True) if time_span else None,
    )


def _labelled_value(soup: BeautifulSoup, label: re.Pattern[str]) -> float:
    for row in soup.select("table:not(.myday-table-std) tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) >= 2 and label.fullmatch(cells[0].get_text(" ", strip=True)):
            return _cell_value(cells[1])
    raise FddbParseError(f"Row {label.pattern!r} not found")


def parse_diary(html: str, day: date) -> DiaryDay:
    """Parse a diary page. Returns an empty DiaryDay if nothing was logged that day."""
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

    return DiaryDay(
        day=day,
        calories=_cell_value(footer_cells[2]),
        fat=_cell_value(footer_cells[3]),
        carbs=_cell_value(footer_cells[4]),
        protein=_cell_value(footer_cells[5]),
        sugar=_labelled_value(soup, _SUGAR),
        fibre=_labelled_value(soup, _FIBRE),
        products=products,
    )
