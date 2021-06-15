import time

import pytest

from sentry import eventstore
from sentry.models import Group, GroupHash
from sentry.testutils.helpers import Feature


@pytest.fixture(autouse=True)
def hierarchical_grouping_features():
    with Feature({"organizations:grouping-tree-ui": True}):
        yield


@pytest.fixture(autouse=True)
def auto_login(settings, client, default_user):
    assert client.login(username=default_user.username, password="admin")


def _reload_event(event):
    return eventstore.get_event_by_id(event.project_id, event.event_id)


@pytest.fixture
def store_stacktrace(default_project, factories):
    default_project.update_option("sentry:grouping_config", "mobile:2021-02-12")

    timestamp = time.time() - 3600

    def inner(functions):
        nonlocal timestamp

        timestamp += 1

        event = {
            "timestamp": timestamp,
            "exception": {
                "values": [
                    {
                        "type": "ZeroDivisionError",
                        "stacktrace": {"frames": [{"function": f} for f in functions]},
                    }
                ]
            },
        }

        return factories.store_event(data=event, project_id=default_project.id)

    return inner


@pytest.fixture
def _render_all_previews(client):
    def inner(group: Group):
        rv = []

        response = client.get(f"/api/0/issues/{group.id}/grouping/levels/", format="json")
        assert response.status_code == 200

        for level in response.data["levels"]:
            rv.append(f"level {level['id']}{level.get('isCurrent') and '*' or ''}")

            response = client.get(
                f"/api/0/issues/{group.id}/grouping/levels/{level['id']}/new-issues/", format="json"
            )

            assert response.status_code == 200

            rv.extend(f"{preview['hash']} ({preview['eventCount']})" for preview in response.data)

        return "\n".join(rv)

    return inner


@pytest.mark.django_db
@pytest.mark.snuba
def test_error_conditions(client, default_project, reset_snuba, factories):
    group = Group.objects.create(project=default_project)
    grouphash = GroupHash.objects.create(
        project=default_project, group=group, hash="d41d8cd98f00b204e9800998ecf8427e"
    )

    with Feature({"organizations:grouping-tree-ui": False}):
        response = client.get(f"/api/0/issues/{group.id}/grouping/levels/", format="json")
        assert response.status_code == 403
        assert response.data["detail"]["code"] == "missing_feature"

    response = client.get(f"/api/0/issues/{group.id}/grouping/levels/", format="json")
    assert response.status_code == 403
    assert response.data["detail"]["code"] == "no_events"

    factories.store_event(
        data={"message": "hello world", "checksum": grouphash.hash}, project_id=default_project.id
    )

    response = client.get(f"/api/0/issues/{group.id}/grouping/levels/", format="json")
    assert response.status_code == 403
    assert response.data["detail"]["code"] == "not_hierarchical"


@pytest.mark.django_db
@pytest.mark.snuba
def test_downwards(default_project, store_stacktrace, reset_snuba, _render_all_previews):
    events = [
        # store events with a common crashing frame `foo` and diverging threadbases
        store_stacktrace(["bam", "baz2", "bar2", "foo"]),
        store_stacktrace(["baz", "bar", "foo"]),
        store_stacktrace(["baz2", "bar2", "foo"]),
        store_stacktrace(["bar3", "foo"]),
    ]

    assert len({e.group_id for e in events}) == 1
    group = events[0].group

    assert (
        _render_all_previews(group)
        == """\
level 0*
bab925683e73afdb4dc4047397a7b36b (4)
level 1
64686dcd59e0cf97f34113e9d360541a (1)
c8ef2dd3dedeed29b4b74b9c579eea1a (2)
aa1c4037371150958f9ea22adb110bbc (1)
level 2
64686dcd59e0cf97f34113e9d360541a (1)
8c0bbfebc194c7aa3e77e95436fd61e5 (2)
b8d08a573c62ca8c84de14c12c0e19fe (1)
level 3
64686dcd59e0cf97f34113e9d360541a (1)
8c0bbfebc194c7aa3e77e95436fd61e5 (1)
b8d08a573c62ca8c84de14c12c0e19fe (1)
b0505d7461a2e36c4a8235bb6c310a3b (1)\
"""
    )


@pytest.mark.django_db
@pytest.mark.snuba
def test_upwards(default_project, store_stacktrace, reset_snuba, _render_all_previews):
    GroupHash.objects.create(
        project_id=default_project.id,
        hash="c8ef2dd3dedeed29b4b74b9c579eea1a",
        state=GroupHash.State.SPLIT,
        group_id=None,
    )

    GroupHash.objects.create(
        project_id=default_project.id,
        hash="aa1c4037371150958f9ea22adb110bbc",
        state=GroupHash.State.SPLIT,
        group_id=None,
    )

    events = [
        store_stacktrace(["baz", "bar2", "foo"]),
        store_stacktrace(["baz", "bar", "foo"]),
        store_stacktrace(["bam", "bar", "foo"]),
    ]

    assert len({e.group_id for e in events}) == 3

    assert (
        _render_all_previews(events[0].group)
        == """\
level 0
bab925683e73afdb4dc4047397a7b36b (3)
level 1
c8ef2dd3dedeed29b4b74b9c579eea1a (1)
level 2*
7411b56aa6591edbdba71898d3a9f01c (1)\
"""
    )
    assert (
        _render_all_previews(events[1].group)
        == """\
level 0
bab925683e73afdb4dc4047397a7b36b (3)
level 1
aa1c4037371150958f9ea22adb110bbc (2)
level 2*
b8d08a573c62ca8c84de14c12c0e19fe (1)\
"""
    )

    assert (
        _render_all_previews(events[2].group)
        == """\
level 0
bab925683e73afdb4dc4047397a7b36b (3)
level 1
aa1c4037371150958f9ea22adb110bbc (2)
level 2*
97df6b60ec530c65ab227585143a087a (1)\
"""
    )


