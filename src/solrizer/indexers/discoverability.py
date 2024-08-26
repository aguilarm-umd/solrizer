"""
Indexer Name: **`discoverability`**

Indexer implementation function: `discoverability_fields()`

Prerequisites: None

Output fields:

| Field             | Python Type | Solr Type |
|-------------------|-------------|-----------|
| `is_published`    | `bool`      | boolean   |
| `is_hidden`       | `bool`      | boolean   |
| `is_top_level`    | `bool`      | boolean   |
| `is_discoverable` | `bool`      | boolean   |
"""

from plastron.namespaces import umdaccess

from solrizer.indexers import IndexerContext, SolrFields


def discoverability_fields(ctx: IndexerContext) -> SolrFields:
    fields = {
        'is_published': umdaccess.Published in ctx.obj.rdf_type,
        'is_hidden': umdaccess.Hidden in ctx.obj.rdf_type,
        'is_top_level': any(str(v).startswith('http://vocab.lib.umd.edu/model#') for v in ctx.obj.rdf_type),
    }
    fields['is_discoverable'] = (fields['is_top_level'] and fields['is_published'] and not fields['is_hidden'])
    return fields
