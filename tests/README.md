# Test fixture tiers

The test suite has two device-fixture tiers. The tiers keep cross-platform
compatibility coverage broad without multiplying every generic behavior test by
every captured device response.

## Representative suite

Run the representative suite with:

```console
uv run pytest --fixture-set representative
```

For each parametrized test function, pytest retains every non-device parameter
combination and selects up to six device fixtures. Selection is deterministic and
favors fixtures that add distinct protocols, models, parent/child roles,
components, component versions, discovery transports, and response shapes.
Small, explicitly parametrized regression fixture sets are retained in full.

This is the suite used for the Python and operating-system compatibility matrix.

## Full fixture suite

Run every collected device-fixture combination with:

```console
uv run pytest --fixture-set all
```

`all` is the local default so an unqualified `uv run pytest` remains exhaustive.
CI runs this tier once on the canonical Ubuntu/Python 3.14 environment with all
optional dependencies installed.

## Marker overrides

Use `all_fixtures` when a test is itself an exhaustive fixture contract and must
not be sampled in representative mode:

```python
@pytest.mark.all_fixtures
async def test_fixture_contract(dev):
    ...
```

Use `fixture_representatives(limit)` when a broad test needs a different maximum:

```python
@pytest.mark.fixture_representatives(20)
async def test_behavior_across_more_capabilities(dev):
    ...
```

Prefer a small explicit `@pytest.mark.parametrize` list for a regression tied to
specific fixture files. Pools at or below the representative limit are never
reduced.

Do not use representative selection as a substitute for a focused regression
test. When a fixture exists because of a particular bug, pin that fixture in the
regression test so the relationship remains visible in review.
