"""Tests for URIBuilder — canonical URI generation with entity name normalization."""

import pytest

from app.services.uri_builder import URIBuilder


class TestEntityURI:
    def test_basic_person(self):
        assert URIBuilder.entity("default", "Juan García López") == "nouxcube://entity/default/juan-garcia-lopez"

    def test_strips_accents(self):
        assert URIBuilder.entity("default", "José María Azañón") == "nouxcube://entity/default/jose-maria-azanon"

    def test_lowercases(self):
        # "SL" is stripped as a corporate suffix — canonical form omits it
        assert URIBuilder.entity("default", "ACME CORP SL") == "nouxcube://entity/default/acme-corp"

    def test_strips_extra_whitespace(self):
        assert URIBuilder.entity("default", "  Juan   García  ") == "nouxcube://entity/default/juan-garcia"

    def test_strips_punctuation(self):
        assert URIBuilder.entity("default", "García, Juan (DNI: 12345678A)") == "nouxcube://entity/default/garcia-juan-dni-12345678a"

    def test_different_collections(self):
        assert URIBuilder.entity("nominas-2025", "Juan García") == "nouxcube://entity/nominas-2025/juan-garcia"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="empty"):
            URIBuilder.entity("default", "")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            URIBuilder.entity("default", "   ")


class TestDocumentURI:
    def test_basic(self):
        assert URIBuilder.document("default", "doc-123") == "nouxcube://document/default/doc-123"

    def test_preserves_document_id_case(self):
        assert URIBuilder.document("default", "ABC-123-DEF") == "nouxcube://document/default/ABC-123-DEF"


class TestFolderURI:
    def test_basic(self):
        uri = URIBuilder.folder("default", "/Empleados/Juan Garcia")
        assert uri.startswith("nouxcube://folder/default/")
        assert len(uri.split("/")[-1]) == 16  # 16-char hex hash

    def test_same_path_same_uri(self):
        assert URIBuilder.folder("default", "/Empleados/Juan") == URIBuilder.folder("default", "/Empleados/Juan")

    def test_different_path_different_uri(self):
        assert URIBuilder.folder("default", "/Empleados/Juan") != URIBuilder.folder("default", "/Clientes/ACME")


class TestPredicateURI:
    def test_core_predicate(self):
        assert URIBuilder.predicate("core", "type") == "nouxcube://predicate/core/type"

    def test_legal_predicate(self):
        assert URIBuilder.predicate("legal", "empleado-de") == "nouxcube://predicate/legal/empleado-de"


class TestExtractionURI:
    def test_generates_uuid(self):
        uri = URIBuilder.extraction()
        assert uri.startswith("nouxcube://extraction/")
        assert len(uri.split("/")[-1]) == 36  # UUID length

    def test_each_call_unique(self):
        assert URIBuilder.extraction() != URIBuilder.extraction()


class TestContradictionURI:
    def test_generates_uuid(self):
        uri = URIBuilder.contradiction()
        assert uri.startswith("nouxcube://contradiction/")
        assert len(uri.split("/")[-1]) == 36

    def test_each_call_unique(self):
        assert URIBuilder.contradiction() != URIBuilder.contradiction()


class TestDBRowURI:
    def test_basic(self):
        assert URIBuilder.dbrow("conn-1", "employees", "42") == "nouxcube://dbrow/conn-1/employees/42"


class TestNormalizeName:
    def test_spanish_articles_kept(self):
        assert URIBuilder.normalize_name("María de los Ángeles") == "maria-de-los-angeles"

    def test_n_tilde_to_n(self):
        assert URIBuilder.normalize_name("Año Nuevo Muñoz") == "ano-nuevo-munoz"

    def test_numbers_preserved(self):
        assert URIBuilder.normalize_name("Ley 39/2015") == "ley-39-2015"

    def test_empty_string_returns_empty(self):
        assert URIBuilder.normalize_name("") == ""

    def test_only_symbols_returns_empty(self):
        assert URIBuilder.normalize_name("---") == ""
