import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

import app.main as web
from app.data import SCHEMES


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web, "engine", None)
    return TestClient(web.app)


def test_comparison_uses_two_catalogue_records_and_their_sources(client):
    first, second = SCHEMES[:2]
    detail = client.get(f"/schemes/{first.slug}")
    assert f'/compare?scheme={first.slug}"' in detail.text
    prefilled = client.get("/compare", params={"scheme": first.slug})
    assert prefilled.status_code == 200
    assert f'value="{first.slug}" selected' in prefilled.text
    assert 'aria-label="Scheme comparison table"' not in prefilled.text

    response = client.get("/compare", params=[("scheme", second.slug), ("scheme", first.slug)])
    table = response.text.split("<table", 1)[1]
    assert response.status_code == 200
    assert table.index(second.name) < table.index(first.name)
    for scheme in (first, second):
        assert str(scheme.source.url) in unescape(table)
        assert scheme.source.last_verified.isoformat() in table
        assert scheme.benefit_summary in unescape(table)
    assert "Eligibility guidance" in table


@pytest.mark.parametrize(
    "slugs",
    [
        ["pm-kisan", "pm-kisan"],
        ["pm-kisan", "missing"],
        ["pm-kisan", "ayushman-bharat-pm-jay", "atal-pension-yojana"],
    ],
)
def test_comparison_rejects_invalid_selections(client, slugs):
    response = client.get("/compare", params=[("scheme", slug) for slug in slugs])
    assert response.status_code == 422
    assert "Choose two different schemes from the catalogue" in response.text
    assert 'aria-label="Scheme comparison table"' not in response.text


def test_demo_uses_working_examples_from_the_loaded_catalogue(client):
    page = client.get("/demo")
    assert page.status_code == 200
    assert 'href="/demo" aria-current="page"' in page.text
    assert 'href="/diagrams/index.html"' in page.text
    comparison = unescape(re.search(r'href="(/compare\?[^\"]+)"', page.text)[1])
    assert "Side-by-side results" in client.get(comparison).text
    assert 'href="/locations?pincode=147004"' in page.text
    assert "Thapar College Patiala S.O" in client.get("/locations?pincode=147004").text
    assert 'href="/developers?endpoint=scheme&amp;id=scheme-pm-jay"' in page.text
    headers = {"X-API-Key": web.DEMO_API_KEY}
    response = client.get("/api/v1/schemes/scheme-pm-jay", headers=headers)
    assert response.status_code == 200 and response.json()["data"]["id"] == "scheme-pm-jay"


def test_demo_handles_a_custom_empty_catalogue(client, monkeypatch):
    monkeypatch.setattr(web, "current_schemes", lambda: [])
    monkeypatch.setattr(web, "current_location", lambda pincode: None)
    demo = client.get("/demo")
    assert demo.status_code == 200
    assert 'href="/compare"' in demo.text
    assert 'href="/locations"' in demo.text
    assert 'href="/developers"' in demo.text
    assert "The catalogue needs at least two schemes" in client.get("/compare").text
