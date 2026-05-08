// TrustGraph Pure Model — :Node, :Literal, :Rel
CREATE INDEX FOR (n:Node) ON (n.uri);
CREATE INDEX FOR (n:Node) ON (n.collection);
CREATE INDEX FOR (l:Literal) ON (l.value, l.collection);
CREATE INDEX FOR (l:Literal) ON (l.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.uri);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.collection, r.uri);
CALL db.idx.fulltext.createNodeIndex('Node', 'uri');
CREATE INDEX FOR ()-[r:Rel]-() ON (r.confidence);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.extraction_method);
CREATE INDEX FOR (n:Node) ON (n.merged);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.has_contradiction);
