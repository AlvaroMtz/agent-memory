# Production Checklist

Before production use:

- [ ] Use PostgreSQL with pgvector installed.
- [ ] Apply migrations successfully.
- [ ] Verify RLS and FORCE RLS on tenant-scoped tables.
- [ ] Use an execution role that is not table owner and has no `BYPASSRLS`.
- [ ] Set tenant and actor context inside every transaction.
- [ ] Use production encryption; never use `noop`.
- [ ] Set consent default to `deny`.
- [ ] Disable fake and rule-based extractors as primary production providers.
- [ ] Run security datasets and release gates with coverage data generated first
  (`make release-check` or equivalent CI steps).
- [ ] Verify no audit/telemetry output includes secrets, decrypted values,
  evidence text or credentials.
- [ ] Document retention and deletion policy for each purpose.
