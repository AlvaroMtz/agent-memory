# Proposal: agent-memory v0.0.1 Compliance Hardening

## Problem Statement

The repository contains many components required by the `agent-memory` v0.0.1 master spec, but current behavior does not prove or provide the full security and evaluation guarantees.

The most dangerous issue is not missing code alone; it is **false confidence**. Some release gates pass while validating weak or configured-only conditions. For a governed long-term memory system, that is not acceptable. Consent, tenant isolation, evidence, encryption, prompt-injection resistance, and evaluation are not optional infrastructure; they are the product.

## Goals

- Bring the implementation into measurable compliance with the master spec.
- Replace weak scenario checks with executable, adversarial, fail-closed tests.
- Ensure release gates fail when guarantees are absent, bypassed, simulated, or unmeasured.
- Complete the critical runtime paths: LangChain v1 integration, encrypted retrieval, Memory Lab workflows, and PostgreSQL/RLS hardening.

## Non-Goals

- Add unrelated product features beyond v0.0.1.
- Add a React dashboard or enterprise UI.
- Support non-PostgreSQL production backends.
- Implement distributed processing, Kafka, Redis, TypeScript SDK, or advanced identity resolution.
- Relax security guarantees to make tests easier.

## Scope

This change covers:

1. LangChain v1 compatibility and middleware correctness.
2. Retrieval decryption and fail-closed behavior.
3. Scenario runner correctness and release gate hardening.
4. Mandatory dataset coverage.
5. Memory Lab compliance workflows.
6. PostgreSQL/RLS doctor and integration checks.
7. Versioning and contradiction alignment with the master spec.
8. CI changes to make security/evaluation gates independent and meaningful.

## Risk

High. These changes touch the security frontier. Implementation must proceed in small, testable slices. Every new behavior requires a failing test or dataset scenario first or in the same change.

## Rollout Strategy

Use chained PRs/waves:

1. Evaluation truthfulness: runner, datasets, gates.
2. Runtime guarantees: encryption retrieval, consent, versioning, RLS checks.
3. LangChain v1 middleware.
4. Memory Lab.
5. CI/release hardening and documentation.
