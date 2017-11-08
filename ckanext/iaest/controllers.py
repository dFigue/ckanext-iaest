import json
import logging

from ckan.plugins import toolkit

if toolkit.check_ckan_version(min_version='2.1'):
    BaseController = toolkit.BaseController
else:
    from ckan.lib.base import BaseController
from ckan.controllers.package import PackageController
from ckan.controllers.home import HomeController

from ckanext.iaest.utils import CONTENT_TYPES, parse_accept_header

from genshi.template import MarkupTemplate
from genshi.template.text import NewTextTemplate

import ckan.lib.base as base
render = base.render


log = logging.getLogger(__name__)

def check_access_header():
    _format = None

    # Check Accept headers
    accept_header = toolkit.request.headers.get('Accept', '')
    if accept_header:
        _format = parse_accept_header(accept_header)
    return _format


class DCATController(BaseController):

    def read_catalog(self, _format=None):
        log.debug('Leyendo catalog')
        if not _format:
            _format = check_access_header()

        if not _format:
            return HomeController().index()

        data_dict = {
            'page': toolkit.request.params.get('page'),
            'modified_since': toolkit.request.params.get('modified_since'),
            'format': _format,
        }

        toolkit.response.headers.update(
            {'Content-type': CONTENT_TYPES[_format]})
        try:
            return toolkit.get_action('iaest_catalog_show')({}, data_dict)
        except toolkit.ValidationError, e:
            toolkit.abort(409, str(e))

    def read_dataset(self, _id, _format=None):
        log.debug('Leyendo dataset')
        if not _format:
            _format = check_access_header()

        if not _format:
            return PackageController().read(_id)

        toolkit.response.headers.update(
            {'Content-type': CONTENT_TYPES[_format]})

        try:
            result = toolkit.get_action('iaest_dataset_show')({}, {'id': _id,
                'format': _format})
        except toolkit.ObjectNotFound:
            toolkit.abort(404)

        return result

    def dcat_json(self):

        data_dict = {
            'page': toolkit.request.params.get('page'),
            'modified_since': toolkit.request.params.get('modified_since'),
        }

        try:
            datasets = toolkit.get_action('iaest_datasets_list')({},
                                                                data_dict)
        except toolkit.ValidationError, e:
            toolkit.abort(409, str(e))

        content = json.dumps(datasets)

        toolkit.response.headers['Content-Type'] = 'application/json'
        toolkit.response.headers['Content-Length'] = len(content)

        return content

    def federador(self):
        
        log.debug('Leyendo catalog')
        data_dict = {
            'page': toolkit.request.params.get('page'),
            'modified_since': toolkit.request.params.get('modified_since'),
            
        }

       
        try:
            log.debug('Obteniendo datasets para el federador')
            dataset_dict = toolkit.get_action('iaest_federador')({}, data_dict)
            log.debug('Creando extra_vars')
            c = {'c':{'pkg':dataset_dict}}
            log.debug('Creando c %s', c)
            
            toolkit.response.headers['Content-Type'] = 'application/rdf+xml;charset=UTF-8'
            loader_render = NewTextTemplate("application/rdf+xml; charset=utf-8", True, 'rdf') 
            return render('package/federador.rdf', extra_vars=c,loader=loader_render)


        except toolkit.ValidationError, e:
            toolkit.abort(409, str(e))



