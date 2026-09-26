"""Migration-graph guards.

The container runs `alembic upgrade head` before uvicorn starts. With more
than one head, that command aborts, the app never binds its port, and Fly
crash-loops the machine -- a total outage caused by a single misplaced
`down_revision`. These tests make a forked graph fail in CI instead.
"""
import os
import re

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS = os.path.join(BACKEND, "alembic", "versions")


def _script_directory():
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    return ScriptDirectory.from_config(cfg)


def _on_disk_files():
    return sorted(
        name
        for name in os.listdir(VERSIONS)
        if name.endswith(".py") and not name.startswith("__")
    )


def _declared_revision(name):
    with open(os.path.join(VERSIONS, name)) as fh:
        text = fh.read()
    match = re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)", text, re.M)
    return match.group(1) if match else None


def _declared_down_revision(name):
    with open(os.path.join(VERSIONS, name)) as fh:
        text = fh.read()
    match = re.search(r"^down_revision(?::[^=]*)?\s*=\s*['\"]([^'\"]+)", text, re.M)
    return match.group(1) if match else None


def test_migrations_have_a_single_head():
    heads = _script_directory().get_heads()
    assert len(heads) == 1, (
        f"Alembic has {len(heads)} head revisions: {sorted(heads)}. "
        "`alembic upgrade head` fails at boot and crash-loops the app. "
        "Point the newest migration's down_revision at the real head, or add a merge migration."
    )


def _revision_map():
    return {name: _declared_revision(name) for name in _on_disk_files()}


def _parent_map():
    parents = {}
    for name in _on_disk_files():
        down = _declared_down_revision(name)
        if down is not None:
            parents[_declared_revision(name)] = down
    return parents


def _reachable_from_base(head):
    parents = _parent_map()
    seen, cursor = set(), head
    while cursor and cursor not in seen:
        seen.add(cursor)
        cursor = parents.get(cursor)
    return seen


def test_every_migration_file_is_reachable_from_the_head():
    reachable = _reachable_from_base(_script_directory().get_heads()[0])
    orphans = [
        name for name, rev in _revision_map().items()
        if rev and rev not in reachable
    ]
    assert not orphans, f"Migration files not reachable from the head: {orphans}"


def test_no_two_migrations_share_the_same_parent():
    """The outage cause: two files naming the same down_revision.

    Branching the newest migration off a mid-chain ancestor leaves the real
    head stranded, so `alembic upgrade head` finds two heads and refuses to
    run. The app then crash-loops on every boot.
    """
    by_parent = {}
    for name in _on_disk_files():
        down = _declared_down_revision(name)
        if down is not None:
            by_parent.setdefault(down, []).append(name)
    forked = {parent: kids for parent, kids in by_parent.items() if len(kids) > 1}
    assert not forked, (
        f"These revisions branch off the same parent: {forked}. "
        "A migration must extend the single head, not fork a second one."
    )


def test_reader_theme_migration_extends_the_previous_head():
    """Regression: this migration's down_revision pointed at a grandparent."""
    name = "b2c3d4e5f6a7_add_reader_theme.py"
    by_parent = {}
    for other in _on_disk_files():
        parent = _declared_down_revision(other)
        if parent is not None:
            by_parent.setdefault(parent, []).append(other)
    down = _declared_down_revision(name)
    assert by_parent.get(down, []) == [name], (
        f"{name} revises {down}, which already has children "
        f"{by_parent.get(down)}; it must revise the previous head instead."
    )