@pytest.mark.django_db
@pytest.mark.snuba
def test_increase(
    client, default_project, store_stacktrace, reset_snuba, _render_all_previews, task_runner
):
    events = [
        store_stacktrace(["baz", "bar2", "foo"]),
        store_stacktrace(["baz", "bar", "foo"]),
        store_stacktrace(["bam", "bar", "foo"]),
    ]

    assert len({e.group_id for e in events}) == 1

    old_group = events[0].group

    assert (
        _render_all_previews(old_group)
        == """\
level 0*
bab925683e73afdb4dc4047397a7b36b (3)
level 1
aa1c4037371150958f9ea22adb110bbc (2)
c8ef2dd3dedeed29b4b74b9c579eea1a (1)
level 2
97df6b60ec530c65ab227585143a087a (1)
b8d08a573c62ca8c84de14c12c0e19fe (1)
7411b56aa6591edbdba71898d3a9f01c (1)\
"""
    )

    with task_runner():
        response = client.post(f"/api/0/issues/{events[0].group_id}/grouping/levels/2/")
        assert response.status_code == 200

    events = [_reload_event(event) for event in events]
    assert len({e.group_id for e in events}) == 3

    assert (
        _render_all_previews(events[0].group)
        == """\
level 0
bab925683e73afdb4dc4047397a7b36b (3)
level 1
c8ef2dd3dedeed29b4b74b9c579eea1a (1)
level 2*
7411b56aa6591edbdba71898d3a9f01c (1)\
"""
    )
    assert (
        _render_all_previews(events[1].group)
        == """\
level 0
bab925683e73afdb4dc4047397a7b36b (3)
level 1
aa1c4037371150958f9ea22adb110bbc (2)
level 2*
b8d08a573c62ca8c84de14c12c0e19fe (1)\
"""
    )

    assert (
        _render_all_previews(events[2].group)
        == """\
level 0
bab925683e73afdb4dc4047397a7b36b (3)
level 1
aa1c4037371150958f9ea22adb110bbc (2)
level 2*
97df6b60ec530c65ab227585143a087a (1)\
"""
    )


@pytest.mark.django_db
@pytest.mark.snuba
def test_decrease(
    client, default_project, store_stacktrace, reset_snuba, _render_all_previews, task_runner
):
    for split_hash in (
        "bab925683e73afdb4dc4047397a7b36b",
        "c8ef2dd3dedeed29b4b74b9c579eea1a",
        "aa1c4037371150958f9ea22adb110bbc",
    ):
        GroupHash.objects.create(
            project_id=default_project.id,
            hash=split_hash,
            state=GroupHash.State.SPLIT,
            group_id=None,
        )

    events = [
        store_stacktrace(["baz", "bar2", "foo"]),
        store_stacktrace(["baz", "bar", "foo"]),
        store_stacktrace(["bam", "bar", "foo"]),
    ]

    assert len({e.group_id for e in events}) == 3

    with task_runner():
        response = client.post(f"/api/0/issues/{events[0].group_id}/grouping/levels/0/")
        assert response.status_code == 200

    events = [_reload_event(event) for event in events]
    assert len({e.group_id for e in events}) == 1

    assert (
        _render_all_previews(events[0].group)
        == """\
level 0*
bab925683e73afdb4dc4047397a7b36b (3)
level 1
aa1c4037371150958f9ea22adb110bbc (2)
c8ef2dd3dedeed29b4b74b9c579eea1a (1)
level 2
97df6b60ec530c65ab227585143a087a (1)
b8d08a573c62ca8c84de14c12c0e19fe (1)
7411b56aa6591edbdba71898d3a9f01c (1)\
"""
    )

    assert set(GroupHash.objects.all().values_list("hash", "state", "group_id")) == {
        # Old levels
        ("7411b56aa6591edbdba71898d3a9f01c", None, None),
        ("b8d08a573c62ca8c84de14c12c0e19fe", None, None),
        ("97df6b60ec530c65ab227585143a087a", None, None),
        ("aa1c4037371150958f9ea22adb110bbc", None, None),
        ("c8ef2dd3dedeed29b4b74b9c579eea1a", None, None),
        # Our newly created group
        ("bab925683e73afdb4dc4047397a7b36b", None, events[0].group_id),
    }
