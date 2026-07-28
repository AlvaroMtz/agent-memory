# Proposal: agent-memory v0.0.1

> Governed Long-Term Memory for AI Agents

## Problem Statement

Los agentes de IA actuales carecen de memoria de largo plazo que sea segura,
verificable y controlada por el usuario. Las soluciones existentes son:

- **LangChain Memory**: efímera, sin control de consentimiento, sin multi-tenancy.
- **Mem0, RAG approaches**: sin garantías de aislamiento, sin versionado de memorias,
  sin control de alucinaciones al extraer, sin trazabilidad forense.
- **Bases vectoriales directas**: sin consentimiento, sin auditoría, sin políticas
  de retención, sin protección contra prompt injection vía contenido almacenado.

No existe un paquete que proporcione:

1. Consentimiento granulado y versionado.
2. Aislamiento multi-tenant probado adversarialmente.
3. Evidencia literal obligatoria en cada memoria.
4. Control de alucinaciones (no extraer del assistant).
5. Resolución de contradicciones con versionado append-only.
6. Cifrado configurable.
7. Retención y olvido programados.
8. Auditoría completa de cada operación.
9. Evaluación continua mediante datasets versionados y gates de release.

## Target Users

- **Desarrolladores LangChain/LangGraph** que necesitan memoria persistente y segura.
- **Platform teams** que construyen sistemas multi-tenant con agentes.
- **AI safety engineers** que necesitan garantías de aislamiento y trazabilidad.
- **Equipos regulados** (health, fintech, legal) con requisitos de consentimiento y auditoría.

## Business Outcomes

1. Un agente LangChain puede recordar preferencias de usuario entre sesiones.
2. Dos tenants completamente independientes no pueden filtrar memorias entre sí.
3. Sin consentimiento explícito, no se persiste ni recupera ninguna memoria.
4. Una afirmación del asistente nunca se convierte en memoria.
5. Cada memoria tiene evidencia literal verificable de su origen.
6. Las contradicciones crean nuevas versiones sin perder historia.
7. Calidad de extracción y recuperación medible mediante datasets reproducibles en CI.

## Non-Goals (v0.0.1)

- Aprendizaje autónomo de instrucciones.
- Activación automática de memoria procedural.
- Dashboard empresarial.
- Cluster distribuido / Kafka.
- SDK TypeScript.
- Backends no-PostgreSQL (Redis, MongoDB).
- Resolución avanzada de identidades.
- Entrenamiento de modelos.
- Inferencia automática de atributos sensibles.
- Alta disponibilidad gestionada por el paquete.

## Product Constraints

- Python 3.11, 3.12, 3.13.
- PostgreSQL 16/17 + pgvector.
- LangChain v1 y LangGraph.
- API asíncrona principal, fachada síncrona opcional.
- Sin dependencias de servicios externos en CI.
- Todos los tests ejecutables sin Internet ni API keys.
- Proveedores deterministas para tests incluidos.

## Key Principles

1. **Fail closed**: sin tenant_id, consentimiento, o autorización → denegar.
2. **Deny by default**: consentimiento default deny, memoria procedural desactivada.
3. **El modelo no controla la seguridad**: tenant/subject/actor/keys vienen del contexto autenticado.
4. **La memoria es contenido no confiable**: nunca concatenar al system prompt directamente.
5. **Tests antes o junto a la implementación**: datasets y tests adversariales obligatorios.

## Architecture Concept

Hexagonal architecture (ports & adapters):

```
LangChain/LangGraph → Middleware → MemoryClient → Application Services → Domain → Ports → Adapters (PostgreSQL + pgvector, Deterministic, AES-GCM, OpenTelemetry)
```

El dominio no depende de LangChain, PostgreSQL, OpenAI, ni pgvector.

## Delivery Strategy

8 fases secuenciales:
1. Dominio y contratos
2. Proveedores deterministas
3. PostgreSQL + RLS
4. Consentimiento y seguridad
5. Extracción y recuperación
6. Memory Lab (GUI)
7. Integración LangChain
8. Empaquetado y release v0.0.1

## Open Questions for the User

1. El workspace actual es `langouste` — ¿querés crear `agent-memory` como proyecto separado dentro del mismo repo `dumbo`, o en un repositorio independiente?
2. ¿Preferís que `agent-memory` se desarrolle en este mismo worktree o en un worktree separado?
3. ¿Tenés preferencia sobre el schema de base de datos (`agent_memory` por defecto)?