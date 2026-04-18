"""Tests for singleton folder consolidation and alphabetical sorting."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bookmark_cleaner import (
    Bookmark,
    Folder,
    _collect_folder_names,
    _move_bookmark,
    _delete_empty_folder,
    _prune_empty_folders,
    collect_singleton_folders,
    consolidate_singleton_folders,
    sort_tree,
)

# ---------------------------------------------------------------------------
# Fixtures / Builders
# ---------------------------------------------------------------------------


def _bm(title: str, href: str = "") -> Bookmark:
    return Bookmark(href=href or f"http://example.com/{title}", title=title)


def _folder(name: str, *children) -> Folder:
    f = Folder(name=name)
    f.children = list(children)
    return f


# ---------------------------------------------------------------------------
# collect_singleton_folders
# ---------------------------------------------------------------------------


class TestCollectSingletonFolders:
    def test_empty_tree_returns_nothing(self):
        root = _folder("__root__")
        assert collect_singleton_folders(root) == []

    def test_finds_singleton_folder(self):
        bm = _bm("Only One")
        singleton = _folder("Solo", bm)
        root = _folder("__root__", singleton)
        results = collect_singleton_folders(root)
        assert len(results) == 1
        parent, sf, lone = results[0]
        assert parent is root
        assert sf is singleton
        assert lone is bm

    def test_ignores_folder_with_two_bookmarks(self):
        two = _folder("Pair", _bm("A"), _bm("B"))
        root = _folder("__root__", two)
        assert collect_singleton_folders(root) == []

    def test_ignores_folder_with_bookmark_and_subfolder(self):
        sub = _folder("Sub", _bm("Child"))
        mixed = _folder("Mixed", _bm("Alone"), sub)
        root = _folder("__root__", mixed)
        # "Mixed" has 2 children, not a singleton
        # "Sub" has 1 child — IS a singleton
        results = collect_singleton_folders(root)
        assert len(results) == 1
        _, sf, _ = results[0]
        assert sf is sub

    def test_does_not_flag_root(self):
        root = _folder("__root__", _bm("Only"))
        # root has 1 child (a bookmark directly) — root itself must not appear
        results = collect_singleton_folders(root)
        assert results == []

    def test_finds_nested_singleton(self):
        bm = _bm("Deep")
        inner = _folder("Inner", bm)
        outer = _folder("Outer", inner)
        root = _folder("__root__", outer)
        results = collect_singleton_folders(root)
        assert len(results) == 1
        parent, sf, lone = results[0]
        assert parent is outer
        assert sf is inner
        assert lone is bm

    def test_finds_multiple_singletons(self):
        s1 = _folder("S1", _bm("X"))
        s2 = _folder("S2", _bm("Y"))
        multi = _folder("Multi", _bm("A"), _bm("B"))
        root = _folder("__root__", s1, s2, multi)
        results = collect_singleton_folders(root)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# _collect_folder_names
# ---------------------------------------------------------------------------


class TestCollectFolderNames:
    def test_empty_root_returns_empty(self):
        root = _folder("__root__")
        assert _collect_folder_names(root) == []

    def test_single_top_level_folder(self):
        root = _folder("__root__", _folder("AI Tools"))
        names = _collect_folder_names(root)
        assert names == ["AI Tools"]

    def test_nested_folders(self):
        inner = _folder("Frontend")
        outer = _folder("Software", inner)
        root = _folder("__root__", outer)
        names = _collect_folder_names(root)
        assert "Software" in names
        assert "Software/Frontend" in names

    def test_bookmarks_excluded(self):
        root = _folder(
            "__root__", _bm("Some Bookmark"), _folder("Real Folder")
        )
        names = _collect_folder_names(root)
        assert names == ["Real Folder"]

    def test_sorted_output(self):
        root = _folder("__root__", _folder("Zebra"), _folder("Apple"))
        names = _collect_folder_names(root)
        assert names == sorted(names)

    def test_does_not_include_root_name(self):
        root = _folder("__root__", _folder("Child"))
        names = _collect_folder_names(root)
        assert "__root__" not in names


# ---------------------------------------------------------------------------
# _move_bookmark
# ---------------------------------------------------------------------------


class TestMoveBookmark:
    def test_moves_from_source_to_dest(self):
        bm = _bm("Target")
        source = _folder("Source", bm)
        dest = _folder("Dest")
        _move_bookmark(source, dest, bm)
        assert bm not in source.children
        assert bm in dest.children

    def test_source_becomes_empty(self):
        bm = _bm("Only")
        source = _folder("Source", bm)
        dest = _folder("Dest")
        _move_bookmark(source, dest, bm)
        assert source.children == []

    def test_dest_preserves_existing_children(self):
        bm = _bm("Mover")
        existing = _bm("Already Here")
        source = _folder("Source", bm)
        dest = _folder("Dest", existing)
        _move_bookmark(source, dest, bm)
        assert existing in dest.children
        assert bm in dest.children


# ---------------------------------------------------------------------------
# _delete_empty_folder
# ---------------------------------------------------------------------------


class TestDeleteEmptyFolder:
    def test_removes_empty_folder_from_parent(self):
        empty = _folder("Empty")
        parent = _folder("Parent", empty)
        _delete_empty_folder(parent, empty)
        assert empty not in parent.children

    def test_raises_if_folder_not_empty(self):
        full = _folder("Full", _bm("Something"))
        parent = _folder("Parent", full)
        with pytest.raises(ValueError):
            _delete_empty_folder(parent, full)

    def test_raises_if_folder_not_in_parent(self):
        stranger = _folder("Stranger")
        parent = _folder("Parent")
        with pytest.raises(ValueError):
            _delete_empty_folder(parent, stranger)


# ---------------------------------------------------------------------------
# _prune_empty_folders
# ---------------------------------------------------------------------------


class TestPruneEmptyFolders:
    def test_removes_empty_leaf_folder(self):
        empty = _folder("Empty")
        root = _folder("__root__", empty)
        _prune_empty_folders(root)
        assert empty not in root.children

    def test_leaves_non_empty_folder_alone(self):
        full = _folder("Full", _bm("Something"))
        root = _folder("__root__", full)
        _prune_empty_folders(root)
        assert full in root.children

    def test_prunes_nested_empty_chain(self):
        deep_empty = _folder("DeepEmpty")
        mid = _folder("Mid", deep_empty)
        root = _folder("__root__", mid)
        _prune_empty_folders(root)
        # mid becomes empty after deep_empty removed → mid also removed
        assert mid not in root.children

    def test_preserves_folder_with_bookmark(self):
        bm = _bm("Keep")
        keeper = _folder("Keeper", bm)
        root = _folder("__root__", keeper)
        _prune_empty_folders(root)
        assert keeper in root.children


# ---------------------------------------------------------------------------
# consolidate_singleton_folders (integration)
# ---------------------------------------------------------------------------


class TestConsolidateSingletonFolders:
    def test_no_singletons_returns_zero(self):
        pair = _folder("Pair", _bm("A"), _bm("B"))
        root = _folder("__root__", pair)
        result = consolidate_singleton_folders(root, use_ai=False)
        assert result == 0

    def test_relocates_singleton_via_rules(self):
        # "python" keyword should match Software Engineering rule
        bm = _bm("Python Tutorial", "http://python.org/tutorial")
        singleton = _folder("SoloFolder", bm)
        pair = _folder("Software Engineering", _bm("A"), _bm("B"))
        root = _folder("__root__", singleton, pair)
        result = consolidate_singleton_folders(root, use_ai=False)
        assert result >= 1
        assert singleton not in root.children

    def test_singleton_moved_to_unsorted_when_no_rule_matches(self):
        bm = _bm("Zork XXXXXXXXX", "http://no-match-xyzzy.example.com")
        singleton = _folder("SoloRando", bm)
        root = _folder("__root__", singleton)
        consolidate_singleton_folders(root, use_ai=False)
        # singleton should be removed, bm should end up somewhere
        assert singleton not in root.children
        all_bookmarks = _collect_all(root)
        assert bm in all_bookmarks

    def test_returns_count_of_relocated(self):
        s1 = _folder("S1", _bm("x1", "http://python.org/x1"))
        s2 = _folder("S2", _bm("x2", "http://python.org/x2"))
        pair = _folder("Software Engineering", _bm("A"), _bm("B"))
        root = _folder("__root__", s1, s2, pair)
        result = consolidate_singleton_folders(root, use_ai=False)
        assert result == 2

    def test_convergence_guard_prevents_infinite_loop(self):
        # Only one bookmark, no other folders — must terminate
        bm = _bm("Lone Wolf", "http://xyzzy-unique-no-match.test")
        singleton = _folder("Only", bm)
        root = _folder("__root__", singleton)
        result = consolidate_singleton_folders(root, use_ai=False)
        # Should not hang; result is 1 (moved to Unsorted Bookmarks)
        assert result == 1


# ---------------------------------------------------------------------------
# sort_tree
# ---------------------------------------------------------------------------


class TestSortTree:
    def test_sorts_bookmarks_alphabetically(self):
        root = _folder("__root__", _bm("Zebra"), _bm("Apple"), _bm("Mango"))
        sort_tree(root)
        titles = [c.title for c in root.children]
        assert titles == sorted(titles, key=str.lower)

    def test_folders_sorted_before_bookmarks(self):
        bm = _bm("Alpha Bookmark")
        folder = _folder("Zebra Folder")
        root = _folder("__root__", bm, folder)
        sort_tree(root)
        assert isinstance(root.children[0], Folder)
        assert isinstance(root.children[1], Bookmark)

    def test_folders_sorted_alphabetically_among_themselves(self):
        f1 = _folder("Zebra")
        f2 = _folder("Apple")
        f3 = _folder("Mango")
        root = _folder("__root__", f1, f2, f3)
        sort_tree(root)
        names = [c.name for c in root.children]
        assert names == sorted(names, key=str.lower)

    def test_case_insensitive_sort(self):
        root = _folder("__root__", _bm("zebra"), _bm("Apple"), _bm("mango"))
        sort_tree(root)
        titles = [c.title for c in root.children]
        assert titles == sorted(titles, key=str.lower)

    def test_recursion_into_subfolders(self):
        inner = _folder("Inner", _bm("Z"), _bm("A"))
        root = _folder("__root__", inner)
        sort_tree(root)
        titles = [c.title for c in inner.children]
        assert titles == ["A", "Z"]


# ---------------------------------------------------------------------------
# AI prompt content check
# ---------------------------------------------------------------------------


def test_taxonomy_prompt_contains_min_bookmark_constraint():
    """AI taxonomy prompt must instruct at-least-2-bookmarks per folder."""
    import inspect
    import bookmark_cleaner

    src = inspect.getsource(bookmark_cleaner.build_ai_folder_taxonomy)
    assert "at least 2" in src or "at least two" in src.lower()


def test_taxonomy_function_accepts_existing_folders_param():
    """build_ai_folder_taxonomy must accept existing_folders keyword argument."""
    import inspect
    import bookmark_cleaner

    sig = inspect.signature(bookmark_cleaner.build_ai_folder_taxonomy)
    assert "existing_folders" in sig.parameters


def test_taxonomy_prompt_includes_existing_folders_when_provided():
    """When existing_folders passed, prompt must mention them."""
    import inspect
    import bookmark_cleaner

    src = inspect.getsource(bookmark_cleaner.build_ai_folder_taxonomy)
    assert "existing_folders" in src
    assert "Prefer assigning" in src or "existing folder" in src


# ---------------------------------------------------------------------------
# Additional edge-case and integration tests
# ---------------------------------------------------------------------------


class TestCollectSingletonFoldersEdgeCases:
    def test_folder_with_only_subfolder_not_flagged(self):
        sub = _folder("Sub", _bm("A"), _bm("B"))
        parent_only = _folder("ParentOnly", sub)
        root = _folder("__root__", parent_only)
        results = collect_singleton_folders(root)
        assert results == []

    def test_deeply_nested_singleton(self):
        bm = _bm("Deep")
        level3 = _folder("Level3", bm)
        level2 = _folder("Level2", level3)
        level1 = _folder("Level1", level2)
        root = _folder("__root__", level1)
        results = collect_singleton_folders(root)
        assert len(results) == 1
        parent, sf, lone = results[0]
        assert parent is level2
        assert sf is level3
        assert lone is bm

    def test_singleton_beside_normal_folder(self):
        singleton = _folder("Alone", _bm("X"))
        normal = _folder("Normal", _bm("A"), _bm("B"))
        root = _folder("__root__", singleton, normal)
        results = collect_singleton_folders(root)
        assert len(results) == 1
        _, sf, _ = results[0]
        assert sf is singleton


class TestCollectFolderNamesEdgeCases:
    def test_multiple_top_level_folders(self):
        root = _folder(
            "__root__", _folder("Coding"), _folder("Health"), _folder("Travel")
        )
        names = _collect_folder_names(root)
        assert set(names) == {"Coding", "Health", "Travel"}

    def test_deep_nesting_path_format(self):
        c = _folder("C")
        b = _folder("B", c)
        a = _folder("A", b)
        root = _folder("__root__", a)
        names = _collect_folder_names(root)
        assert "A" in names
        assert "A/B" in names
        assert "A/B/C" in names


class TestMoveBookmarkEdgeCases:
    def test_move_one_of_multiple_bookmarks(self):
        bm1 = _bm("Stay")
        bm2 = _bm("Move")
        source = _folder("Source", bm1, bm2)
        dest = _folder("Dest")
        _move_bookmark(source, dest, bm2)
        assert bm1 in source.children
        assert bm2 not in source.children
        assert bm2 in dest.children


class TestConsolidateSingletonFoldersEdgeCases:
    def test_empty_tree_unchanged(self):
        root = _folder("__root__")
        result = consolidate_singleton_folders(root, use_ai=False)
        assert result == 0
        assert root.children == []

    def test_no_ai_flag_respected(self):
        """With use_ai=False, function should still work via keyword rules or Unsorted."""
        bm = _bm("Python Guide", "http://python.org/guide")
        singleton = _folder("SoloPython", bm)
        pair = _folder("Software Engineering", _bm("A"), _bm("B"))
        root = _folder("__root__", singleton, pair)
        result = consolidate_singleton_folders(root, use_ai=False)
        assert result >= 1

    def test_all_bookmarks_preserved_after_consolidation(self):
        bms = [_bm(f"BM{i}", f"http://example.com/{i}") for i in range(6)]
        s1 = _folder("Solo1", bms[0])
        s2 = _folder("Solo2", bms[1])
        pair = _folder("Group", bms[2], bms[3], bms[4], bms[5])
        root = _folder("__root__", s1, s2, pair)
        consolidate_singleton_folders(root, use_ai=False)
        all_bms = _collect_all(root)
        for bm in bms:
            assert bm in all_bms, f"{bm.title} lost after consolidation"

    def test_singleton_deleted_after_move(self):
        bm = _bm("Python Docs", "http://docs.python.org")
        singleton = _folder("OnlyPython", bm)
        pair = _folder("Software Engineering", _bm("A"), _bm("B"))
        root = _folder("__root__", singleton, pair)
        consolidate_singleton_folders(root, use_ai=False)
        folder_names = [c.name for c in root.children if isinstance(c, Folder)]
        assert "OnlyPython" not in folder_names

    def test_multipass_chain_resolved(self):
        """Moving a bookmark creates another singleton — second pass resolves it."""
        bm_a = _bm("Python A", "http://python.org/a")
        bm_b = _bm("Python B", "http://python.org/b")
        # Two singletons, after first pass one might create a new singleton scenario
        s1 = _folder("S1", bm_a)
        s2 = _folder("S2", bm_b)
        # A folder with 2 items so there's a destination
        normal = _folder("Software Engineering", _bm("X"), _bm("Y"))
        root = _folder("__root__", s1, s2, normal)
        result = consolidate_singleton_folders(root, use_ai=False)
        # No singleton folders should remain
        remaining = collect_singleton_folders(root)
        assert remaining == []
        assert result >= 2


class TestSortTreeEdgeCases:
    def test_empty_folder_unchanged(self):
        root = _folder("__root__")
        sort_tree(root)
        assert root.children == []

    def test_single_child_unchanged(self):
        bm = _bm("Alone")
        root = _folder("__root__", bm)
        sort_tree(root)
        assert root.children == [bm]

    def test_mixed_folders_and_bookmarks_sorted(self):
        bm1 = _bm("Zebra Book")
        bm2 = _bm("Apple Book")
        f1 = _folder("Mango Folder")
        f2 = _folder("Banana Folder")
        root = _folder("__root__", bm1, f1, bm2, f2)
        sort_tree(root)
        # Folders first, alphabetical; then bookmarks, alphabetical
        assert isinstance(root.children[0], Folder)
        assert isinstance(root.children[1], Folder)
        assert root.children[0].name == "Banana Folder"
        assert root.children[1].name == "Mango Folder"
        assert isinstance(root.children[2], Bookmark)
        assert isinstance(root.children[3], Bookmark)
        assert root.children[2].title == "Apple Book"
        assert root.children[3].title == "Zebra Book"

    def test_numbers_sort_before_letters(self):
        root = _folder("__root__", _bm("B item"), _bm("1 item"), _bm("A item"))
        sort_tree(root)
        titles = [c.title for c in root.children]
        assert titles == sorted(titles, key=str.lower)


# ---------------------------------------------------------------------------
# Helpers for tests
# ---------------------------------------------------------------------------


def _collect_all(node) -> list:
    result = []
    for child in node.children:
        if isinstance(child, Bookmark):
            result.append(child)
        elif isinstance(child, Folder):
            result.extend(_collect_all(child))
    return result
