from zenie_code.branding import banner


def test_banner_contains_name():
    assert "C  O  D  E" in banner("1.1.0")
