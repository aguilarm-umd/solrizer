from pathlib import Path
from unittest.mock import MagicMock

import httpretty
import pytest
from plastron.models.authorities import VocabularyTerm, Subject
from plastron.models.umd import Item
from plastron.namespaces import umdtype, rdf, xsd, dcterms, owl
from plastron.rdfmapping.properties import RDFDataProperty, RDFObjectProperty
from plastron.rdfmapping.resources import RDFResource
from plastron.repo import Repository, RepositoryResource
from plastron.validation.vocabularies import Vocabulary
from rdflib import URIRef, Literal

from solrizer.indexers import IndexerError
from solrizer.indexers.content_model import get_model_fields, get_data_fields, shorten_uri, get_object_fields, \
    language_suffix


@pytest.mark.parametrize(
    ('uri', 'expected_value'),
    [
        (None, None),
        ('http://purl.org/dc/terms/title', 'dcterms:title'),
        ('http://example.com/foobar', 'http://example.com/foobar'),
    ]
)
def test_shorten_uri(uri, expected_value):
    assert shorten_uri(uri) == expected_value


@pytest.mark.parametrize(
    ('language', 'expected_value'),
    [
        (None, ''),
        ('en', '_en'),
        ('en-US', '_en_us'),
        ('ja-Latn', '_ja_latn'),
        ('jpn-LATN', '_ja_latn'),
        ('ger', '_de'),
    ]
)
def test_language_suffix(language, expected_value):
    assert language_suffix(language) == expected_value


def test_invalid_language_suffix():
    with pytest.raises(IndexerError):
        language_suffix('invalid::tag')


@pytest.mark.parametrize(
    ('attr_name', 'datatype', 'repeatable', 'values', 'expected_fields'),
    [
        ('title', None, False, ['Foobar'], {'title__txt': 'Foobar'}),
        ('date', None, False, ['2024-08'], {'date__edtf': '2024-08'}),
        ('identifier', None, False, ['foobar'], {'identifier__id': 'foobar'}),
        ('handle', umdtype.handle, False, ['hdl:1903.1/123'], {'handle__id': 'hdl:1903.1/123'}),
        ('accession_number', umdtype.accessionNumber, False, ['123'], {'accession_number__id': '123'}),
        ('size', xsd.int, False, ['59'], {'size__int': 59}),
        ('size', xsd.integer, False, ['59'], {'size__int': 59}),
        ('size', xsd.long, False, ['59'], {'size__int': 59}),
        ('timestamp', xsd.dateTime, False, ['2024-08-16'], {'timestamp__dt': '2024-08-16'}),
        (
            'value',
            None,
            False,
            [Literal('dog'), Literal('dog', lang='en'), Literal('der Hund', lang='de')],
            {
                'value__txt': 'dog',
                'value__txt_en': 'dog',
                'value__txt_de': 'der Hund',
            },
        ),
        ('value', None, True, ['a', 'b', 'c'], {'value__txts': ['a', 'b', 'c']}),
    ]
)
def test_get_data_properties(attr_name, datatype, repeatable, values, expected_fields):
    # repo = Repository(client=Client(endpoint=Endpoint('http://example.com/fcrepo')))
    resource = RDFResource(uri='http://example.com/fcrepo/foo')
    prop = RDFDataProperty(
        resource=resource,
        attr_name=attr_name,
        predicate=rdf.value,
        repeatable=repeatable,
        datatype=datatype,
    )
    prop.update(Literal(v, datatype=datatype) for v in values)
    fields = get_data_fields(prop)
    if repeatable:
        # multivalued fields are not guaranteed to come out of the RDF in the
        # same order they went in, so we just want to compare the values as sets
        # instead of lists
        for k, v in fields.items():
            assert set(v) == set(expected_fields[k])
    else:
        assert fields == expected_fields


def test_object_property_simple_no_curie():
    resource = RDFResource(uri='http://example.com/fcrepo/foo')
    prop = RDFObjectProperty(
        resource=resource,
        attr_name='same_as',
        predicate=owl.sameAs,
    )
    prop.add(URIRef('http://example.net/thing'))
    repo = MagicMock(spec=Repository)
    fields = get_object_fields(prop, repo)
    assert fields['same_as__uri'] == 'http://example.net/thing'
    assert fields['same_as__curie'] == 'http://example.net/thing'


def test_object_property_simple_with_curie():
    resource = RDFResource(uri='http://example.com/fcrepo/foo')
    prop = RDFObjectProperty(
        resource=resource,
        attr_name='same_as',
        predicate=owl.sameAs,
    )
    prop.add(URIRef('http://purl.org/dc/terms/Image'))
    repo = MagicMock(spec=Repository)
    fields = get_object_fields(prop, repo)
    assert fields['same_as__uri'] == 'http://purl.org/dc/terms/Image'
    assert fields['same_as__curie'] == 'dcterms:Image'


