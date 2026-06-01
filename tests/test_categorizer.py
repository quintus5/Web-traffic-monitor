import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proxy.categorizer import Categorizer


def make_cat():
    c = Categorizer(db=None)  # loads from categories.json
    return c


def test_exact_match():
    cat = make_cat()
    result = cat.categorize("x.com")
    assert result is not None
    assert result["name"] == "social"


def test_suffix_match():
    cat = make_cat()
    result = cat.categorize("www.youtube.com")
    assert result is not None
    assert result["name"] == "video_streaming"


def test_subdomain_suffix():
    cat = make_cat()
    result = cat.categorize("m.facebook.com")
    assert result is not None
    assert result["name"] == "social"


def test_unknown_domain():
    cat = make_cat()
    result = cat.categorize("completely-unknown-domain-xyz.io")
    assert result is None


def test_work_tool():
    cat = make_cat()
    result = cat.categorize("slack.com")
    assert result["name"] == "work_tools"


def test_case_insensitive():
    cat = make_cat()
    result = cat.categorize("YouTube.COM")
    assert result is not None
    assert result["name"] == "video_streaming"
