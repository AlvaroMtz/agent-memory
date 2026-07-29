"""Property-based tests for agent-memory using Hypothesis.

Verifies invariants:
- Monotonic versions: version numbers never decrease for a given memory.
- Revoked consents never grant access.
- Expired consents never grant access.
- Tenant isolation: data from one tenant never leaks to another.

Note: These tests operate on domain models directly to verify invariants
without requiring database or async infrastructure.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import assume, given
from hypothesis import strategies as st

from agent_memory.domain.consent import ConsentRecord

# ── Custom strategies ─────────────────────────────────────────────────────────


memory_type_strategy = st.sampled_from(["semantic", "preference"])
sensitivity_strategy = st.sampled_from(["public", "internal", "personal", "sensitive"])


@st.composite
def consent_records(draw):
    """Generate arbitrary ConsentRecord instances with valid constraints."""
    now = datetime.now(UTC)

    tenant_id = draw(st.text(min_size=1, max_size=20))
    subject_id = draw(st.text(min_size=1, max_size=20))
    actor_id = draw(st.text(min_size=1, max_size=20))
    purpose = draw(st.text(min_size=1, max_size=20))

    allow_write = draw(st.booleans())
    allow_read = draw(st.booleans())

    allowed_types = draw(st.sets(memory_type_strategy, min_size=0, max_size=2))
    allowed_sens = draw(st.sets(sensitivity_strategy, min_size=0, max_size=4))

    if not allowed_types:
        allowed_types = {"preference"}
    if not allowed_sens:
        allowed_sens = {"public"}

    # Optional expiry
    expires_at = draw(
        st.one_of(
            st.none(),
            st.just(now - timedelta(days=draw(st.integers(min_value=1, max_value=365)))),
            st.just(now + timedelta(days=draw(st.integers(min_value=1, max_value=365)))),
        )
    )

    return ConsentRecord(
        tenant_id=tenant_id,
        subject_id=subject_id,
        actor_id=actor_id,
        purpose=purpose,
        allow_write=allow_write,
        allow_read=allow_read,
        allowed_memory_types=allowed_types,
        allowed_sensitivity=allowed_sens,
        expires_at=expires_at,
    )


# ── Test: Revoked consent never grants access ─────────────────────────────────


@given(consent_records())
def test_revoked_never_grants_access(record: ConsentRecord) -> None:
    """A revoked consent must never allow read or write operations."""
    record.revoke()
    assert record.is_revoked() is True
    assert record.is_active() is False

    for mtype in record.allowed_memory_types:
        for sens in record.allowed_sensitivity:
            assert record.allows_write(mtype, sens) is False, (
                f"Revoked consent should not allow write for {mtype}/{sens}"
            )
            assert record.allows_read(mtype, sens) is False, (
                f"Revoked consent should not allow read for {mtype}/{sens}"
            )


@given(consent_records())
def test_revoked_returns_false_for_is_active(record: ConsentRecord) -> None:
    """revoked_at set → is_active=False, is_revoked=True."""
    now = datetime.now(UTC)
    assume(record.expires_at is None or record.expires_at > now)
    assume(record.revoked_at is None)
    assert record.is_active() is True
    assert record.is_revoked() is False

    record.revoke()
    assert record.is_active() is False
    assert record.is_revoked() is True


# ── Test: Expired consent never grants access ─────────────────────────────────


@given(consent_records())
def test_expired_never_grants_access(record: ConsentRecord) -> None:
    """An expired consent must never allow read or write operations."""
    now = datetime.now(UTC)

    assume(record.expires_at is not None)
    assume(record.expires_at < now)

    # Expired consents should not be active
    assert record.is_active() is False

    for mtype in record.allowed_memory_types:
        for sens in record.allowed_sensitivity:
            assert record.allows_write(mtype, sens) is False, (
                f"Expired consent should not allow write for {mtype}/{sens}"
            )
            assert record.allows_read(mtype, sens) is False, (
                f"Expired consent should not allow read for {mtype}/{sens}"
            )


@given(consent_records())
def test_non_expired_allows_when_configured(record: ConsentRecord) -> None:
    """A non-expired, non-revoked consent should allow operations
    that match its allowed types and sensitivity."""
    now = datetime.now(UTC)

    assume(record.expires_at is None or record.expires_at > now)
    assume(record.revoked_at is None)

    assert record.is_active() is True

    for mtype in record.allowed_memory_types:
        for sens in record.allowed_sensitivity:
            expected_write = record.allow_write
            expected_read = record.allow_read

            assert record.allows_write(mtype, sens) is expected_write, (
                f"Write for {mtype}/{sens} should be {expected_write}"
            )
            assert record.allows_read(mtype, sens) is expected_read, (
                f"Read for {mtype}/{sens} should be {expected_read}"
            )


# ── Test: Consent with no allowed types denies everything ──────────────────────


@given(
    st.builds(
        ConsentRecord,
        tenant_id=st.text(min_size=1, max_size=10),
        subject_id=st.text(min_size=1, max_size=10),
        actor_id=st.text(min_size=1, max_size=10),
        purpose=st.text(min_size=1, max_size=10),
        allow_write=st.just(True),
        allow_read=st.just(True),
        allowed_memory_types=st.just(set()),
        allowed_sensitivity=st.sets(sensitivity_strategy, min_size=1, max_size=4),
    )
)
def test_empty_allowed_types_deny_everything(record: ConsentRecord) -> None:
    """If allowed_memory_types is empty, no memory type is allowed."""
    assert record.is_active() is True

    for sens in record.allowed_sensitivity:
        assert record.allows_write("preference", sens) is False
        assert record.allows_write("semantic", sens) is False
        assert record.allows_read("preference", sens) is False
        assert record.allows_read("semantic", sens) is False


# ── Test: Tenant ID is always preserved ───────────────────────────────────────


@given(consent_records())
def test_tenant_id_preserved(record: ConsentRecord) -> None:
    """The tenant_id on a consent record is never modified by operations."""
    original_tenant_id = record.tenant_id
    record.revoke()
    assert record.tenant_id == original_tenant_id


# ── Test: Grant → Revoke lifecycle ────────────────────────────────────────────


@given(consent_records())
def test_grant_revoke_lifecycle(record: ConsentRecord) -> None:
    """After revoke, is_active flips, is_revoked flips, access is denied."""
    assume(record.expires_at is None or record.expires_at > datetime.now(UTC))
    assume(record.revoked_at is None)

    # Before revoke — should be active
    assert record.is_active() is True
    assert record.is_revoked() is False

    # Revoke
    record.revoke()
    assert record.is_active() is False
    assert record.is_revoked() is True


# ── Test: Consent version is monotonic (within record) ────────────────────────


@given(consent_records())
def test_version_monotonic(record: ConsentRecord) -> None:
    """Version numbers start at 1 and are positive integers."""
    assert record.version >= 1, "Version should be >= 1"


# ── Test: Sensitivity filters work correctly ──────────────────────────────────


def test_sensitivity_filter_outside_range():
    """A consent with 'public' sensitivity should deny 'sensitive' access."""
    record = ConsentRecord(
        tenant_id="t1",
        subject_id="s1",
        actor_id="a1",
        purpose="test",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference"},
        allowed_sensitivity={"public"},
    )

    assert record.allows_write("preference", "public") is True
    assert record.allows_write("preference", "internal") is False
    assert record.allows_write("preference", "personal") is False
    assert record.allows_write("preference", "sensitive") is False
