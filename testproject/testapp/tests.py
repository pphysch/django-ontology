from django.db import IntegrityError
import ontology.models as ontology_models
import ontology_auth.models as ontology_auth_models
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db import transaction
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
def user(db):
    return ontology_auth_models.User.objects.create(username="jdoe", email="jdoe@example.com")

@pytest.fixture
def thing(db):
    return models.Thing.objects.create(slug="foobar")

@pytest.fixture
def domain(db):
    return ontology_models.Domain.objects.create(slug="mydomain")

@pytest.fixture
def broad_policy(db, domain):
    return ontology_auth_models.Policy.objects.create_from_strs(
        domain=domain,
        label="members_can_use_things",
        source_attr_strs=["role:member"],
        perm_strs=["testapp.can_use_thing"],
    )

@pytest.fixture
def narrow_policy(db, domain):
    return ontology_auth_models.Policy.objects.create_from_strs(
        domain=domain,
        label="distinguished_members_can_use_certain_things",
        source_attr_strs=["role:member", "honor:distinguished"],
        perm_strs=["testapp.can_use_thing"],
        target_attr_strs=["access:exclusive"],
    )

def test_fixtures(db, people):
    assert models.Person.objects.count() == 3


def test_attributes(db, domain, people):
    alice, bob = people["alice"], people["bob"]
    assert not alice.has_attr(domain, "mykey", "myvalue")
    alice.add_to_domain(domain)
    attr = alice.add_attr(domain, "mykey", "myvalue")
    assert alice.has_attr(domain, "mykey", "myvalue")
    qs = models.Person.objects.with_attr(domain, "mykey", "myvalue")
    assert alice in qs
    assert bob not in qs
    alice.remove_attr(domain, "mykey", "myvalue")
    assert not alice.has_attr(domain, "mykey", "myvalue")


def test_domains(db, people, domain):
    alice, bob = people["alice"], people["bob"]
    alice.add_to_domain(domain)
    assert alice.is_in_domain(domain)
    assert not bob.is_in_domain(domain)
    alice.add_attr(domain, "role", "researcher")
    with pytest.raises(ValueError):
        bob.add_attr(domain, "role", "researcher")
    assert alice.has_attr(domain, "role", "researcher")
    alice.remove_from_domain(domain)
    assert not alice.has_attr(domain, "role", "researcher")

def test_subdomains(db, people):
    alice, bob = people["alice"], people["bob"]
    myproject = ontology_models.Domain.objects.create(slug="myproject")
    mysubproject = ontology_models.Domain.objects.create(slug="myproject_subproject")
    mysubsubproject = ontology_models.Domain.objects.create(slug="myproject_subproject_subproject")
    mysubproject.add_to_domain(myproject)
    mysubsubproject.add_to_domain(mysubproject)
    assert mysubproject in mysubsubproject.superdomains()

    # no subdomain cycles allowed!
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            myproject.add_to_domain(myproject)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            myproject.add_to_domain(mysubsubproject)

    alice.add_to_domain(myproject)
    bob.add_to_domain(mysubsubproject)
    assert alice.is_in_domain(myproject)
    assert not bob.is_in_domain(myproject)
    assert bob.is_in_domain(myproject, recursive=True)


def test_entities_as_graph(db, people, places):
    graph = ontology_models.Entity.objects.as_graph()
    assert len(graph.nodes) == ontology_models.Entity.objects.count()

    # Alice's nearest relationship to the location Newtown is through her friend Chris who lives there
    assert nx.shortest_path(graph, source=people["alice"], target=places["newtown"]) == [people["alice"], people["chris"], places["newtown"]]

    # Even though Alice is Bob's "friend", her closest path to him is through her mutual friend Chris
    assert people["alice"] in people["bob"].friends.all()
    assert nx.shortest_path(graph, source=people["alice"], target=people["bob"]) == [people["alice"], people["chris"], people["bob"]]


def test_entities_as_objects(db, people):
    alice = people["alice"]
    objects = ontology_models.Entity.objects.as_objects()
    ct_person = ContentType.objects.get_for_model(models.Person)
    assert len(objects) == 2  # Two different ContentTypes, Person and Place
    assert len(objects[ct_person]) == 3  # Three people
    assert alice in objects[ct_person]


def test_simple_policy(db, user, broad_policy, thing):
    # By default, a random user should not be able to use things
    assert not user.has_perm("testapp.can_use_thing", thing)

    # ...Even if they are in the domain
    user.add_to_domain(broad_policy.domain)
    thing.add_to_domain(broad_policy.domain)
    assert not user.has_perm("testapp.can_use_thing", thing)

    # But once they have the correct attributes, they can use any thing in the domain
    attr = user.add_attr(broad_policy.domain, "role", "member")
    assert attr in broad_policy.source_attrs.all()
    assert broad_policy.entitlements.count() > 0
    assert user.has_perm("testapp.can_use_thing", thing)

    thing.remove_from_domain(broad_policy.domain)
    assert not user.has_perm("testapp.can_use_thing", thing)

    thing.add_to_domain(broad_policy.domain)
    assert user.has_perm("testapp.can_use_thing", thing)




def test_complex_policy(db, user, narrow_policy, thing):
    # By default, a random user should not be able to use the thing
    assert not user.has_perm("testapp.can_use_thing", thing)

    # Nor even if they are both in the same domain
    user.add_to_domain(narrow_policy.domain)
    thing.add_to_domain(narrow_policy.domain)
    assert not user.has_perm("testapp.can_use_thing", thing)

    # Nor even if they both have some of the correct attributes
    attr_member = user.add_attr(narrow_policy.domain, "role", "member")
    thing.add_attr(narrow_policy.domain, "access", "exclusive")
    assert not user.has_perm("testapp.can_use_thing", thing)

    # Finally, the user has both required attributes
    user.add_attr(narrow_policy.domain, "honor", "distinguished")    
    assert user.has_perm("testapp.can_use_thing", thing)

    # The user stops being a member, and should lose access according to the policy even if we don't remove their honors.
    user.remove_attr(narrow_policy.domain, "role", "member")
    assert not user.has_perm("testapp.can_use_thing", thing)

    # Test reverse attr add
    attr_member.entities.add(user.entity)
    assert user.has_perm("testapp.can_use_thing", thing)