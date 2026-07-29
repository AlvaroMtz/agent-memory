# Datasets

Datasets live under `datasets/` and are YAML files validated with Pydantic.

Each scenario should include:

- context: tenant, subject and purpose;
- consent configuration;
- messages with explicit roles;
- expected candidates;
- expected persistence state;
- expected queries and forbidden retrievals;
- expected audit events where relevant.

Run a dataset with:

```bash
agent-memory scenario run datasets/extraction/role-filtering.yaml
agent-memory eval run --path datasets/extraction/role-filtering.yaml
```

Datasets are product artifacts, not test afterthoughts. If extraction or
retrieval behavior changes, add or update a scenario in the same change.
