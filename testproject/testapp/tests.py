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
