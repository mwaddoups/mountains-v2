import datetime
import re
import unicodedata


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None)


def readable_id(values: list[str]) -> str:
    return slugify(" ".join(v[:15].lower() for v in values))


def slugify(value: str) -> str:
    """
    Converts to lowercase, removes non-word characters (alphanumerics and
    underscores) and converts spaces to hyphens. Also strips leading and
    trailing whitespace.
    """
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)
