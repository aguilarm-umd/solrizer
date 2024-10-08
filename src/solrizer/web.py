from flask import Flask, request
from plastron.client import Client, Endpoint
from plastron.models import ModelClassError, guess_model
from plastron.rdfmapping.resources import RDFResource
from plastron.repo import Repository, RepositoryError, RepositoryResource
from requests_jwtauth import JWTSecretAuth
from werkzeug.exceptions import InternalServerError

from solrizer.errors import (
    NoResourceRequested,
    ProblemDetailError,
    ResourceNotAvailable,
    problem_detail_response,
)
from solrizer.indexers import IndexerContext, IndexerError


def create_app():
    app = Flask(__name__)
    app.config.from_prefixed_env('SOLRIZER')

    client = Client(
        endpoint=Endpoint(app.config['FCREPO_ENDPOINT']),
        auth=JWTSecretAuth(
            secret=app.config['FCREPO_JWT_SECRET'],
            claims={
                'sub': 'solrizer',
                'iss': 'solrizer',
                'role': 'fedoraAdmin'
            })
        )
    app.config['repo'] = Repository(client=client)
    app.config['INDEXERS'] = app.config.get('INDEXERS', 'content_model').split(',')

    @app.route('/doc')
    def get_doc():
        uri = request.args.get('uri')

        if uri is None:
            raise NoResourceRequested()

        try:
            resource: RepositoryResource = app.config['repo'][uri].read()
        except RepositoryError as e:
            raise ResourceNotAvailable(uri=uri) from e

        # dynamically determine the model_class
        try:
            model_class = guess_model(resource.describe(RDFResource))
        except ModelClassError as e:
            app.logger.error(f'Unable to determine model class for {uri}')
            raise ResourceNotAvailable(uri=uri) from e

        ctx = IndexerContext(
            repo=app.config['repo'],
            resource=resource,
            model_class=model_class,
            doc={'id': uri},
            config=app.config,
        )

        try:
            doc = ctx.run(app.config['INDEXERS'])
        except IndexerError as e:
            raise InternalServerError(f'Error while processing {uri} for indexing: {e}')

        return doc, {'Content-Type': 'application/json;charset=utf-8'}

    # serve error responses using the RFC 9457 Problem Detail JSON format
    app.register_error_handler(ProblemDetailError, problem_detail_response)

    return app
