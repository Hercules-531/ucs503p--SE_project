"""Maintain and query scheme metadata indexes without persisting user searches."""

import json
from dataclasses import dataclass

from sqlalchemy import Select, Text, cast, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import Scheme
from app.storage import SchemeFilterValue, SchemeIndex, StoredRecord


@dataclass
class CatalogueFacets:
    record_count: int
    categories: list[str]
    states: list[str]
    audiences: list[str]


def catalogue_facets(session: Session) -> CatalogueFacets:
    """Read distinct filter labels without loading source and eligibility payloads."""
    categories: set[str] = set()
    states: set[str] = set()
    audiences: set[str] = set()
    query = (
        select(
            StoredRecord.payload["category"].as_string(),
            cast(StoredRecord.payload["states"], Text),
            cast(StoredRecord.payload["audiences"], Text),
        )
        .where(StoredRecord.kind == "scheme")
        .distinct()
    )
    for category, state_json, audience_json in session.execute(query):
        if category:
            categories.add(category)
        # Older payloads without states use the same nationwide default as Scheme.
        states.update(json.loads(state_json) if state_json not in (None, "null") else ["All India"])
        if audience_json not in (None, "null"):
            audiences.update(json.loads(audience_json))
    count = session.scalar(
        select(func.count()).select_from(StoredRecord).where(StoredRecord.kind == "scheme")
    )
    return CatalogueFacets(count, sorted(categories), sorted(states), sorted(audiences))


def searchable_text(scheme: Scheme) -> str:
    return " ".join(
        [scheme.name, scheme.short_name, scheme.ministry, scheme.summary, *scheme.tags]
    ).casefold()


def update_scheme_index(session: Session, schemes: list[Scheme]) -> None:
    if not schemes:
        return
    identifiers = [scheme.id for scheme in schemes]
    existing = {
        entry.identifier: entry
        for entry in session.scalars(
            select(SchemeIndex).where(SchemeIndex.identifier.in_(identifiers))
        )
    }
    session.execute(delete(SchemeFilterValue).where(SchemeFilterValue.identifier.in_(identifiers)))
    for scheme in schemes:
        entry = existing.get(scheme.id)
        if entry is None:
            entry = SchemeIndex(identifier=scheme.id)
            session.add(entry)
        entry.slug = scheme.slug
        entry.category_key = scheme.category.casefold()
        entry.searchable = searchable_text(scheme)
    session.flush()
    for scheme in schemes:
        attributes = {("state", state.casefold()) for state in scheme.states}
        attributes.update(("audience", audience.casefold()) for audience in scheme.audiences)
        session.add_all(
            SchemeFilterValue(identifier=scheme.id, attribute=kind, value=value)
            for kind, value in attributes
        )


def scheme_search_query(
    *,
    q: str = "",
    category: str = "",
    state: str = "",
    audience: str = "",
    include_unknown: bool = False,
) -> Select:
    query = (
        select(StoredRecord.payload)
        .join(SchemeIndex, SchemeIndex.identifier == StoredRecord.identifier)
        .where(StoredRecord.kind == "scheme")
    )
    if key := q.strip().casefold():
        query = query.where(SchemeIndex.searchable.contains(key, autoescape=True))
    if key := category.strip().casefold():
        query = query.where(SchemeIndex.category_key == key)
    if key := state.strip().casefold():
        matches = exists().where(
            SchemeFilterValue.identifier == SchemeIndex.identifier,
            SchemeFilterValue.attribute == "state",
            or_(SchemeFilterValue.value == key, SchemeFilterValue.value == "all india"),
        )
        present = exists().where(
            SchemeFilterValue.identifier == SchemeIndex.identifier,
            SchemeFilterValue.attribute == "state",
        )
        query = query.where(or_(matches, ~present) if include_unknown else matches)
    if key := audience.strip().casefold():
        matches = exists().where(
            SchemeFilterValue.identifier == SchemeIndex.identifier,
            SchemeFilterValue.attribute == "audience",
            SchemeFilterValue.value == key,
        )
        present = exists().where(
            SchemeFilterValue.identifier == SchemeIndex.identifier,
            SchemeFilterValue.attribute == "audience",
        )
        query = query.where(or_(matches, ~present) if include_unknown else matches)
    return query


def indexed_schemes(
    session: Session,
    *,
    q: str = "",
    category: str = "",
    state: str = "",
    audience: str = "",
    include_unknown: bool = False,
) -> list[Scheme]:
    query = scheme_search_query(
        q=q, category=category, state=state, audience=audience, include_unknown=include_unknown
    )
    return [
        Scheme.model_validate(payload)
        for payload in session.scalars(query.order_by(StoredRecord.identifier))
    ]


def indexed_scheme_page(
    session: Session,
    *,
    limit: int,
    offset: int,
    q: str = "",
    category: str = "",
    state: str = "",
    audience: str = "",
    include_unknown: bool = False,
) -> tuple[list[Scheme], int]:
    query = scheme_search_query(
        q=q, category=category, state=state, audience=audience, include_unknown=include_unknown
    )
    total = session.scalar(query.with_only_columns(func.count())) or 0
    payloads = session.scalars(query.order_by(StoredRecord.identifier).limit(limit).offset(offset))
    return [Scheme.model_validate(payload) for payload in payloads], total


def indexed_uncertain_exclusions(
    session: Session, *, q: str = "", category: str = "", state: str = "", audience: str = ""
) -> int:
    """Count records that could match but lack a selected state or audience field."""
    state_key, audience_key = state.strip().casefold(), audience.strip().casefold()
    unknown_fields = []
    possible_conditions = []
    for attribute, key in (("state", state_key), ("audience", audience_key)):
        if not key:
            continue
        present = exists().where(
            SchemeFilterValue.identifier == SchemeIndex.identifier,
            SchemeFilterValue.attribute == attribute,
        )
        values = [key, "all india"] if attribute == "state" else [key]
        matches = exists().where(
            SchemeFilterValue.identifier == SchemeIndex.identifier,
            SchemeFilterValue.attribute == attribute,
            SchemeFilterValue.value.in_(values),
        )
        unknown_fields.append(~present)
        possible_conditions.append(or_(~present, matches))
    if not unknown_fields:
        return 0
    query = scheme_search_query(q=q, category=category).where(
        *possible_conditions, or_(*unknown_fields)
    )
    return session.scalar(query.with_only_columns(func.count())) or 0
