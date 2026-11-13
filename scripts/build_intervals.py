"""
sha -> release interval, by ANCESTRY.

    python scripts/build_intervals.py workspace_data commons-lang checkstyle dubbo junit-framework questdb

Reads workspace_data/versions/rel_hist_<repo>.json and the clone in workspace_data/repos/.
Writes workspace_data/outputs/intervals_<repo>.json, alongside the other mined artifacts, so it
uploads with them.

WHY NOT TIMESTAMPS

    A commit authored in January on a feature branch and merged in June belongs, by date, to
    whichever release was cut in between -- a release its code was never in. `git rev-list A..B`
    asks what B contains that A does not, which is what "shipped in this release" means.

    It also matches the CK snapshots, which are taken AT the release commits. Assigning commits
    by date and metrics by ancestry would put them in different frames, and the disagreement
    would be silent: every join would succeed and some rows would describe the wrong interval.

MUST RUN LOCALLY

    It reads the git clones. Everything downstream reads the JSON it writes, so this is the
    only step that needs the repositories.
"""
import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args, check=False):
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if check and r.returncode != 0:
        return None
    return r.stdout


def read_releases(rel_hist: Path):
    """[(tag, sha)] as the manifest records them."""
    data = json.loads(rel_hist.read_text(encoding="utf-8"))
    out = []
    for e in data.get("entries", []):
        sha = e.get("snapshot_sha") or e.get("sha") or e.get("commit_sha")
        tag = e.get("tag") or e.get("version")
        if sha and tag:
            out.append((str(tag), str(sha)))
    return out


def order_by_ancestry(clone: Path, rels):
    """
    Sort releases oldest first, by how many commits each can reach.

    NOT by the manifest's order and NOT by date. A tag cut from a maintenance branch can be
    dated after a tag that descends from it, and a manifest may list tags however it found
    them. Reachable-commit count is monotonic along any path through history, so sorting by it
    puts a release after everything it contains.

    Tags whose commit is absent from the clone are dropped and counted.
    """
    dated, missing = [], []
    for tag, sha in rels:
        if (git(clone, "cat-file", "-t", sha) or "").strip() != "commit":
            missing.append(tag)
            continue
        count = git(clone, "rev-list", "--count", sha) or "0"
        dated.append((int(count.strip() or 0), tag, sha))
    dated.sort()
    return [(t, s) for _, t, s in dated], missing


def find_rel_hist(workspace: Path, repo: str):
    """
    The release manifest. `versions/` is where the pinning stage writes it; the others are
    checked so a workspace laid out differently still works, and the path used is printed.
    """
    name = f"rel_hist_{repo}.json"
    for d in (workspace / "versions", workspace / "outputs", workspace, Path.cwd()):
        if (d / name).exists():
            return d / name
    return None


def build(workspace: Path, repo: str) -> bool:
    clone = workspace / "repos" / repo
    rel_hist = find_rel_hist(workspace, repo)
    if not clone.exists():
        print(f"❌ {repo}: clone not found at {clone}")
        return False
    if rel_hist is None:
        print(f"❌ {repo}: rel_hist_{repo}.json not found. Looked in:")
        for d in (workspace / "versions", workspace / "outputs", workspace, Path.cwd()):
            print(f"      {d}")
        return False

    rels = read_releases(rel_hist)
    if len(rels) < 2:
        print(f"❌ {repo}: needs at least two releases, found {len(rels)}")
        return False

    ordered, missing = order_by_ancestry(clone, rels)
    if len(ordered) < 2:
        print(f"❌ {repo}: only {len(ordered)} release commit(s) present in the clone")
        return False

    reordered = [t for (t, _), (t2, _) in zip(ordered, rels) if t != t2]

    mapping, sizes, intervals = {}, [], []
    for i in range(len(ordered) - 1):
        (tag_a, sha_a), (tag_b, sha_b) = ordered[i], ordered[i + 1]
        name = f"{tag_a} -> {tag_b}"
        shas = (git(clone, "rev-list", f"{sha_a}..{sha_b}") or "").split()
        sizes.append(len(shas))
        intervals.append({"interval": name, "from": tag_a, "to": tag_b,
                          "from_sha": sha_a, "to_sha": sha_b, "commits": len(shas)})
        for s in shas:
            # A commit reachable from several releases is assigned to the EARLIEST interval
            # that contains it -- the release it actually shipped in.
            mapping.setdefault(s, name)

    before = (git(clone, "rev-list", ordered[0][1]) or "").split()

    # Written to outputs/ rather than beside the manifest: it is a derived artifact of the
    # corpus, like links_<repo>.csv, and belongs with the files that get archived together.
    out_dir = workspace / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"intervals_{repo}.json"
    dest.write_text(json.dumps({
        "repo": repo,
        "method": "git rev-list A..B (ancestry, releases ordered by reachable-commit count)",
        "rel_hist": str(rel_hist),
        "releases": len(ordered),
        "intervals": len(intervals),
        "commits_assigned": len(mapping),
        "commits_before_first_release": len(before),
        "tags_absent_from_clone": missing,
        "interval_index": intervals,
        "map": mapping,
    }, indent=1), encoding="utf-8")

    size_mb = dest.stat().st_size / 1e6
    print(f"✅ {repo:<18}{len(ordered):>4} releases  {len(intervals):>4} intervals  "
          f"{len(mapping):>7,} commits   {size_mb:.1f} MB")
    print(f"   {'':16}manifest: {rel_hist}")
    if sizes:
        srt = sorted(sizes)
        print(f"   {'':16}commits per interval: median {srt[len(srt)//2]:,}  "
              f"min {srt[0]:,}  max {srt[-1]:,}")
        if srt[0] == 0:
            n = sum(1 for s in sizes if s == 0)
            print(f"   {'':16}⚠️  {n} interval(s) contain no commits -- two tags on the same "
                  f"commit, or a re-tag")
    if before:
        print(f"   {'':16}{len(before):,} commit(s) predate the first release -- unassigned")
    if missing:
        print(f"   {'':16}⚠️  absent from the clone: {', '.join(missing[:5])}")
    if reordered:
        print(f"   {'':16}ℹ️  {len(reordered)} tag(s) were not in ancestry order in the manifest")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    ws = Path(sys.argv[1])
    print(f"workspace: {ws.resolve()}\n")
    results = [build(ws, r) for r in sys.argv[2:]]
    print()
    if all(results):
        print("All repositories mapped. Upload intervals_<repo>.json with the other outputs.")
    else:
        print(f"{results.count(False)} repository/repositories failed.")
    sys.exit(0 if all(results) else 1)
