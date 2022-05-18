from django.test import TestCase
import ontology.models as ontology_models
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from . import models
import pytest
import networkx as nx

# Create your tests here.

@pytest.fixture
def places(db):
    nacirema = models.Place.objects.create(slug="Nacirema")
    fredonia = models.Place.objects.create(slug="Fredonia", parent=nacirema)
    springville = models.Place.objects.create(slug="Springville", parent=fredonia)
    newtown = models.Place.objects.create(slug="Newtown", parent=fredonia)

    return {
        "nacirema": nacirema,
        "fredonia": fredonia,
        "springville": springville,
        "newtown": newtown,
    }

@pytest.fixture
def people(db, places):
    alice = models.Person.objects.create(slug="Alice", location=places["springville"])
    bob = models.Person.objects.create(slug="Bob", location=places["springville"])
    chris = models.Person.objects.create(slug="Chris", location=places["newtown"])

    alice.friends.add(chris)
    bob.friends.add(alice, chris)
    chris.friends.add(alice, bob)

    return {
        "alice": alice,
        "bob": bob,
        "chris": chris,
    }

@pytest.fixture
def bank_policy(db, people):
    tag_manager = people["alice"].add_tag("role:account_manager")
    tag_janitor = people["bob"].add_tag("role:janitor")

    ba = models.Thing.objects.create(slug="bank_account")
    tag_restricted = ba.add_tag("access:restricted")

    action_access_account = ontology_models.Action.objects.from_objects(people["alice"], "access", ba, may_create=True)

    policy = ontology_models.Policy.objects.create(name="Bank account access policy", description="Allow account managers to access restricted accounts")
    policy.subject_tags.add(tag_manager)
    policy.actions.add(action_access_account)
    policy.target_tags.add(tag_restricted)

    return {"policy": policy, "account": ba}


def test_fixtures(db, people):
    assert models.Person.objects.count() == 3


def test_entities_as_graph(db, people, places):
    graph = ontology_models.Entity.objects.as_graph()
    assert len(graph.nodes) == ontology_models.Entity.objects.count()

    # Alice's nearest relationship to the location Newtown is through her friend Chris who lives there
    assert nx.shortest_path(graph, source=people["alice"], target=places["newtown"]) == [people["alice"], people["chris"], places["newtown"]]

    # Even though Alice is Bob's "friend", her closest path to him is through her mutual friend Chris
    assert people["alice"] in people["bob"].friends.all()
    assert nx.shortest_path(graph, source=people["alice"], target=people["bob"]) == [people["alice"], people["chris"], people["bob"]]


def test_entities_as_objects(db, people):
    objects = ontology_models.Entity.objects.as_objects()
    ct_person = ContentType.objects.get_for_model(models.Person)
    assert len(objects) == 2  # Two different ContentTypes, Person and Place
    assert len(objects[ct_person]) == 3  # Three people
    assert people["alice"] in objects[ct_person]


def test_basic_policy(db, people, bank_policy):
    bank_account = bank_policy["account"]

    # The account manager can access the account, but the janitor cannot
    assert people["alice"].has_permission("access", bank_account) == True
    assert people["bob"].has_permission("access", bank_account) == False

    # Alice retires from the bank and loses account access
    people["alice"].remove_tag("role:account_manager")
    assert people["alice"].has_permission("access", bank_account) == False

    # Bob is promoted to account manager and gains access
    people["bob"].add_tag("role:account_manager")
    assert people["bob"].has_permission("access", bank_account) == True

    # The bank closes down and terminates account access
    bank_policy["policy"].expiration_time = timezone.now()
    bank_policy["policy"].save()
    assert people["bob"].has_permission("access", bank_account) == False