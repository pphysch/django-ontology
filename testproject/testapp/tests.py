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
def person_user(db, user):
    return models.Person.objects.create(entity=user.entity, slug="john_doe")

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


def test_entity_lifecycle(db, thing):
    assert thing in models.Thing.objects.all()

    # soft-delete by default; still available in the archive Manager
    thing.delete()
    assert thing in models.Thing.objects_archive.all()
    assert thing not in models.Thing.objects.all()

    # soft-delete can be reversed (via Manager)
    models.Thing.objects_archive.undelete()
    assert thing in models.Thing.objects.all()

    # can also soft-delete a queryset
    models.Thing.objects.delete()
    assert thing in models.Thing.objects_archive.all()
    assert thing not in models.Thing.objects.all()

    # hard-delete will permanently remove it from the database
    models.Thing.objects_archive.delete(hard_delete=True)
    assert thing not in models.Thing.objects_archive.all()
    with pytest.raises(ontology_models.Entity.DoesNotExist):
        ontology_models.Entity.objects_archive.get(pk=thing.entity_id)


def test_entity_composition(db, person_user):
    # person_user is a Person component with a peer User component
    entity = person_user.entity
    user = person_user.cast(ontology_auth_models.User)
    assert user.username == "jdoe"
    assert person_user.entity == user.entity
    assert entity.content_types.count() == 2

    # We can cleanly remove the User component without affecting the Person or Entity
    user.delete(isolated=True, hard_delete=True)
    assert entity.content_types.count() == 1
    with pytest.raises(ontology_auth_models.User.DoesNotExist):
        with transaction.atomic():
            person_user.cast(ontology_auth_models.User)

    # We can readd a User component by specifying the PK entity
    user = ontology_auth_models.User.objects.create(entity=person_user.entity, username="jdoe", email="jdoe@example.com")
    assert entity.content_types.count() == 2
    assert user == person_user.cast(ontology_auth_models.User)

    # We can't add a second User component due to User PK conflict
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ontology_auth_models.User.objects.create(entity=person_user.entity, username="jdoe2", email="jdoe2@example.com")

    # We can also soft-delete the User, which will maintain its references but prevent it from showing up in normal queries
    user.delete(isolated=True, hard_delete=False)
    assert ontology_auth_models.User.objects_archive.count() == 1
    assert ontology_auth_models.User.objects.count() == 0
    assert entity.content_types.count() == 2
    with pytest.raises(ontology_auth_models.User.DoesNotExist):
        with transaction.atomic():
            person_user.cast(ontology_auth_models.User)

    # If we hard-delete the Person Component, the associated User Component is also permanently deleted.
    person_user.delete(hard_delete=True)
    assert ontology_auth_models.User.objects_archive.count() == 0


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

    # subdomain cycles are automatically prevented
    myproject.add_to_domain(myproject)
    assert not myproject.is_in_domain(myproject)
    myproject.add_to_domain(mysubsubproject)
    assert not myproject.is_in_domain(mysubsubproject)

    alice.add_to_domain(myproject)
    bob.add_to_domain(mysubsubproject)
    assert alice.is_in_domain(myproject)
    assert not bob.is_in_domain(myproject)
    assert bob.is_in_domain(myproject, recursive=True)


@pytest.mark.skip(reason="Must reimplement as_graph()")
def test_entities_as_graph(db, people, places):
    graph = ontology_models.Entity.objects.as_graph()
    assert len(graph.nodes) == ontology_models.Entity.objects.count()

    # Alice's nearest relationship to the location Newtown is through her friend Chris who lives there
    assert nx.shortest_path(graph, source=people["alice"], target=places["newtown"]) == [people["alice"], people["chris"], places["newtown"]]

    # Even though Alice is Bob's "friend", her closest path to him is through her mutual friend Chris
    assert people["alice"] in people["bob"].friends.all()
    assert nx.shortest_path(graph, source=people["alice"], target=people["bob"]) == [people["alice"], people["chris"], people["bob"]]


def test_entities_by_model(db, people):
    alice = people["alice"]
    objects = ontology_models.Entity.objects.by_model()
    assert len(objects) == 2  # Two different ContentTypes, Person and Place
    assert len(objects[models.Person]) == 3  # Three people
    assert alice in objects[models.Person]


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