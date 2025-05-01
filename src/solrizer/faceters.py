"""
The following table lists the faceters implemented in this module, and which
properties they are based on for the different content models.

| Faceter Class             | Facet                 | Item                        | Letter                   | Poster                   | Issue                    |
|---------------------------|-----------------------|-----------------------------|--------------------------|--------------------------|--------------------------|
| `ArchivalCollectionFacet` | `archival_collection` | `archival_collection.label` | `part_of.label`          | `part_of`                | —                        |
| `ContributorFacet`        | `contributor`         | `contributor.label`         | —                        | —                        | —                        |
| `CreatorFacet`            | `creator`             | `creator.label`             | `author.label`           | —                        | —                        |
| `LanguageFacet`           | `language`            | `language`¹                 | `language`¹              | `language`               | —                        |
| `LocationFacet`           | `location`            | `location.label`            | `place.label`            | `location`               | —                        |
| `OCRFacet`                | `has_ocr`             | `N/A`                       | `N/A`                    | `N/A`                    | `N/A`                    |
| `PresentationSetFacet`    | `presentation_set`    | `presentation_set.label`    | `presentation_set.label` | `presentation_set.label` | `presentation_set.label` |
| `PublicationStatusFacet`  | `publication_status`  | `rdf_type`                  | `rdf_type`               | `rdf_type`               | `rdf_type`               |
| `PublisherFacet`          | `publisher`           | `publisher.label`           | —                        | `publisher.label`        | —                        |
| `RDFTypeFacet`            | `rdf_type`            | `rdf_type`                  | `rdf_type`               | `rdf_type`               | `rdf_type`               |
| `ResourceTypeFacet`       | `resource_type`       | `format.label`              | `type`                   | `format`²                | —                        |
| `RightsFacet`             | `rights`              | `rights.label`              | `rights`³                | `rights`³                | —                        |
| `SubjectFacet`            | `subject`             | `subject.label`             | `subject.label`          | `subject`                | —                        |
| `VisibilityFacet`         | `visibility`          | `rdf_type`                  | `rdf_type`               | `rdf_type`               | `rdf_type`               |

¹ For these properties, `language_name()` is used to translate the ISO 639 code
to the full language name.

² The `format` property of `Poster` also includes the extent information after
the genre/form term, so the facet here just takes the segment of the `format`
property up to the first comma.

³ For these properties, `rights_statement_label()` is used to correlate a
rightsstatement.org URL to a vocab.lib.umd.edu term and its label.

⁴ For the OCR facet, the check for the presence of an OCR file is via creating a
PCDMObjectResource and checking for an extracted text file.
"""  # noqa: E501

import logging
from collections.abc import Callable

from iso639 import Language, LanguageNotFoundError
from plastron.models.letter import Letter
from plastron.models.poster import Poster
from plastron.models.umd import AdminSet, Item
from plastron.namespaces import owl, pcdmuse, rdfs, umdaccess
from plastron.rdfmapping.properties import RDFDataProperty, RDFObjectProperty
from plastron.repo.pcdm import PCDMObjectResource
from plastron.validation.vocabularies import Vocabulary
from rdflib import URIRef

from solrizer.indexers import IndexerContext

logger = logging.getLogger(__name__)

RIGHTS_VOCAB = Vocabulary('http://vocab.lib.umd.edu/rightsStatement#')


def rights_statement_label(uri: str) -> str:
    """Given a URI (usually from rightsstatements.org), find the vocabulary term
    in the UMD Libraries Rights Statements vocabulary that corresponds to that URI,
    and return the RDF label for that term."""
    try:
        term = RIGHTS_VOCAB.find(owl.sameAs, URIRef(uri))
        return str(term[rdfs.label])
    except KeyError as e:
        logger.warning(f'Cannot find term with "{e}" in {RIGHTS_VOCAB.uri}')
        return uri


