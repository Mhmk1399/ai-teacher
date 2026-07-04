# ADR-004: Relational representation of the competency graph

- Status: Accepted
- Date: 2026-06-23

## Context
The competency graph has prerequisite relationships and could suggest a graph
database. We have no traversal-heavy requirement yet.

## Decision
Represent the graph **relationally**: `competency_definitions` nodes plus a
`competency_prerequisites` edge table (`competency_id`,
`prerequisite_competency_id`, `relationship_type`, `weight`). No graph DB, no
vector DB.

## Consequences
- Works on SQLite now and PostgreSQL later; standard migrations and FKs.
- Prerequisite checks are simple joins/recursive queries — sufficient at this
  scale. Revisit only with a concrete traversal/retrieval requirement.
