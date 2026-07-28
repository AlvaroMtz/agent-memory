"""Custom encryption provider example — implement and use a custom provider.

Run: python examples/custom_provider/custom_provider.py
"""

import asyncio

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext
from agent_memory.ports.encryption import EncryptionProvider
from agent_memory.providers.in_memory_backend import InMemoryBackend
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor


class Rot13Encryption(EncryptionProvider):
    """A simple ROT-13 encryption provider (demonstration only)."""

    def encrypt(self, plaintext: str) -> bytes:
        result = []
        for ch in plaintext:
            if "a" <= ch <= "z":
                result.append(chr((ord(ch) - ord("a") + 13) % 26 + ord("a")))
            elif "A" <= ch <= "Z":
                result.append(chr((ord(ch) - ord("A") + 13) % 26 + ord("A")))
            else:
                result.append(ch)
        return "".join(result).encode("utf-8")

    def decrypt(self, ciphertext: bytes) -> str:
        plain = ciphertext.decode("utf-8")
        result = []
        for ch in plain:
            if "a" <= ch <= "z":
                result.append(chr((ord(ch) - ord("a") - 13) % 26 + ord("a")))
            elif "A" <= ch <= "Z":
                result.append(chr((ord(ch) - ord("A") - 13) % 26 + ord("A")))
            else:
                result.append(ch)
        return "".join(result)


async def main():
    encryption = Rot13Encryption()
    backend = InMemoryBackend()
    extractor = RuleBasedExtractor()
    client = MemoryClient(backend, extractor=extractor)

    context = MemoryContext(
        tenant_id="t1",
        subject_id="user-1",
        actor_id="assistant-1",
        purpose="general",
    )

    original = "Secreto: prefiero respuestas cortas"
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    print(f"Original:  {original}")
    print(f"Encrypted: {encrypted!r}")
    print(f"Decrypted: {decrypted}")

    result = await client.remember(original, context)
    print(f"Remembered: {len(result)} memories")

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())