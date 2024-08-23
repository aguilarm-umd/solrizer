import os

from flask import Flask, request
from plastron.client import Client, Endpoint
from plastron.models import guess_model, ModelClassError
from plastron.rdfmapping.resources import RDFResource
from plastron.repo import Repository, RepositoryError, RepositoryResource
from requests_jwtauth import HTTPBearerAuth
from werkzeug.exceptions import InternalServerError

from solrizer.errors import ResourceNotAvailable, NoResourceRequested, ProblemDetailError, problem_detail_response
from solrizer.indexers import IndexerContext, IndexerError

FCREPO_ENDPOINT = os.environ.get('FCREPO_ENDPOINT')
FCREPO_JWT_TOKEN = os.environ.get('FCREPO_JWT_TOKEN')


def create_app():
    app = Flask(__name__)

    client = Client(endpoint=Endpoint(FCREPO_ENDPOINT), auth=HTTPBearerAuth(FCREPO_JWT_TOKEN))
    app.config['repo'] = Repository(client=client)

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
        )

        try:
            doc = ctx.run(['content_model'])
        except IndexerError as e:
            raise InternalServerError(f'Error while processing {uri} for indexing: {e}')

        return doc, {'Content-Type': 'application/json;charset=utf-8'}

    # serve error responses using the RFC 9457 Problem Detail JSON format
    app.register_error_handler(ProblemDetailError, problem_detail_response)

    return app
