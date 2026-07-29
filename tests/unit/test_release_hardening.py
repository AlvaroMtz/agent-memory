"""Release-hardening tests for plugin factories and encrypted retrieval paths."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_memory.application.retrieve import _decrypt_evidence, _decrypt_value
from agent_memory.crypto import AESGCMEncryptionFactory, NoopEncryptionFactory
from agent_memory.crypto.aes_gcm import AESGCMEncryptionProvider
from agent_memory.crypto.noop import NoopEncryptionProvider
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.ports.encryption import EncryptionContext
from agent_memory.providers import (
    DeterministicEmbeddingFactory,
    FakeExtractorFactory,
    InMemoryBackendFactory,
    LangChainExtractorFactory,
    RuleBasedExtractorFactory,
)
from agent_memory.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from agent_memory.providers.fake_extractor import FakeExtractor
from agent_memory.providers.in_memory_backend import InMemoryBackend
from agent_memory.providers.langchain_extractor import LangChainStructuredExtractor
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor


@pytest.mark.asyncio
async def test_encryption_factories_create_working_providers() -> None:
    noop = NoopEncryptionFactory().create()
    aes = AESGCMEncryptionFactory().create("release-key")

    assert isinstance(noop, NoopEncryptionProvider)
    assert isinstance(aes, AESGCMEncryptionProvider)

    ctx = EncryptionContext(tenant_id="tenant-a", purpose="release", key_id="key-1")
    payload = await aes.encrypt(b"secret", context=ctx)

    assert await aes.decrypt(payload, context=ctx) == b"secret"


@pytest.mark.asyncio
async def test_provider_factories_create_importable_plugins() -> None:
    backend = await InMemoryBackendFactory().create()
    embedder = DeterministicEmbeddingFactory().create(dimensions=16)
    fake = FakeExtractorFactory().create()
    rules = RuleBasedExtractorFactory().create()

    assert isinstance(backend, InMemoryBackend)
    assert isinstance(embedder, DeterministicEmbeddingProvider)
    assert isinstance(fake, FakeExtractor)
    assert isinstance(rules, RuleBasedExtractor)
    assert len(await embedder.embed("same text")) == 16


@pytest.mark.asyncio
async def test_langchain_structured_extractor_accepts_ainvoke_candidates() -> None:
    candidate = MemoryCandidate(
        memory_type="preference",
        subject_key="code",
        predicate="code_language",
        value="Python",
        source_message_id="m1",
        evidence_text="I prefer Python",
    )

    class Runnable:
        async def ainvoke(self, payload):
            assert payload["subject_id"] == "subject-1"
            return {"candidates": [candidate.model_dump()]}

    extractor = LangChainStructuredExtractor(Runnable())

    result = await extractor.extract(
        messages=[{"id": "m1", "role": "user", "content": "I prefer Python"}],
        subject_id="subject-1",
    )

    assert result == [candidate]


@pytest.mark.asyncio
async def test_langchain_structured_extractor_accepts_sync_invoke_object() -> None:
    class Output:
        candidates = [
            {
                "memory_type": "semantic",
                "subject_key": "user",
                "predicate": "name",
                "value": "Ada",
                "source_message_id": "m1",
                "evidence_text": "My name is Ada",
            }
        ]

    class Runnable:
        def invoke(self, payload):
            return Output()

    result = await LangChainStructuredExtractor(Runnable()).extract(
        messages=[{"id": "m1", "role": "user", "content": "My name is Ada"}],
        subject_id="subject-1",
    )

    assert result[0].predicate == "name"
    assert result[0].value == "Ada"


def test_langchain_factory_fails_clearly_without_runnable() -> None:
    with pytest.raises(TypeError, match="runnable"):
        LangChainExtractorFactory().create()


@pytest.mark.asyncio
async def test_encrypted_retrieval_helpers_decrypt_value_and_evidence() -> None:
    provider = AESGCMEncryptionProvider("release-key")
    ctx = EncryptionContext(tenant_id="tenant-a", purpose="release", key_id="key-1")

    value_payload = await provider.encrypt(json.dumps({"language": "Python"}).encode(), context=ctx)
    evidence_payload = await provider.encrypt(b"I prefer Python", context=ctx)
    encrypted_value = {
        "encrypted": True,
        "algorithm": value_payload.algorithm,
        "key_id": value_payload.key_id,
        "ciphertext": base64.b64encode(value_payload.ciphertext).decode("ascii"),
        "nonce": base64.b64encode(value_payload.nonce or b"").decode("ascii"),
    }
    encrypted_evidence = json.dumps(
        {
            "encrypted": True,
            "algorithm": evidence_payload.algorithm,
            "key_id": evidence_payload.key_id,
            "ciphertext": base64.b64encode(evidence_payload.ciphertext).decode("ascii"),
            "nonce": base64.b64encode(evidence_payload.nonce or b"").decode("ascii"),
        }
    )

    assert await _decrypt_value(encrypted_value, provider, "tenant-a") == {"language": "Python"}
    assert await _decrypt_evidence(encrypted_evidence, provider, "tenant-a") == "I prefer Python"


@pytest.mark.asyncio
async def test_encrypted_retrieval_helpers_fail_closed_on_wrong_tenant() -> None:
    provider = AESGCMEncryptionProvider("release-key")
    ctx = EncryptionContext(tenant_id="tenant-a", purpose="release", key_id="key-1")
    value_payload = await provider.encrypt(json.dumps("secret").encode(), context=ctx)
    encrypted_value = {
        "encrypted": True,
        "algorithm": value_payload.algorithm,
        "key_id": value_payload.key_id,
        "ciphertext": base64.b64encode(value_payload.ciphertext).decode("ascii"),
        "nonce": base64.b64encode(value_payload.nonce or b"").decode("ascii"),
    }

    assert await _decrypt_value(encrypted_value, provider, "tenant-b") == encrypted_value


def test_retrieved_memory_shape_remains_structured() -> None:
    from agent_memory.domain.retrieval import RetrievedMemory

    memory = RetrievedMemory(
        id=uuid4(),
        version=1,
        memory_type="preference",
        predicate="code_language",
        value="Python",
        score=0.9,
        score_breakdown={"lexical": 1.0},
        confidence=0.95,
        source_type="user_explicit",
        sensitivity="public",
        created_at=datetime.now(UTC),
        evidence_text="I prefer Python",
    )

    assert memory.model_dump()["score_breakdown"] == {"lexical": 1.0}
