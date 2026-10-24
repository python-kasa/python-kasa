#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "git-cliff==2.14.2",
#   "packaging==26.3",
# ]
# ///
"""Release tooling, see RELEASING.md.

release.py prepare [--base master|patch] [--push] VERSION [COMMIT...]
    Preview the release PR, or with --push open it.

release.py extract CHANGELOG.md VERSION
    Print the notes of one release, used as the GitHub release notes.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from packaging.version import InvalidVersion, Version

REPO = "python-kasa/python-kasa"
# The remote of python-kasa/python-kasa, override if it is named differently.
REMOTE = os.environ.get("REMOTE", "upstream")

# Sections of CHANGELOG.md start with a "## [version](...)" heading, newest first.
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.MULTILINE)
RELEASE_VERSION = re.compile(r"\d+(\.\d+){2,3}")


def _parse(version: str) -> Version:
    """Parse the version of a changelog heading."""
    try:
        return Version(version)
    except InvalidVersion:
        raise ValueError(f"Unsupported version in changelog: {version!r}") from None


def _span(text: str, version: str) -> tuple[int, int] | None:
    """Return the start and end offset of the section of ``version``."""
    matches = list(HEADING.finditer(text))
    for idx, match in enumerate(matches):
        if match["version"] == version:
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            return match.start(), end

    return None


def extract(text: str, version: str) -> str:
    """Return the notes of ``version``, without the heading."""
    span = _span(text, version)
    if span is None:
        raise ValueError(f"No section for {version} found")

    start = text.index("\n", span[0]) + 1
    return text[start : span[1]].strip() + "\n"


def insert(text: str, section: str) -> str:
    """Insert a section above the first section with a lower version."""
    section = section.strip() + "\n\n"
    first = HEADING.match(section)
    if not first:
        raise ValueError("The section needs to start with a '## [version]' heading")
    key = _parse(first["version"])
    for match in HEADING.finditer(text):
        existing = _parse(match["version"])
        if existing == key:
            raise ValueError(f"{first['version']} is already in the changelog")
        if existing < key:
            return text[: match.start()] + section + text[match.start() :]
    raise ValueError(f"No older release than {first['version']} found")


def run(
    *cmd: str,
    capture: bool = False,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> str:
    """Run a command, echoing it, and raise if it fails."""
    print("+", " ".join(cmd), file=sys.stderr)
    result = subprocess.run(  # noqa: S603
        cmd,
        check=True,
        text=True,
        capture_output=capture,
        input=stdin,
        env=env,
        cwd=cwd,
    )
    return result.stdout if capture else ""


@contextlib.contextmanager
def worktree(rev: str) -> Iterator[Path]:
    """Check out ``rev`` in a temporary worktree, to leave the user's checkout alone."""
    with tempfile.TemporaryDirectory(prefix="release-") as tmp:
        path = Path(tmp) / "checkout"
        run("git", "worktree", "add", "--quiet", "--detach", str(path), rev)
        try:
            yield path
        finally:
            run("git", "worktree", "remove", "--force", str(path))


def remote_branch_exists(branch: str) -> bool:
    """Return True if the branch exists on the remote."""
    return bool(run("git", "ls-remote", REMOTE, f"refs/heads/{branch}", capture=True))


def generate_section(version: str, checkout: Path) -> str:
    """Generate the changelog section of ``version`` with git-cliff."""
    token = run("gh", "auth", "token", capture=True).strip()
    env = {**os.environ, "GITHUB_TOKEN": token}
    cmd = ["git-cliff", "--github-repo", REPO, "--unreleased", "--strip", "header"]
    cmd += ["--tag", version]

    return run(*cmd, capture=True, env=env, cwd=checkout)


def update_changelog(checkout: Path, section: str) -> None:
    """Add the section to CHANGELOG.md of the checkout."""
    path = checkout / "CHANGELOG.md"
    changelog = insert(path.read_text(encoding="utf-8"), section)
    path.write_text(changelog, encoding="utf-8")


def publish_pr(version: str, base: str, branch: str, section: str) -> None:
    """Open the release PR."""
    create = ["gh", "pr", "create", "--repo", REPO, "--base", base, "--head", branch]
    create += ["--title", f"Prepare {version}", "--label", "release-prep"]
    run(*create, "--body-file", "-", stdin=section)


