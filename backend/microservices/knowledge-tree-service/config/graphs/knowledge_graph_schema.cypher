// Unified Knowledge Graph Schema for FalkorDB
// Node labels are implicit — this file defines indexes for performance.

CREATE INDEX FOR (d:Document) ON (d.tenant_id);
CREATE INDEX FOR (d:Document) ON (d.document_id);
CREATE INDEX FOR (f:Folder) ON (f.tenant_id);
CREATE INDEX FOR (e:Entity) ON (e.tenant_id, e.normalized_name);
CREATE INDEX FOR (e:Entity) ON (e.entity_type);
CREATE INDEX FOR (c:Claim) ON (c.tenant_id);
CREATE INDEX FOR (et:EntityType) ON (et.name);
CREATE INDEX FOR (dm:DocumentMemory) ON (dm.document_id);
CALL db.idx.fulltext.createNodeIndex('Document', 'title');
CALL db.idx.fulltext.createNodeIndex('Entity', 'name');
