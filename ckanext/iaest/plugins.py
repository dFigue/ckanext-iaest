from pylons import config

from ckan import plugins as p
try:
    from ckan.lib.plugins import DefaultTranslation
except ImportError:
    class DefaultTranslation():
        pass


from ckanext.iaest.logic import (iaest_dataset_show,
                                iaest_catalog_show,
                                iaest_catalog_search,
                                iaest_datasets_list,
                                iaest_auth,
                                iaest_federador,
                                )
from ckanext.iaest import utils

DEFAULT_CATALOG_ENDPOINT = '/catalog/iaest.{_format}'
CUSTOM_ENDPOINT_CONFIG = 'ckanext.iaest.catalog_endpoint'
ENABLE_CONTENT_NEGOTIATION_CONFIG = 'ckanext.iaest.enable_content_negotiation'


class IAESTPlugin(p.SingletonPlugin, DefaultTranslation):

    p.implements(p.IConfigurer, inherit=True)
    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IActions, inherit=True)
    p.implements(p.IAuthFunctions, inherit=True)
    p.implements(p.IPackageController, inherit=True)
    if p.toolkit.check_ckan_version(min_version='2.5.0'):
        p.implements(p.ITranslation, inherit=True)

    # IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'templates')

        # Check catalog URI on startup to emit a warning if necessary
        utils.catalog_uri()

        # Check custom catalog endpoint
        custom_endpoint = config.get(CUSTOM_ENDPOINT_CONFIG)
        if custom_endpoint:
            if not custom_endpoint[:1] == '/':
                raise Exception(
                    '"{0}" should start with a backslash (/)'.format(
                        CUSTOM_ENDPOINT_CONFIG))
            if '{_format}' not in custom_endpoint:
                raise Exception(
                    '"{0}" should contain {{_format}}'.format(
                        CUSTOM_ENDPOINT_CONFIG))

    # IRoutes
    def before_map(self, _map):

        controller = 'ckanext.iaest.controllers:DCATController'

        _map.connect('iaest_catalog',
                     config.get('ckanext.iaest.catalog_endpoint',
                                DEFAULT_CATALOG_ENDPOINT),
                     controller=controller, action='read_catalog',
                     requirements={'_format': 'xml|rdf|n3|ttl|jsonld'})

        _map.connect('iaest_dataset', '/dataset/iaest/{_id}.{_format}',
                     controller=controller, action='read_dataset',
                     requirements={'_format': 'xml|rdf|n3|ttl|jsonld'})
        
        _map.connect('federador_rdf', '/federador.rdf',
                     controller=controller, action='federador')

       
        return _map

    # IActions
    def get_actions(self):
        return {
            'iaest_dataset_show': iaest_dataset_show,
            'iaest_catalog_show':iaest_catalog_show,
            'iaest_catalog_search': iaest_catalog_search,
            'iaest_federador':iaest_federador,
        }

    # IAuthFunctions
    def get_auth_functions(self):
        return {
            'iaest_dataset_show': iaest_auth,
            'iaest_catalog_show': iaest_auth,
            'iaest_catalog_search': iaest_auth,
            'iaest_federador': iaest_auth
        }

    # IPackageController
    def after_show(self, context, data_dict):

        if context.get('for_view'):
            field_labels = utils.field_labels()

            def set_titles(object_dict):
                for key, value in object_dict.iteritems():
                    if key in field_labels:
                        object_dict[field_labels[key]] = object_dict[key]
                        del object_dict[key]

            for resource in data_dict.get('resources', []):
                set_titles(resource)

            for extra in data_dict.get('extras', []):
                if extra['key'] in field_labels:
                    extra['key'] = field_labels[extra['key']]

        return data_dict


class DCATJSONInterface(p.SingletonPlugin):

    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions, inherit=True)

    # IRoutes
    def after_map(self, map):

        controller = 'ckanext.iaest.controllers:DCATController'
        route = config.get('ckanext.iaest.json_endpoint', '/dcat.json')
        map.connect(route, controller=controller, action='dcat_json')

        return map

    # IActions
    def get_actions(self):
        return {
            'iaest_datasets_list': iaest_datasets_list,
        }

    # IAuthFunctions
    def get_auth_functions(self):
        return {
            'iaest_datasets_list': iaest_auth,
        }
