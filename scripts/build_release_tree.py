"""
Every release, on the branch it belongs to: a RELEASE TREE, written beside the existing files.

    python scripts/build_release_tree.py workspace_data commons-lang checkstyle dubbo junit-framework questdb
    python scripts/build_release_tree.py workspace_data --write-intervals commons-lang checkstyle ...

Put this file beside build_intervals.py (it reuses that script's functions). It writes
outputs/release_tree_<repo>.json. With --write-intervals it also writes the tree as
outputs/intervals_<repo>.json, the file Notebooks 0-2 read, in the same format with the edges as
intervals; the one-list version is kept once as intervals_<repo>.list.json.

THE IDEA

    A single ordered list of releases cannot follow two lines developed at the same time. Instead,
    every release gets a PARENT: the latest release whose code it contains. That gives a tree:

        5.0.0 ── 5.1.0 ── 5.2.0 ...          main line
          └── 5.0.1 ── 5.0.2 ── 5.0.3        maintenance line

    Each interval is an EDGE parent -> release, holding the commits the release has and its parent
    lacks (git rev-list parent..release) -- the same rule as before, but measured from the release
    the code was built on, not from whichever release happened to sit before it in a list. A commit
    belongs to the first edge that contains it, as before.

    A release with several children (a fork point, 5.0.0 above) is labelled from all of them: its file
    counts as refactored if it was refactored on ANY line built on that release. A release with no
    child (the end of a maintenance line, and the latest release) has no finished interval after it,
    so it can describe history but cannot be a labelled row -- exactly as the last release is today.

THE PARENT -- exact containment of the Java code, no tolerance

    Among earlier releases whose Java code the release contains, the one that reaches the most
    commits. "Contains" is exact, judged on .java files, the only files this study measures:

      - A is an ancestor of B in git: B contains everything A had. Or
      - every commit A has and B lacks is a RELEASE-ONLY commit: a commit that no other release
        contains and that changes no .java file -- e.g. a "prepare release" commit that only bumps the
        version in pom.xml, made on a short side branch and tagged. A's Java code is then exactly the
        Java code B was built on, so nothing B's commits touch differs from A's files.

    Anything else -- a maintenance release whose fixes continue in its own line, or a side commit that
    changes Java code -- means B does not contain A, and A cannot be B's parent. The script counts
    the edges that rely on release-only commits, so the rule can be checked.

    A release whose version number is lower than its parent's is a re-tag (checkstyle's
    "checkstyle-4.4" on a 2018 commit) and is left out; so are duplicate tags of one commit.
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from build_intervals import git, read_releases, find_rel_hist

def version(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag))


def reaches(clone, sha):
    return int((git(clone, "rev-list", "--count", sha) or "0").strip() or 0)


def is_ancestor(clone, a, b):
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=str(clone)).returncode == 0


def changes_java(clone, sha):
    files = git(clone, "diff-tree", "-r", "--name-only", "--no-commit-id", "-m", "--first-parent", sha) or ""
    return any(f.endswith(".java") for f in files.split())


def release_only(clone, a, b, nodes):
    """
    The commits release A has and release B lacks, when every one of them is release-only (changes
    no .java file and is in no other release); None otherwise.
    """
    xs = (git(clone, "rev-list", f"{b['sha']}..{a['sha']}") or "").split()
    if not xs or any(changes_java(clone, x) for x in xs):
        return None
    for r in nodes:
        if r["sha"] != a["sha"] and any(is_ancestor(clone, x, r["sha"]) for x in xs):
            return None
    return xs


def tree(clone, rels):
    present = [(t, s) for t, s in rels if (git(clone, "cat-file", "-t", s) or "").strip() == "commit"]
    nodes, seen, duplicate = [], {}, []
    for c, t, s in sorted((reaches(clone, s), t, s) for t, s in present):
        if s in seen:
            duplicate.append(f"{t} (same commit as {seen[s]})")
            continue
        seen[s] = t
        nodes.append({"tag": t, "sha": s, "reaches": c})

    # A release can be a parent across release-only commits only if its own commit changes no Java
    # code and no other release contains it (a tag on a short side branch). Such a release may
    # reach as many commits as the release built after it, or more, so it is not limited to smaller
    # histories; every other parent is an ancestor, which always has a smaller history.
    for a in nodes:
        a["side_tag"] = (not changes_java(clone, a["sha"]) and
                         not any(is_ancestor(clone, a["sha"], b["sha"]) for b in nodes if b is not a))

    dropped, retag = set(), []
    while True:
        kept = [n for n in nodes if n["tag"] not in dropped]
        by_tag = {n["tag"]: n for n in kept}
        for b in kept:
            b["parent"], b["parent_extra"] = None, 0
            # The nearest contained release: the one whose Java code is the largest history. For an
            # ancestor that is its history size; for a side tag, its size without its release-only
            # commits (the commit it was branched from). Ties go to the ancestor.
            best = None                          # (effective size, is an ancestor, tag, release-only)
            for a in sorted(kept, key=lambda a: -a["reaches"]):
                if a is b:
                    continue
                if best and (a["reaches"] < best[0] or (a["reaches"] == best[0] and best[1])):
                    break                        # nothing further down can be nearer
                if a["reaches"] < b["reaches"] and is_ancestor(clone, a["sha"], b["sha"]):
                    if not best or a["reaches"] >= best[0]:
                        best = (a["reaches"], True, a["tag"], 0)
                    break                        # every later ancestor is smaller
                if a["side_tag"] and not is_ancestor(clone, b["sha"], a["sha"]):
                    xs = release_only(clone, a, b, kept)
                    # two side tags with identical Java code would each contain the other:
                    # the one with the smaller history is then the parent
                    mutual = xs and b["side_tag"] and release_only(clone, b, a, kept)
                    if xs and not (mutual and a["reaches"] >= b["reaches"]):
                        eff = a["reaches"] - len(xs)
                        if not best or eff > best[0]:
                            best = (eff, False, a["tag"], len(xs))
            if best:
                b["parent"], b["parent_extra"] = best[2], best[3]
        # a re-tag: a release whose version number is lower than its parent's
        new = [b for b in kept if b["parent"] and version(b["tag"]) < version(by_tag[b["parent"]]["tag"])]
        if not new:
            break
        for b in new:
            dropped.add(b["tag"])
            retag.append(f"{b['tag']} (inside {b['parent']})")

    for b in kept:                               # no release may be its own ancestor
        seen, t = set(), b["tag"]
        while t:
            if t in seen:
                raise SystemExit(f"cycle in the release tree at {t}")
            seen.add(t)
            t = by_tag[t]["parent"]

    children = defaultdict(list)
    for b in kept:
        if b["parent"]:
            children[b["parent"]].append(b["tag"])
    for b in kept:
        b["children"] = children.get(b["tag"], [])
    missing = [t for t, s in rels if (t, s) not in present]
    return kept, duplicate, retag, missing


def build(workspace: Path, repo: str, write_intervals=False) -> bool:
    clone = workspace / "repos" / repo
    rel_hist = find_rel_hist(workspace, repo)
    if not clone.exists() or rel_hist is None:
        print(f"❌ {repo}: clone or rel_hist_{repo}.json not found")
        return False
    nodes, duplicate, retag, missing = tree(clone, read_releases(rel_hist))
    by_tag = {b["tag"]: b for b in nodes}

    mapping, edges = {}, []
    for b in nodes:                                        # smallest history first
        if not b["parent"]:
            continue
        a = by_tag[b["parent"]]
        name = f"{a['tag']} -> {b['tag']}"
        shas = (git(clone, "rev-list", f"{a['sha']}..{b['sha']}") or "").split()
        edges.append({"interval": name, "from": a["tag"], "to": b["tag"], "from_sha": a["sha"],
                      "to_sha": b["sha"], "commits": len(shas), "release_only_commits": b["parent_extra"]})
        for s in shas:
            mapping.setdefault(s, name)

    roots = [b["tag"] for b in nodes if not b["parent"]]
    leaves = [b["tag"] for b in nodes if not b["children"]]
    forks = {b["tag"]: b["children"] for b in nodes if len(b["children"]) > 1}
    labelled = [b["tag"] for b in nodes if b["children"]]
    before = set()
    for r in roots:
        before |= set((git(clone, "rev-list", by_tag[r]["sha"]) or "").split())

    # every release's position in history-size order, and each edge's path from the root
    pos = {b["tag"]: i for i, b in enumerate(nodes)}
    for b in nodes:
        b["pos"] = pos[b["tag"]]
    edge_of = {e["to"]: k for k, e in enumerate(edges)}
    for e in edges:
        chain, t = [], e["from"]
        while t in edge_of:                      # the edges that led to this edge's start
            chain.append(edge_of[t])
            t = by_tag[t]["parent"]
        e["from_pos"], e["to_pos"] = pos[e["from"]], pos[e["to"]]
        e["ancestor_edges"] = chain[::-1]        # from the root down to this edge's start

    out = workspace / "outputs" / f"release_tree_{repo}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "repo": repo,
        "method": "parent = the latest release whose Java code the release contains exactly; "
                  "interval = git rev-list parent..release; a commit belongs to the first such edge",
        "releases": nodes, "edges": edges, "roots": roots, "leaves": leaves, "forks": forks,
        "labelled_releases": labelled, "duplicate_tags": duplicate, "retags": retag,
        "tags_absent_from_clone": missing, "commits_assigned": len(mapping),
        "commits_before_first_release": len(before - set(mapping)), "map": mapping,
    }, indent=1), encoding="utf-8")

    if write_intervals:
        dest = workspace / "outputs" / f"intervals_{repo}.json"
        keep = workspace / "outputs" / f"intervals_{repo}.list.json"
        if dest.exists() and not keep.exists():
            dest.replace(keep)                   # the one-list version, kept once
        dest.write_text(json.dumps({
            "repo": repo, "kind": "tree",
            "method": "release tree: parent = the latest release whose Java code the release contains "
                      "exactly; interval = git rev-list parent..release; a commit belongs to the first "
                      "edge that contains it",
            "rel_hist": str(rel_hist), "releases": nodes, "intervals": len(edges),
            "labelled_releases": labelled, "commits_assigned": len(mapping),
            "commits_before_first_release": len(before - set(mapping)),
            "tags_absent_from_clone": missing, "duplicate_tags": duplicate, "retags": retag,
            "interval_index": edges, "map": mapping,
        }, indent=1), encoding="utf-8")

    print(f"✅ {repo:<18}{len(nodes):>4} releases in the tree   {len(edges):>4} edges   "
          f"{len(mapping):>7,} commits assigned")
    print(f"   {'':16}labelled releases (have a child): {len(labelled)}   "
          f"without a child: {len(leaves)}   fork points: {len(forks)}   roots: {len(roots)}")
    ro = [e["release_only_commits"] for e in edges if e["release_only_commits"]]
    print(f"   {'':16}edges across release-only commits (no .java change, in no other release): "
          f"{len(ro)}" + (f", {min(ro)}-{max(ro)} commits each" if ro else ""))
    print(f"   {'':16}without a child: {', '.join(leaves)}")
    for f, c in list(forks.items())[:8]:
        print(f"   {'':16}fork {f} -> {', '.join(c)}")
    if len(forks) > 8:
        print(f"   {'':16}... {len(forks) - 8} more fork points in the file")
    for name, items in (("duplicate tags", duplicate), ("re-tags left out", retag),
                        ("absent from the clone", missing)):
        if items:
            print(f"   {'':16}{name}: {', '.join(items)}")
    if len(roots) > 1:
        print(f"   {'':16}⚠️  more than one root: {', '.join(roots)}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    args = [a for a in sys.argv[1:] if a != "--write-intervals"]
    write = "--write-intervals" in sys.argv
    ws = Path(args[0])
    print(f"workspace: {ws.resolve()}\n")
    ok = [build(ws, r, write) for r in args[1:]]
    print("\nwrote release_tree_<repo>.json" + (
        " and intervals_<repo>.json (the one-list version kept as intervals_<repo>.list.json)"
        if write else "; intervals_<repo>.json untouched (add --write-intervals to replace it)"))
    sys.exit(0 if all(ok) else 1)