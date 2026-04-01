"""Tests for canonical name resolution — honorific prefix and corporate suffix stripping."""

import pytest
from app.services.uri_builder import URIBuilder


class TestHonorificStripping:
    def test_d_dot_prefix(self):
        assert URIBuilder.normalize_name("D. Carlos Ruiz") == "carlos-ruiz"

    def test_dna_dot_prefix(self):
        assert URIBuilder.normalize_name("Dña. María López") == "maria-lopez"

    def test_don_prefix(self):
        assert URIBuilder.normalize_name("Don Pedro García") == "pedro-garcia"

    def test_dona_prefix(self):
        assert URIBuilder.normalize_name("Doña Ana Martínez") == "ana-martinez"

    def test_sr_prefix(self):
        assert URIBuilder.normalize_name("Sr. José Fernández") == "jose-fernandez"

    def test_sra_prefix(self):
        assert URIBuilder.normalize_name("Sra. Carmen Rodríguez") == "carmen-rodriguez"

    def test_dr_prefix(self):
        assert URIBuilder.normalize_name("Dr. Miguel Sánchez") == "miguel-sanchez"

    def test_dra_prefix(self):
        assert URIBuilder.normalize_name("Dra. Laura Gómez") == "laura-gomez"

    def test_no_false_positive_on_daniel(self):
        assert URIBuilder.normalize_name("Daniel Ruiz") == "daniel-ruiz"

    def test_no_false_positive_on_dragones(self):
        assert URIBuilder.normalize_name("Dragones S.L.") == "dragones"

    def test_multiple_prefixes_stripped(self):
        # Only one pass of stripping — "D. Don Carlos" strips "D." leaving "Don Carlos"
        assert URIBuilder.normalize_name("D. Don Carlos") == "don-carlos"

    def test_entity_uri_dedup(self):
        uri1 = URIBuilder.entity("default", "D. Carlos Ruiz Fernández")
        uri2 = URIBuilder.entity("default", "Carlos Ruiz Fernández")
        assert uri1 == uri2


class TestCorporateSuffixStripping:
    def test_sl_suffix(self):
        assert URIBuilder.normalize_name("ACME S.L.") == "acme"

    def test_sa_suffix(self):
        assert URIBuilder.normalize_name("TechCorp S.A.") == "techcorp"

    def test_slu_suffix(self):
        assert URIBuilder.normalize_name("Gestiones SLU") == "gestiones"

    def test_sc_suffix(self):
        assert URIBuilder.normalize_name("Cooperativa S.C.") == "cooperativa"

    def test_no_false_positive_on_short_names(self):
        assert URIBuilder.normalize_name("Basel") == "basel"

    def test_entity_uri_dedup(self):
        uri1 = URIBuilder.entity("default", "ACME S.L.")
        uri2 = URIBuilder.entity("default", "ACME")
        assert uri1 == uri2


class TestExistingNormalizationPreserved:
    def test_comma_reorder(self):
        assert URIBuilder.normalize_name("García, Juan") == "juan-garcia"

    def test_accents_stripped(self):
        assert URIBuilder.normalize_name("José María Azañón") == "jose-maria-azanon"

    def test_spanish_articles_kept(self):
        assert URIBuilder.normalize_name("María de los Ángeles") == "maria-de-los-angeles"

    def test_numbers_preserved(self):
        assert URIBuilder.normalize_name("Ley 39/2015") == "ley-39-2015"
