# Delivery Plan: agent-memory v0.0.1

## Strategy: Chained PRs via Worktrees Paralelos

### Dependencies entre fases
```
Phase 1 (Domain) ─┬── Phase 2 (Deterministic) ──┐
                   ├── Phase 3 (PostgreSQL) ─────┤
                   │                             ├── Phase 4 (Consent+Security) ──┬── Phase 5 (Extraction+Retrieval) ──┬── Phase 6 (Lab) ──┐
                   └─────────────────────────────┘                               │                                   └── Phase 7 (LC)──┤
                                                                                  └──────────────────────────────────────────────────────┴── Phase 8 (Release)
```

### Waves

#### Wave 1: Fundación (1 worktree)
- **Worktree A**: Phase 1 (domain + contracts) + Phase 2 (deterministic providers)
- PR #1: Domain, contracts, proveedores deterministas
- Estimado: ~650 lines

#### Wave 2: Infraestructura (1 worktree)
- **Worktree B**: Phase 3 (PostgreSQL + RLS) + Phase 4 (consent + security + encryption)
- PR #2: Backend PostgreSQL, RLS, cifrado, consentimiento
- Estimado: ~1300 lines (puede dividirse en 2 PRs si es necesario)

#### Wave 3: Core Intelligence (1 worktree)
- **Worktree C**: Phase 5 (extraction + retrieval + contradictions)
- PR #3: Pipeline de extracción, recuperación híbrida, resolución de contradicciones
- Estimado: ~700 lines

#### Wave 4: Interfaces (2 worktrees paralelos)
- **Worktree D**: Phase 6 (Memory Lab)
- **Worktree E**: Phase 7 (LangChain integration)
- PR #4: Memory Lab
- PR #5: Middleware LangChain
- Estimado: ~1200 lines

#### Wave 5: Release (1 worktree)
- **Worktree F**: Phase 8 (CLI, packaging, CI, docs, release gates)
- PR #6: CLI completa, CI, documentación, release v0.0.1
- Estimado: ~500 lines

### Total: 6 PRs | ~4350 lines | ~800 lines avg/PR

Cada PR es autónomo: se aplica → verifica → sync → mergea antes del siguiente.
Los worktrees en Wave 4 son paralelos porque Phase 6 y Phase 7 solo dependen de Phase 5.