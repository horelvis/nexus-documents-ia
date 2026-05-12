// Example audit / analytics queries against the :Trace subgraph
// (Pieza C of the TrustGraph Provenance DAG).
//
// Run inside the FalkorDB container, e.g.:
//   docker compose exec falkordb redis-cli -p 6379 GRAPH.QUERY knowledge_graph "<query>"
//
// All queries filter on collection='default' to avoid mixing scopes.

// ──────────────────────────────────────────────────────────────────────
// Q1. Recent traces for a specific thread — useful for replaying a
//     conversation's reasoning history after Redis 24h TTL expires.
// ──────────────────────────────────────────────────────────────────────
MATCH (t:Trace {collection: 'default'})
WHERE t.thread_id = '<THREAD_ID>'
RETURN t.msg_index AS idx,
       t.created_at AS ts,
       t.total_execution_ms AS ms,
       t.sources_cited AS cited,
       substring(t.answer, 0, 120) AS preview
ORDER BY t.msg_index DESC
LIMIT 20;


// ──────────────────────────────────────────────────────────────────────
// Q2. Tool usage frequency + median latency across all traces.
//     Lets ops see which tools are hot paths and whether any specific
//     tool drags up overall latency.
// ──────────────────────────────────────────────────────────────────────
MATCH (t:Trace {collection: 'default'})
      -[:Rel {uri: 'nouxcube://predicate/trace/used-tool',
              collection: 'default'}]
      ->(lit:Literal)
WITH lit.value AS tool, collect(t.total_execution_ms) AS latencies
RETURN tool,
       size(latencies) AS invocations,
       reduce(s = 0, x IN latencies | s + x) / size(latencies) AS avg_ms
ORDER BY invocations DESC;


// ──────────────────────────────────────────────────────────────────────
// Q3. Most-touched entities — which knowledge-graph nodes are reached
//     most often by the agent. Combined with the regular core/label
//     predicate, you get a ranking by human-readable name. Useful
//     for identifying hot entities + candidate caching targets.
// ──────────────────────────────────────────────────────────────────────
MATCH (t:Trace {collection: 'default'})
      -[:Rel {uri: 'nouxcube://predicate/trace/touched-entity',
              collection: 'default'}]
      ->(e:Node)
OPTIONAL MATCH (e)-[:Rel {uri: 'nouxcube://predicate/core/label',
                          collection: 'default'}]
              ->(lab:Literal)
WITH e, collect(lab.value)[0] AS label, count(t) AS touches
RETURN e.uri AS entity_uri,
       label,
       touches
ORDER BY touches DESC
LIMIT 30;


// ──────────────────────────────────────────────────────────────────────
// Q4 (bonus). Chunks cited as evidence most often — surfaces which
//     specific document chunks the agent keeps returning to.
// ──────────────────────────────────────────────────────────────────────
MATCH (t:Trace {collection: 'default'})
      -[:Rel {uri: 'nouxcube://predicate/trace/cited-chunk',
              collection: 'default'}]
      ->(c:Chunk)
OPTIONAL MATCH (c)-[:Rel {uri: 'nouxcube://predicate/core/of-document',
                          collection: 'default'}]
              ->(d:Node)
WITH c, d, count(t) AS cites
RETURN c.uri AS chunk_uri,
       c.offset AS offset,
       d.uri AS document_uri,
       cites
ORDER BY cites DESC
LIMIT 30;


// ──────────────────────────────────────────────────────────────────────
// Q5 (bonus). Full trace replay — pull a single trace's timeline in
//     order with all linked entities and chunks. Equivalent to
//     `GET /traces/{thread_id}/{message_index}` but in Cypher.
// ──────────────────────────────────────────────────────────────────────
MATCH (t:Trace {uri: 'nouxcube://trace/default/<THREAD_ID>/<MSG_IDX>'})
OPTIONAL MATCH (t)-[:Rel {uri: 'nouxcube://predicate/trace/has-step',
                          collection: 'default'}]->(st:TraceStep)
OPTIONAL MATCH (t)-[:Rel {uri: 'nouxcube://predicate/trace/touched-entity',
                          collection: 'default'}]->(e:Node)
OPTIONAL MATCH (t)-[:Rel {uri: 'nouxcube://predicate/trace/cited-chunk',
                          collection: 'default'}]->(c:Chunk)
RETURN t.thread_id, t.msg_index, t.total_execution_ms,
       collect(DISTINCT {idx: st.step_idx, type: st.type, content: st.content})
           AS steps,
       collect(DISTINCT e.uri) AS entities,
       collect(DISTINCT c.uri) AS chunks;