def commit_changes(
    checkout: Path, message: str, branch: str, sign: list[str], *, push: bool
) -> None:
    """Commit the staged changes, then push them or show what would be pushed."""
    # The hooks of the user's checkout also run in the worktree, CI lints the PR.
    run("git", "commit", "--no-verify", "--message", message, *sign, cwd=checkout)
    if push:
        run("git", "push", REMOTE, f"HEAD:refs/heads/{branch}", cwd=checkout)
    else:
        run("git", "show", "--stat", "--format=%h %s", cwd=checkout)


def create_branch(
    version: str,
    base: str,
    branch: str,
    commits: list[str],
    sign: list[str],
    *,
    push: bool,
) -> str:
    """Create the release branch on the remote and return the changelog section."""
    for commit in commits:
        try:
            run("git", "rev-parse", "--verify", f"{commit}^{{commit}}", capture=True)
        except subprocess.CalledProcessError:
            raise ValueError(f"Unknown commit: {commit}") from None

    with worktree(f"{REMOTE}/{base}") as checkout:
        if commits:
            try:
                run("git", "cherry-pick", "-x", *sign, *commits, cwd=checkout)
            except subprocess.CalledProcessError:
                # There is nothing to abort if the failure was not a conflict
                with contextlib.suppress(subprocess.CalledProcessError):
                    run("git", "cherry-pick", "--abort", cwd=checkout)
                raise ValueError(
                    "Cherry-picking failed, if the commits conflict with "
                    f"{REMOTE}/{base} cherry-pick them on a branch of your own, "
                    "resolve the conflicts and pass the resulting commits instead"
                ) from None

        run("uv", "version", version, "--no-sync", cwd=checkout)
        section = generate_section(version, checkout)

        update_changelog(checkout, section)
        run("git", "add", "pyproject.toml", "uv.lock", "CHANGELOG.md", cwd=checkout)
        commit_changes(checkout, f"Prepare {version}", branch, sign, push=push)

    return section


def prepare(
    version: str,
    base: str,
    commits: list[str],
    *,
    push: bool = False,
) -> None:
    """Create the release PR for ``version``."""
    if commits and base != "patch":
        raise ValueError("Commits can only be cherry-picked with --base patch")

    # Patch releases require signed commits
    sign = ["-S"] if base == "patch" else []
    branch = f"release/{version}"

    run("git", "fetch", REMOTE, base, "--tags")

    # Without the config git-cliff silently falls back to its default template.
    try:
        run("git", "cat-file", "-e", f"{REMOTE}/{base}:cliff.toml", capture=True)
    except subprocess.CalledProcessError:
        raise ValueError(f"cliff.toml is missing from {REMOTE}/{base}") from None

    if remote_branch_exists(branch):
        raise ValueError(
            f"{branch} exists on {REMOTE}, to prepare the release again "
            "close its PR and delete the branch"
        )

    section = create_branch(version, base, branch, commits, sign, push=push)
    if not push:
        print(section)
        print(f"Dry run, add --push to push {branch} and open the PR.", file=sys.stderr)
        return

    publish_pr(version, base, branch, section)
    print("Review CHANGELOG.md in the PR, fix entries and add the summary there.")
    print("Merge the PR once CI passes, a draft release is created automatically.")


def _release_version(value: str) -> str:
    """Accept x.y.z and x.y.z.n as release versions."""
    if not RELEASE_VERSION.fullmatch(value) or str(Version(value)) != value:
        raise argparse.ArgumentTypeError(f"invalid version: {value}")

    return value


