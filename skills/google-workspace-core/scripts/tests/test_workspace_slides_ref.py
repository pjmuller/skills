"""Slide references: pasted URLs, slide numbers and objectIds, all without touching Google."""

import pytest

from gws_core.cli import slide_target, slide_targets
from gws_core.errors import WorkspaceError
from gws_core.slides_ref import parse_slides_url, resolve_slide, slide_url

DECK = "13XeUjkBen5Tst1ZllJYqQU4dta7rHINzDZGEYxio7QY"
EDIT = f"https://docs.google.com/presentation/d/{DECK}/edit"
PRESENTATION = {"presentationId": DECK,
                "slides": [{"objectId": "p"}, {"objectId": "s_a981e2532f"},
                           {"objectId": "g3f846124570_0_183"}]}


@pytest.mark.parametrize("url, expected", [
    (f"{EDIT}?slide=id.g3f846124570_0_183#slide=id.g3f846124570_0_183", "g3f846124570_0_183"),
    (f"{EDIT}#slide=id.p12", "p12"),
    (f"{EDIT}?slide=id.p#slide=id.p", "p"),
    (f"{EDIT}#id.s_a981e2532f", "s_a981e2532f"),           # fragment without the slide= key
    (f"{EDIT}?usp=sharing&slide=id.p3", "p3"),
    (EDIT, None),                                          # deck link, no slide
])
def test_a_slides_url_yields_its_presentation_and_slide(url, expected):
    assert parse_slides_url(url) == (DECK, expected)


@pytest.mark.parametrize("value", ["g3f846124570_0_183", "70", DECK, ""])
def test_a_bare_reference_is_not_a_url(value):
    assert parse_slides_url(value) == (None, None)


def test_digits_are_slide_numbers_and_everything_else_is_an_object_id():
    assert resolve_slide(PRESENTATION, "3") == (3, "g3f846124570_0_183")
    assert resolve_slide(PRESENTATION, "s_a981e2532f") == (2, "s_a981e2532f")
    assert resolve_slide(PRESENTATION, "p") == (1, "p")  # an id that looks like a page name
    assert resolve_slide(PRESENTATION, f"{EDIT}#slide=id.s_a981e2532f") == (2, "s_a981e2532f")


def test_an_unknown_slide_says_what_the_deck_holds():
    with pytest.raises(WorkspaceError, match="out of range: this deck has 3 slides"):
        resolve_slide(PRESENTATION, "70")
    with pytest.raises(WorkspaceError, match="no slide 'gNope' in this deck"):
        resolve_slide(PRESENTATION, "gNope")


def test_slide_url_round_trips_through_the_parser():
    assert parse_slides_url(slide_url(DECK, "g3f846124570_0_183")) == (DECK, "g3f846124570_0_183")


def test_a_url_alone_carries_both_positionals():
    url = f"{EDIT}?slide=id.g3f846124570_0_183"
    assert slide_target(url, None) == (url, "g3f846124570_0_183")
    assert slide_target(DECK, "70") == (DECK, "70")
    assert slide_target(DECK, url) == (DECK, "g3f846124570_0_183")
    assert slide_targets(url, []) == ["g3f846124570_0_183"]
    assert slide_targets(DECK, ["2", "3"]) == ["2", "3"]


def test_a_deck_link_without_a_slide_asks_for_one():
    with pytest.raises(WorkspaceError, match="no slide given"):
        slide_target(EDIT, None)


def test_a_slide_url_for_another_deck_is_refused():
    other = "https://docs.google.com/presentation/d/1BBBBBBBBBBBBBBBBBBB/edit#slide=id.g1"
    with pytest.raises(WorkspaceError, match="that slide URL is for presentation"):
        slide_target(EDIT, other)