def language_name(code: str) -> str:
    """Attempt to interpret `code` as an ISO 639 language code and return
    the full name of the language. If unsuccessful, logs a warning and returns
    `code` instead."""
    try:
        return Language.match(str(code)).name
    except LanguageNotFoundError:
        logger.warning(f'Cannot match {code} to an ISO 639 language code')
        return str(code)


def concat_values(prop: RDFDataProperty, separator: str = ' / ') -> str:
    """Join the sorted values of the given data property using the `separator`
    (defaults to " / ")."""
    return separator.join(sorted(prop.values))


def get_labels(prop: RDFObjectProperty, separator: str = ' / '):
    """For each object in the given object property, construct the concatenated
    string of its label values, and return the list of these strings."""
    return [concat_values(obj.label, separator) for obj in prop.objects]


def get_data_values(prop: RDFDataProperty, converter: Callable[..., str] = str) -> list[str] | None:
    """Return a list of the values in the given data property after passing
    them through a converter function. If no `converter` is specified, uses
    the built-in `str()` function."""
    return [converter(v) for v in prop]


class FacetBase:
    """Base class for faceters."""

    facet_name: str = None

    def __init__(self, ctx: IndexerContext):
        self.ctx: IndexerContext = ctx
        """Context for the resource being indexed."""

    def get_values(self) -> list[str] | None:
        raise NotImplementedError


class AdminSetFacet(FacetBase):
    """Admin set facet.

    Retrieves the `title` property of the administrative set object (i.e., `pcdm:Collection`)
    that this object is a member of."""

    facet_name = 'admin_set'

    def get_values(self) -> list[str] | None:
        if len(self.ctx.obj.member_of) == 0:
            return None
        collection_uri = self.ctx.obj.member_of.value
        collection = self.ctx.repo[collection_uri].read().describe(AdminSet)
        return [str(collection.title)]


class ArchivalCollectionFacet(FacetBase):
    """Archival collection facet.

    For `Item` objects, uses the `label` properties of the objects of the `archival_collection`
    property. For `Letter` objects, uses the `label` properties of the objects of the
    `part_of` property instead. For `Poster` objects, uses the direct values of the
    `part_of` property."""

    facet_name = 'archival_collection'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.archival_collection)
            case Letter():
                return get_labels(self.ctx.obj.part_of)
            case Poster():
                return [str(self.ctx.obj.part_of.value)]
            case _:
                return None


class ContributorFacet(FacetBase):
    """Contributor facet.

    For `Item` objects, uses the `label` properties of the objects of the `contributor`
    property."""

    facet_name = 'contributor'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.contributor)
            case _:
                return None


class CreatorFacet(FacetBase):
    """Creator facet.

    For `Item` objects, uses the `label` properties of the objects of the `creator`
    property. For `Letter` objects, uses the `label` properties of the objects of the
    `author` property instead."""

    facet_name = 'creator'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.creator)
            case Letter():
                return get_labels(self.ctx.obj.author)
            case _:
                return None


class LanguageFacet(FacetBase):
    """Language facet.

    For `Item` and `Letter` objects, assumes `language` contains one or more
    [ISO 639](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes)
    language codes. For `Poster`, assumes the `language` property contains the
    full name of the language."""

    facet_name = 'language'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item() | Letter():
                return get_data_values(self.ctx.obj.language, language_name)
            case Poster():
                return get_data_values(self.ctx.obj.language)
            case _:
                return None


class LocationFacet(FacetBase):
    """Location facet.

    For `Item` objects, uses the `label` properties of the objects of the `location`
    property. For `Letter` objects, uses the `label` properties of the objects of the
    `place` property instead. For `Poster` objects, uses the direct values from the
    `location` property."""

    facet_name = 'location'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.location)
            case Letter():
                return get_labels(self.ctx.obj.place)
            case Poster():
                return [concat_values(self.ctx.obj.location)]
            case _:
                return None


