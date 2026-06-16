from app.i18n.report_labels import LABELS

DEFAULT_LANG = "en"


def get_labels(lang: str) -> dict[str, str]:
    """Return the report label dict for `lang`, falling back to English."""
    return LABELS.get(lang, LABELS[DEFAULT_LANG])
