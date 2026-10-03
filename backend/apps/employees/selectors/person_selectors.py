"""Person queries. Persons are reached through their employee's scope (``apps.employees.scope``)."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import Http404

from ..models import Person, PersonRelationship
from ..scope import can_access_person


def get_person(user: Any, pk: Any) -> Person:
    person = Person.objects.filter(pk=pk).first()
    if person is None or not can_access_person(user, person):
        raise Http404("Person not found.")
    return person


def get_person_relationships(person: Person) -> QuerySet[PersonRelationship]:
    return PersonRelationship.objects.filter(from_person=person).select_related("to_person")
