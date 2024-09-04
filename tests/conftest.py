from uuid import uuid4

import pytest

import solrizer.web
from solrizer.indexers import SolrFields
from solrizer.web import create_app


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('SOLRIZER_FCREPO_ENDPOINT', 'http://localhost:8080/fcrepo/rest')
    monkeypatch.setenv('SOLRIZER_FCREPO_JWT_TOKEN', '')
    monkeypatch.setenv('SOLRIZER_FCREPO_JWT_SECRET', str(uuid4()))
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def proxies() -> SolrFields:
    return {
        'proxy__proxy_for__uri': 'url1',
        'proxy__next': [{
            'proxy__proxy_for__uri': 'url2',
            'proxy__next': [{
                'proxy__proxy_for__uri': 'url3',
            }]
        }]
    }
