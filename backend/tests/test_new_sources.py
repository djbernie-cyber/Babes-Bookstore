"""Tests for the new source adapters (registry-gated, no network)."""
import pytest


def test_wikibooks_parse_maps_titles():
    from app.sources.wikibooks import WikibooksSource
    src = WikibooksSource()
    book = src._parse("OpenSCAD User Manual")
    assert book is not None
    assert book.title == "OpenSCAD User Manual"
    assert book.source_id == "OpenSCAD_User_Manual"
    assert book.source == "wikibooks"
    assert book.license_type == "cc_by_sa_4.0"
    assert "Teaching & Education" in book.tags


def test_wikibooks_parse_drops_subpages_and_meta():
    from app.sources.wikibooks import WikibooksSource
    src = WikibooksSource()
    assert src._parse("Book/Chapter 1") is None
    assert src._parse("Wikibooks:Sandbox") is None
    assert src._parse("Help:Contents") is None
    assert src._parse("Cookbook/Recipe") is None


def test_biodiversity_maps_top_titles():
    from app.sources.biodiversity import BiodiversitySource
    src = BiodiversitySource()
    book = src._parse("12345", "Birds of the World")
    assert book is not None
    assert book.title == "Birds of the World"
    assert book.source_id == "12345"
    assert book.source == "biodiversity"
    assert book.license_type == "public_domain"


def test_biodiversity_requires_api_key():
    from app.sources.biodiversity import BiodiversitySource
    assert BiodiversitySource.requires_api_key is True


def test_new_sources_are_registered():
    from app.sources.registry import source_registry
    assert "wikibooks" in source_registry
    assert "biodiversity" in source_registry
    info = source_registry.describe()
    assert info["wikibooks"]["license_type"] == "cc_by_sa_4.0"
    assert info["biodiversity"]["requires_api_key"] is True