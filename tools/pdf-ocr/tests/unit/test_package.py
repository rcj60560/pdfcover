def test_can_import_convert_folder():
    """Test that convert_folder can be imported."""
    from pdfcover import convert_folder
    assert callable(convert_folder)


def test_version_defined():
    """Test that __version__ is defined."""
    from pdfcover import __version__
    assert __version__ == "0.1.0"