class OCRFacet(FacetBase):
    """OCR facet.

    If the object has the `ocr` property, returns "Has OCR",
    otherwise returns None"""

    facet_name = 'has_ocr'

    def get_values(self) -> list[str] | None:
        pcdm_resource = PCDMObjectResource(self.ctx.repo, self.ctx.resource.path)
        if pcdm_resource.get_file(rdf_type=pcdmuse.ExtractedText):
            return ['Has OCR']
        else:
            return None


class PresentationSetFacet(FacetBase):
    """Presentation set facet.

    Returns the `label` properties of the objects in the `presentation_set`
    property."""

    facet_name = 'presentation_set'

    def get_values(self) -> list[str] | None:
        try:
            return get_labels(self.ctx.obj.presentation_set)
        except AttributeError:
            return None


class PublicationStatusFacet(FacetBase):
    """Publication status facet.

    If the object has the RDF type `umdaccess:Published`, returns "Published",
    otherwise returns "Unpublished"."""

    facet_name = 'publication_status'

    def get_values(self) -> list[str] | None:
        if umdaccess.Published in self.ctx.obj.rdf_type:
            return ['Published']
        else:
            return ['Unpublished']


class PublisherFacet(FacetBase):
    """Publisher facet.

    For `Item` objects, uses the `label` properties of the objects of the `publisher`
    property. For `Poster` objects, uses the direct values from the `publisher`
    property."""

    facet_name = 'publisher'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.publisher)
            case Poster():
                return [concat_values(self.ctx.obj.publisher)]
            case _:
                return None


class RDFTypeFacet(FacetBase):
    """RDF type facet.

    Values are CURIES taken from the `rdf_type__curies` field created by the
    `content_model` indexer."""

    facet_name = 'rdf_type'

    def get_values(self) -> list[str] | None:
        return self.ctx.doc.get(self.ctx.content_model_prefix + 'rdf_type__curies', None)


class ResourceTypeFacet(FacetBase):
    """Resource type facet.

    For `Item` objects, uses the `label` properties of the objects of the `format`
    property. For `Letter` objects, uses the direct values of the `type` property.
    For `Poster` objects, uses the direct value of the `format` property, up to
    the first comma (in the Poster content descriptions, the `format` property
    contains both a genre/format description and physical extent information)."""

    facet_name = 'resource_type'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.format)
            case Letter():
                return get_data_values(self.ctx.obj.type)
            case Poster():
                return get_data_values(self.ctx.obj.format, lambda v: v.split(',')[0])
            case _:
                return None


class RightsFacet(FacetBase):
    """Rights facet.

    For `Item` objects, uses the `label` properties of the objects of the `rights`
    property. For `Letter` and `Poster` objects, correlates the direct values (URIs
    from rightsstatements.org) with labels from the UMD Libraries Rights Statements
    vocabulary."""

    facet_name = 'rights'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item():
                return get_labels(self.ctx.obj.rights)
            case Letter() | Poster():
                return get_data_values(self.ctx.obj.rights, rights_statement_label)
            case _:
                return None


class SubjectFacet(FacetBase):
    """Subject facet.

    For `Item` and `Letter` objects, uses the `label` properties of the objects
    of the `subject` property. For `Poster` objects, uses the direct values from
    the `subject` property."""

    facet_name = 'subject'

    def get_values(self) -> list[str] | None:
        match self.ctx.obj:
            case Item() | Letter():
                return get_labels(self.ctx.obj.subject)
            case Poster():
                return get_data_values(self.ctx.obj.subject)
            case _:
                return None


class VisibilityFacet(FacetBase):
    """Visibility facet.

    If the object has the RDF type `umdaccess:Hidden`, returns "Hidden", otherwise
    returns "Visible"."""

    facet_name = 'visibility'

    def get_values(self) -> list[str] | None:
        if umdaccess.Hidden in self.ctx.obj.rdf_type:
            return ['Hidden']
        else:
            return ['Visible']
