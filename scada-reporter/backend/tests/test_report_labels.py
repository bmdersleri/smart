from app.i18n import get_labels


def test_english_labels():
    labels = get_labels("en")
    assert labels["summary_sheet"] == "Summary"
    assert labels["total_reads"] == "Total Reads"


def test_turkish_labels():
    labels = get_labels("tr")
    assert labels["summary_sheet"] == "Özet"
    assert labels["total_reads"] == "Toplam Okuma"


def test_unknown_language_falls_back_to_english():
    assert get_labels("xx") == get_labels("en")


def test_all_languages_have_same_keys():
    en_keys = set(get_labels("en").keys())
    for lang in ("tr", "ru", "de", "ar"):
        assert set(get_labels(lang).keys()) == en_keys, f"{lang} key mismatch"


def test_arabic_labels():
    labels = get_labels("ar")
    assert labels["summary_sheet"] == "ملخص"
    assert labels["total_reads"] == "إجمالي القراءات"