@httpretty.activate
def test_object_property_from_vocabulary(datadir: Path):
    httpretty.register_uri(
        method=httpretty.GET,
        uri='http://vocab.lib.umd.edu/collection#',
        body=(datadir / 'collection.json').read_text(),
        adding_headers={'Content-Type': 'application/ld+json'},
    )
    resource = RDFResource(uri='http://example.com/fcrepo/foo')
    prop = RDFObjectProperty(
        resource=resource,
        attr_name='archival_collection',
        predicate=dcterms.isPartOf,
        object_class=VocabularyTerm,
        values_from=Vocabulary('http://vocab.lib.umd.edu/collection#'),
    )
    prop.add(URIRef('http://vocab.lib.umd.edu/collection#0051-MDHC'))
    repo = MagicMock(spec=Repository)
    fields = get_object_fields(prop, repo)
    assert fields['archival_collection__uri'] == 'http://vocab.lib.umd.edu/collection#0051-MDHC'
    assert fields['archival_collection__curie'] == 'http://vocab.lib.umd.edu/collection#0051-MDHC'
    assert fields['archival_collection__label__txt'] == 'Maryland Conservation Council records'
    assert fields['archival_collection__same_as__uris'] == ['http://hdl.handle.net/1903.1/1720']


def test_object_property_embedded():
    resource = RDFResource(uri='http://example.com/fcrepo/foo')
    prop = RDFObjectProperty(
        resource=resource,
        attr_name='subject',
        predicate=dcterms.subject,
        embedded=True,
        object_class=Subject,
    )
    prop.add(Subject(
        uri=URIRef('http://example.com/fcrepo/foo#subject'),
        label=Literal('Test'),
    ))
    repo = MagicMock(spec=Repository)
    fields = get_object_fields(prop, repo)
    assert fields['subject'] == [{'id': 'http://example.com/fcrepo/foo#subject', 'subject__label__txt': 'Test'}]


def test_object_property_linked():
    resource = RDFResource(uri='http://example.com/fcrepo/foo')
    prop = RDFObjectProperty(
        resource=resource,
        attr_name='subject',
        predicate=dcterms.subject,
        object_class=Subject,
    )
    prop.add(URIRef('http://example.com/fcrepo/foo/bar'))
    repo = MagicMock(spec=Repository)
    repo_resource = MagicMock(spec=RepositoryResource)
    repo.__getitem__.return_value = repo_resource
    repo_resource.read.return_value = repo_resource
    repo_resource.describe.return_value = Subject(
        uri=URIRef('http://example.com/fcrepo/foo/bar'),
        label=Literal('Bar'),
    )
    fields = get_object_fields(prop, repo)
    assert fields['subject'] == [{'id': 'http://example.com/fcrepo/foo/bar', 'subject__label__txt': 'Bar'}]


def test_get_model_fields():
    item = Item(
        title=Literal('Test Object'),
        handle=Literal('hdl:1903.1/123', datatype=umdtype.handle),
        accession_number=Literal('123', datatype=umdtype.accessionNumber),
        date=Literal('2024-08'),
        identifier=Literal('tst-123'),
        archival_collection=URIRef('http://vocab.lib.umd.edu/collection#0051-MDHC'),
    )
    repo = MagicMock(spec=Repository)
    expected_fields = {
        'rdf_type__uris': ['http://vocab.lib.umd.edu/model#Item', 'http://pcdm.org/models#Object'],
        'rdf_type__curies': ['umd:Item', 'pcdm:Object'],
        'title__txt': 'Test Object',
        'accession_number__id': '123',
        'date__edtf': '2024-08',
        'handle__id': 'hdl:1903.1/123',
        'identifier__ids': ['tst-123'],
        'archival_collection__uri': 'http://vocab.lib.umd.edu/collection#0051-MDHC',
        'archival_collection__curie': 'http://vocab.lib.umd.edu/collection#0051-MDHC',
        'archival_collection__label__txt': 'Maryland Conservation Council records',
        'archival_collection__same_as__uris': ['http://hdl.handle.net/1903.1/1720'],
        'archival_collection__same_as__curies': ['http://hdl.handle.net/1903.1/1720'],
    }
    fields = get_model_fields(item, repo)
    for k, v in fields.items():
        if isinstance(v, list):
            assert set(v) == set(expected_fields[k])
        else:
            assert v == expected_fields[k]
