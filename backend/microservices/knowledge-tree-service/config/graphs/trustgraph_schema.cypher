// TrustGraph Pure Model — :Node, :Literal, :Rel
CREATE INDEX FOR (n:Node) ON (n.uri);
CREATE INDEX FOR (n:Node) ON (n.user, n.collection);
CREATE INDEX FOR (l:Literal) ON (l.value, l.user, l.collection);
CREATE INDEX FOR (l:Literal) ON (l.user, l.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.uri);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection, r.uri);
CREATE INDEX FOR (c:CollectionMetadata) ON (c.user, c.collection);
CALL db.idx.fulltext.createNodeIndex('Node', 'uri');
