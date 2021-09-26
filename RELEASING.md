1. Set release information

```bash
# export PREVIOUS_RELEASE=$(git describe --abbrev=0)
export PREVIOUS_RELEASE=0.3.5 # generate the full changelog since last pyhs100 release
export NEW_RELEASE=0.4.0.dev4
```

2. Update the version number

```bash
poetry version $NEW_RELEASE
```

3. Generate changelog

```bash
# gem install github_changelog_generator --pre
# https://github.com/github-changelog-generator/github-changelog-generator#github-token
export CHANGELOG_GITHUB_TOKEN=token
github_changelog_generator --base HISTORY.md --user python-kasa --project python-kasa --since-tag $PREVIOUS_RELEASE --future-release $NEW_RELEASE -o CHANGELOG.md
```

3. Write a short and understandable summary for the release.

4. Commit the changed files

```bash
git commit -av
```

5. Create a PR for the release.

6. Get it merged, fetch the upstream master

```bash
git checkout master
git fetch upstream
git rebase upstream/master
```

7. Tag the release (add short changelog as a tag commit message), push the tag to git

```bash
git tag -a $NEW_RELEASE
git push upstream $NEW_RELEASE
```

All tags on master branch will trigger a new release on pypi.

8. Click the "Draft a new release" button on github, select the new tag and copy & paste the changelog into the description.