def main() -> int:
    """Run the command line interface."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser("prepare", help="preview or open the PR")
    prepare_parser.add_argument("--base", choices=["master", "patch"], default="master")
    prepare_parser.add_argument(
        "--push",
        action="store_true",
        help="push the branch and open the PR, by default only a preview",
    )
    prepare_parser.add_argument("version", type=_release_version)
    prepare_parser.add_argument("commits", nargs="*", help="commits to cherry-pick")

    extract_parser = commands.add_parser("extract", help="print one release section")
    extract_parser.add_argument("file", type=Path)
    extract_parser.add_argument("version")

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.version, args.base, args.commits, push=args.push)
        else:
            text = args.file.read_text(encoding="utf-8")
            sys.stdout.write(extract(text, args.version))
    except (ValueError, subprocess.CalledProcessError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        # Captured output (git-cliff, gh) is otherwise lost.
        if isinstance(ex, subprocess.CalledProcessError) and ex.stderr:
            print(ex.stderr, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


if "pytest" in sys.modules:
    # Tests, run with: uv run pytest devtools/release.py
    # pytest is only imported when it runs this file, the script does not need it.
    import pytest

    def _versions(changelog: str) -> list[str]:
        return [match["version"] for match in HEADING.finditer(changelog)]

    @pytest.fixture
    def changelog() -> str:
        """Return a changelog with a release, a patch release and a legacy heading."""
        return (
            "# Changelog\n\n"
            "## [0.12.0](https://example.com/0.12.0) (2026-10-12)\n\n- new\n\n"
            "## [0.11.0.1](https://example.com/0.11.0.1) (2026-10-04)\n\n- fix\n\n"
            "## [0.10.2](https://example.com/0.10.2) (2025-02-12)\n\n- old\n\n"
            "## [0.4.0.pre0](https://example.com/0.4.0.pre0) (2020-05-27)\n\n- old\n"
        )

    @pytest.mark.parametrize(
        ("version", "notes"),
        [("0.12.0", "- new\n"), ("0.11.0.1", "- fix\n"), ("0.4.0.pre0", "- old\n")],
    )
    def test_extract(changelog: str, version: str, notes: str) -> None:
        """The notes are the section without its heading, also for the last one."""
        assert extract(changelog, version) == notes

    def test_extract_unknown_version(changelog: str) -> None:
        """A release that is not in the changelog is an error."""
        with pytest.raises(ValueError, match="No section for 0.13.0"):
            extract(changelog, "0.13.0")

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("0.13.0", ["0.13.0", "0.12.0", "0.11.0.1", "0.10.2", "0.4.0.pre0"]),
            ("0.11.0.2", ["0.12.0", "0.11.0.2", "0.11.0.1", "0.10.2", "0.4.0.pre0"]),
            ("0.10.2.1", ["0.12.0", "0.11.0.1", "0.10.2.1", "0.10.2", "0.4.0.pre0"]),
            ("0.5.0", ["0.12.0", "0.11.0.1", "0.10.2", "0.5.0", "0.4.0.pre0"]),
        ],
    )
    def test_insert_orders_by_version(
        changelog: str, version: str, expected: list[str]
    ) -> None:
        """Sections are inserted by version, a patch release lands below newer ones."""
        section = f"## [{version}](https://example.com/{version})\n\n- entry\n"
        assert _versions(insert(changelog, section)) == expected

    def test_insert_existing_release(changelog: str) -> None:
        """Inserting a release that is in the changelog is an error."""
        section = "## [0.11.0.1](https://example.com/0.11.0.1)\n\n- again\n"
        with pytest.raises(ValueError, match="already in the changelog"):
            insert(changelog, section)

    @pytest.mark.parametrize(
        ("section", "message"),
        [
            ("- no heading\n", "needs to start with"),
            ("## [0.1.0](https://example.com/0.1.0)\n", "No older release"),
        ],
    )
    def test_insert_errors(changelog: str, section: str, message: str) -> None:
        """A section without a heading or older than everything is not inserted."""
        with pytest.raises(ValueError, match=message):
            insert(changelog, section)

    @pytest.mark.parametrize("value", ["0.12.0", "0.11.0.1"])
    def test_release_version_accepts(value: str) -> None:
        """Releases and patch releases are accepted."""
        assert _release_version(value) == value

    @pytest.mark.parametrize(
        "value",
        ["0.12", "0.12.0rc1", "0.12.0.dev1", "v0.12.0", "0.12.0.1.1", "0.12.00"],
    )
    def test_release_version_rejects(value: str) -> None:
        """Other version forms would not match the tag and branch names."""
        with pytest.raises(argparse.ArgumentTypeError):
            _release_version(value)

    def test_prepare_rejects_cherry_pick_without_patch_base() -> None:
        """Cherry-picks are rejected before anything is run."""
        with pytest.raises(ValueError, match="only be cherry-picked with --base patch"):
            prepare("0.12.0", "master", ["abc"])
