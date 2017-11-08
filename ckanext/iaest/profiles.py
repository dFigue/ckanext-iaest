import datetime
import json
import logging

from dateutil.parser import parse as parse_date

from pylons import config

import rdflib
from rdflib import URIRef, BNode, Literal
from rdflib.namespace import Namespace, RDF, XSD, SKOS, RDFS

from geomet import wkt, InvalidGeoJSONException

from ckan.model.license import LicenseRegister
from ckan.model.group import Group
from ckan.plugins import toolkit

from ckanext.iaest.utils import resource_uri, publisher_uri_from_dataset_dict,catalog_uri

DCT = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
ADMS = Namespace("http://www.w3.org/ns/adms#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
SCHEMA = Namespace('http://schema.org/')
TIME = Namespace('http://www.w3.org/2006/time')
LOCN = Namespace('http://www.w3.org/ns/locn#')
GSP = Namespace('http://www.opengis.net/ont/geosparql#')
OWL = Namespace('http://www.w3.org/2002/07/owl#')
SPDX = Namespace('http://spdx.org/rdf/terms#')

GEOJSON_IMT = 'https://www.iana.org/assignments/media-types/application/vnd.geo+json'

RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#") 
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#") 
DC = Namespace("http://purl.org/dc/elements/1.1/") 
DBPEDIA = Namespace("http://dbpedia.org/ontology/") 
ARAGODEF = Namespace("http://opendata.aragon.es/def/Aragopedia.html") 

namespaces = {
    'dct': DCT,
    'dcat': DCAT,
    'adms': ADMS,
    'vcard': VCARD,
    'foaf': FOAF,
    'schema': SCHEMA,
    'time': TIME,
    'skos': SKOS,
    'locn': LOCN,
    'gsp': GSP,
    'owl': OWL,
    'rdfs': RDFS,
    'rdf': RDF,
    'dc': DC,
    'dbpedia': DBPEDIA,
    'aragodef': ARAGODEF
}

log = logging.getLogger(__name__)

class RDFProfile(object):
    '''Base class with helper methods for implementing RDF parsing profiles

       This class should not be used directly, but rather extended to create
       custom profiles
    '''

    def __init__(self, graph, compatibility_mode=False):
        '''Class constructor

        Graph is an rdflib.Graph instance.

        In compatibility mode, some fields are modified to maintain
        compatibility with previous versions of the ckanext-dcat parsers
        (eg adding the `dcat_` prefix or storing comma separated lists instead
        of JSON dumps).
        '''

        self.g = graph

        self.compatibility_mode = compatibility_mode

        # Cache for mappings of licenses URL/title to ID built when needed in
        # _license().
        self._licenceregister_cache = None

    def _datasets(self):
        '''
        Generator that returns all DCAT datasets on the graph

        Yields rdflib.term.URIRef objects that can be used on graph lookups
        and queries
        '''
        for dataset in self.g.subjects(RDF.type, DCAT.Dataset):
            yield dataset

    def _distributions(self, dataset):
        '''
        Generator that returns all DCAT distributions on a particular dataset

        Yields rdflib.term.URIRef objects that can be used on graph lookups
        and queries
        '''
        for distribution in self.g.objects(dataset, DCAT.distribution):
            yield distribution

    def _themes(self, dataset):      
        '''
        '''
        for themes in self.g.objects(dataset, DCAT.theme):
            yield themes

    def _object(self, subject, predicate):
        '''
        Helper for returning the first object for this subject and predicate

        Both subject and predicate must be rdflib URIRef or BNode objects

        Returns an rdflib reference (URIRef or BNode) or None if not found
        '''
        for _object in self.g.objects(subject, predicate):
            return _object
        return None

    def _object_value(self, subject, predicate):
        '''
        Given a subject and a predicate, returns the value of the object

        Both subject and predicate must be rdflib URIRef or BNode objects

        If found, the unicode representation is returned, else an empty string
        '''
        for o in self.g.objects(subject, predicate):
            return unicode(o)
        return ''

    def _object_value_int(self, subject, predicate):
        '''
        Given a subject and a predicate, returns the value of the object as an
        integer

        Both subject and predicate must be rdflib URIRef or BNode objects

        If the value can not be parsed as intger, returns None
        '''
        object_value = self._object_value(subject, predicate)
        if object_value:
            try:
                return int(object_value)
            except ValueError:
                pass
        return None

    def _object_value_list(self, subject, predicate):
        '''
        Given a subject and a predicate, returns a list with all the values of
        the objects

        Both subject and predicate must be rdflib URIRef or BNode  objects

        If no values found, returns an empty string
        '''
        return [unicode(o) for o in self.g.objects(subject, predicate)]

    def _time_interval(self, subject, predicate):
        '''
        Returns the start and end date for a time interval object

        Both subject and predicate must be rdflib URIRef or BNode objects

        It checks for time intervals defined with both schema.org startDate &
        endDate and W3C Time hasBeginning & hasEnd.

        Note that partial dates will be expanded to the first month / day
        value, eg '1904' -> '1904-01-01'.

        Returns a tuple with the start and end date values, both of which
        can be None if not found
        '''

        start_date = end_date = None

        for interval in self.g.objects(subject, predicate):
            # Fist try the schema.org way
            start_date = self._object_value(interval, SCHEMA.startDate)
            end_date = self._object_value(interval, SCHEMA.endDate)

            if start_date or end_date:
                return start_date, end_date

            # If no luck, try the w3 time way
            start_nodes = [t for t in self.g.objects(interval,
                                                     TIME.hasBeginning)]
            end_nodes = [t for t in self.g.objects(interval,
                                                   TIME.hasEnd)]
            if start_nodes:
                start_date = self._object_value(start_nodes[0],
                                                TIME.inXSDDateTime)
            if end_nodes:
                end_date = self._object_value(end_nodes[0],
                                              TIME.inXSDDateTime)

        return start_date, end_date

    def _publisher(self, subject, predicate):
        '''
        Returns a dict with details about a dct:publisher entity, a foaf:Agent

        Both subject and predicate must be rdflib URIRef or BNode objects

        Examples:

        <dct:publisher>
            <foaf:Organization rdf:about="http://orgs.vocab.org/some-org">
                <foaf:name>Publishing Organization for dataset 1</foaf:name>
                <foaf:mbox>contact@some.org</foaf:mbox>
                <foaf:homepage>http://some.org</foaf:homepage>
                <dct:type rdf:resource="http://purl.org/adms/publishertype/NonProfitOrganisation"/>
            </foaf:Organization>
        </dct:publisher>

        {
            'uri': 'http://orgs.vocab.org/some-org',
            'name': 'Publishing Organization for dataset 1',
            'email': 'contact@some.org',
            'url': 'http://some.org',
            'type': 'http://purl.org/adms/publishertype/NonProfitOrganisation',
        }

        <dct:publisher rdf:resource="http://publications.europa.eu/resource/authority/corporate-body/EURCOU" />

        {
            'uri': 'http://publications.europa.eu/resource/authority/corporate-body/EURCOU'
        }

        Returns keys for uri, name, email, url and type with the values set to
        an empty string if they could not be found
        '''

        publisher = {}

        for agent in self.g.objects(subject, predicate):

            publisher['uri'] = (unicode(agent) if isinstance(agent,
                                rdflib.term.URIRef) else '')

            publisher['name'] = self._object_value(agent, FOAF.name)

            publisher['email'] = self._object_value(agent, FOAF.mbox)

            publisher['url'] = self._object_value(agent, FOAF.homepage)

            publisher['type'] = self._object_value(agent, DCT.type)

            publisher['title'] = self._object_value(agent, DCT.title)

        return publisher

    def _contact_details(self, subject, predicate):
        '''
        Returns a dict with details about a vcard expression

        Both subject and predicate must be rdflib URIRef or BNode objects

        Returns keys for uri, name and email with the values set to
        an empty string if they could not be found
        '''

        contact = {}

        for agent in self.g.objects(subject, predicate):

            contact['uri'] = (unicode(agent) if isinstance(agent,
                              rdflib.term.URIRef) else '')

            contact['name'] = self._object_value(agent, VCARD.fn)

            contact['email'] = self._object_value(agent, VCARD.hasEmail)

        return contact

    def _spatial(self, subject, predicate):
        '''
        Returns a dict with details about the spatial location

        Both subject and predicate must be rdflib URIRef or BNode objects

        Returns keys for uri, text or geom with the values set to
        None if they could not be found.

        Geometries are always returned in GeoJSON. If only WKT is provided,
        it will be transformed to GeoJSON.

        Check the notes on the README for the supported formats:

        https://github.com/ckan/ckanext-dcat/#rdf-dcat-to-ckan-dataset-mapping
        '''

        uri = None
        text = None
        geom = None

        for spatial in self.g.objects(subject, predicate):

            if isinstance(spatial, URIRef):
                uri = unicode(spatial)

            if isinstance(spatial, Literal):
                text = unicode(spatial)

            if (spatial, RDF.type, DCT.Location) in self.g:
                for geometry in self.g.objects(spatial, LOCN.geometry):
                    if (geometry.datatype == URIRef(GEOJSON_IMT) or
                            not geometry.datatype):
                        try:
                            json.loads(unicode(geometry))
                            geom = unicode(geometry)
                        except (ValueError, TypeError):
                            pass
                    if not geom and geometry.datatype == GSP.wktLiteral:
                        try:
                            geom = json.dumps(wkt.loads(unicode(geometry)))
                        except (ValueError, TypeError):
                            pass
                for label in self.g.objects(spatial, SKOS.prefLabel):
                    text = unicode(label)
                for label in self.g.objects(spatial, RDFS.label):
                    text = unicode(label)

        return {
            'uri': uri,
            'text': text,
            'geom': geom,
        }

    def _license(self, dataset_ref):
        '''
        Returns a license identifier if one of the distributions license is
        found in CKAN license registry. If no distribution's license matches,
        an empty string is returned.

        The first distribution with a license found in the registry is used so
        that if distributions have different licenses we'll only get the first
        one.
        '''
        log.debug('Obteniendo licencias')
        license_id_final = ''
        license_title_final = ''
        license_id_rdf = self._object_value(dataset_ref, DCT.license)
        log.debug('Licencia Obtenida: %s ',license_id_rdf)
        for license_id, license in LicenseRegister().items():
            log.debug('Tratando licencia: %s ',license_id)
            if license_id == license_id_rdf:
                log.debug('Encontrada licencia')
                license_id_final = license_id
                license_title_final = license.title
                break
        
        log.debug('Licencias que se insertan en el dataset: %s, %s ',license_id_final,license_title_final)
      
        return license_id_final,license_title_final

    def _distribution_format(self, distribution, normalize_ckan_format=True):
        '''
        Returns the Internet Media Type and format label for a distribution

        Given a reference (URIRef or BNode) to a dcat:Distribution, it will
        try to extract the media type (previously knowm as MIME type), eg
        `text/csv`, and the format label, eg `CSV`

        Values for the media type will be checked in the following order:

        1. literal value of dcat:mediaType
        2. literal value of dct:format if it contains a '/' character
        3. value of dct:format if it is an instance of dct:IMT, eg:

            <dct:format>
                <dct:IMT rdf:value="text/html" rdfs:label="HTML"/>
            </dct:format>

        Values for the label will be checked in the following order:

        1. literal value of dct:format if it not contains a '/' character
        2. label of dct:format if it is an instance of dct:IMT (see above)

        If `normalize_ckan_format` is True and using CKAN>=2.3, the label will
        be tried to match against the standard list of formats that is included
        with CKAN core
        (https://github.com/ckan/ckan/blob/master/ckan/config/resource_formats.json)
        This allows for instance to populate the CKAN resource format field
        with a format that view plugins, etc will understand (`csv`, `xml`,
        etc.)

        Return a tuple with the media type and the label, both set to None if
        they couldn't be found.
        '''

        imt = None
        label = None

        imt = self._object_value(distribution, DCAT.mediaType)

        _format = self._object(distribution, DCT['format'])
        if isinstance(_format, Literal):
            if not imt and '/' in _format:
                imt = unicode(_format)
            else:
                label = unicode(_format)
        elif isinstance(_format, (BNode, URIRef)):
            if self._object(_format, RDF.type) == DCT.IMT:
                if not imt:
                    imt = unicode(self.g.value(_format, default=None))
                label = unicode(self.g.label(_format, default=None))

        if ((imt or label) and normalize_ckan_format and
                toolkit.check_ckan_version(min_version='2.3')):
            import ckan.config
            from ckan.lib import helpers

            format_registry = helpers.resource_formats()

            if imt in format_registry:
                label = format_registry[imt][1]
            elif label in format_registry:
                label = format_registry[label][1]

        return imt, label

    def _get_dict_value(self, _dict, key, default=None):
        '''
        Returns the value for the given key on a CKAN dict

        By default a key on the root level is checked. If not found, extras
        are checked, both with the key provided and with `dcat_` prepended to
        support legacy fields.

        If not found, returns the default value, which defaults to None
        '''

        if key in _dict:
            return _dict[key]

        for extra in _dict.get('extras', []):
            if extra['key'] == key or extra['key'] == 'dcat_' + key:
                return extra['value']

        return default

    def _get_dataset_value(self, dataset_dict, key, default=None):
        '''
        Returns the value for the given key on a CKAN dict

        Check `_get_dict_value` for details
        '''
        return self._get_dict_value(dataset_dict, key, default)

    def _get_resource_value(self, resource_dict, key, default=None):
        '''
        Returns the value for the given key on a CKAN dict

        Check `_get_dict_value` for details
        '''
        return self._get_dict_value(resource_dict, key, default)

    def _add_date_triples_from_dict(self, _dict, subject, items):
        self._add_triples_from_dict(_dict, subject, items,
                                    date_value=True)

    def _add_list_triples_from_dict(self, _dict, subject, items):
        self._add_triples_from_dict(_dict, subject, items,
                                    list_value=True)

    def _add_triples_from_dict(self, _dict, subject, items,
                               list_value=False,
                               date_value=False):
        for item in items:
            key, predicate, fallbacks, _type = item
            self._add_triple_from_dict(_dict, subject, predicate, key,
                                       fallbacks=fallbacks,
                                       list_value=list_value,
                                       date_value=date_value,
                                       _type=_type)

    def _add_triple_from_dict(self, _dict, subject, predicate, key,
                              fallbacks=None,
                              list_value=False,
                              date_value=False,
                              _type=Literal):
        '''
        Adds a new triple to the graph with the provided parameters

        The subject and predicate of the triple are passed as the relevant
        RDFLib objects (URIRef or BNode). The object is always a literal value,
        which is extracted from the dict using the provided key (see
        `_get_dict_value`). If the value for the key is not found, then
        additional fallback keys are checked.

        If `list_value` or `date_value` are True, then the value is treated as
        a list or a date respectively (see `_add_list_triple` and
        `_add_date_triple` for details.
        '''
        value = self._get_dict_value(_dict, key)
        if not value and fallbacks:
            for fallback in fallbacks:
                value = self._get_dict_value(_dict, fallback)
                if value:
                    break

        if value and list_value:
            self._add_list_triple(subject, predicate, value, _type)
        elif value and date_value:
            self._add_date_triple(subject, predicate, value, _type)
        elif value:
            # Normal text value
            self.g.add((subject, predicate, _type(value)))

    def _add_list_triple(self, subject, predicate, value, _type=Literal):
        '''
        Adds as many triples to the graph as values

        Values are literal strings, if `value` is a list, one for each
        item. If `value` is a string there is an attempt to split it using
        commas, to support legacy fields.
        '''
        items = []
        # List of values
        if isinstance(value, list):
            items = value
        elif isinstance(value, basestring):
            try:
                # JSON list
                items = json.loads(value)
                if isinstance(items, ((int, long, float, complex))):
                    items = [items]
            except ValueError:
                if ',' in value:
                    # Comma-separated list
                    items = value.split(',')
                else:
                    # Normal text value
                    items = [value]

        for item in items:
            self.g.add((subject, predicate, _type(item)))

    def _add_date_triple(self, subject, predicate, value, _type=Literal):
        '''
        Adds a new triple with a date object

        Dates are parsed using dateutil, and if the date obtained is correct,
        added to the graph as an XSD.dateTime value.

        If there are parsing errors, the literal string value is added.
        '''
        if not value:
            return
        try:
            default_datetime = datetime.datetime(1, 1, 1, 0, 0, 0)
            _date = parse_date(value, default=default_datetime)

            self.g.add((subject, predicate, _type(_date.isoformat(),
                                                  datatype=XSD.dateTime)))
        except ValueError:
            self.g.add((subject, predicate, _type(value)))

    def _last_catalog_modification(self):
        '''
        Returns the date and time the catalog was last modified

        To be more precise, the most recent value for `metadata_modified` on a
        dataset.

        Returns a dateTime string in ISO format, or None if it could not be
        found.
        '''
        context = {
            'user': toolkit.get_action('get_site_user')(
                {'ignore_auth': True})['name']
        }
        result = toolkit.get_action('package_search')(context, {
            'sort': 'metadata_modified desc',
            'rows': 1,
        })
        if result and result.get('results'):
            return result['results'][0]['metadata_modified']
        return None

    # Public methods for profiles to implement

    def parse_dataset(self, dataset_dict, dataset_ref):
        '''
        Creates a CKAN dataset dict from the RDF graph

        The `dataset_dict` is passed to all the loaded profiles before being
        yielded, so it can be further modified by each one of them.
        `dataset_ref` is an rdflib URIRef object
        that can be used to reference the dataset when querying the graph.

        Returns a dataset dict that can be passed to eg `package_create`
        or `package_update`
        '''
        return dataset_dict

    def graph_from_catalog(self, catalog_dict, catalog_ref):
        '''
        Creates an RDF graph for the whole catalog (site)

        The class RDFLib graph (accessible via `self.g`) should be updated on
        this method

        `catalog_dict` is a dict that can contain literal values for the
        dcat:Catalog class like `title`, `homepage`, etc. `catalog_ref` is an
        rdflib URIRef object that must be used to reference the catalog when
        working with the graph.
        '''
        pass

    def graph_from_dataset(self, dataset_dict, dataset_ref):
        '''
        Given a CKAN dataset dict, creates an RDF graph

        The class RDFLib graph (accessible via `self.g`) should be updated on
        this method

        `dataset_dict` is a dict with the dataset metadata like the one
        returned by `package_show`. `dataset_ref` is an rdflib URIRef object
        that must be used to reference the dataset when working with the graph.
        '''
        pass


class EuropeanDCATAPProfile(RDFProfile):
    '''
    An RDF profile based on the DCAT-AP for data portals in Europe

    More information and specification:

    https://joinup.ec.europa.eu/asset/dcat_application_profile

    '''

    def parse_dataset(self, dataset_dict, dataset_ref):
        log.debug('Parsing Dataset with IAEST DCAT Profile')
        dataset_dict['tags'] = []
        dataset_dict['extras'] = []
        dataset_dict['resources'] = []
        dataset_dict['groups'] = []

        log.debug('Parsing Keyword')
        # Tags
        keywords = self._object_value_list(dataset_ref, DCAT.keyword) or []
        # Split keywords with commas
        keywords_with_commas = [k for k in keywords if ',' in k]
        for keyword in keywords_with_commas:
            keywords.remove(keyword)
            keywords.extend([k.strip() for k in keyword.split(',')])

        for keyword in keywords:
            dataset_dict['tags'].append({'name': keyword})

        # Basic fields
        log.debug('Parsing Basic Fields')
        for key, predicate in (
                ('title', DCT.title),
                ('notes', DCT.description),
                ('url', DCAT.landingPage),
                ('version', OWL.versionInfo),                
                ):
            value = self._object_value(dataset_ref, predicate)
            if value:
                dataset_dict[key] = value

        # Publisher
        log.debug('Parsing publisher')
        publisher = self._publisher(dataset_ref, DCT.publisher)
        dataset_dict['maintainer'] = publisher.get('title')   
        dataset_dict['author'] = publisher.get('title')    
        dataset_dict['author_email'] = self._object_value(dataset_ref, DCAT.author_email)
        dataset_dict['url'] = publisher.get('url')    

        log.debug('version')
        if not dataset_dict.get('version'):
            # adms:version was supported on the first version of the DCAT-AP
            value = self._object_value(dataset_ref, ADMS.version)
            if value:
                dataset_dict['version'] = value
                log.debug('version obtenida: %s',dataset_dict['version'])
       
        # Extras       
        #TODO Revisar los 0X_ porque alguno deben llevar acentos.
        log.debug('Obteniendo Extras')
        for key, predicate in (
                ('01_IAEST_Tema estadistico', DCAT.tema_estadistico),
                ('04_IAEST_Unidad de medida', DCAT.unidad_medida),
                ('06_IAEST_Periodo base', DCAT.periodo_base),
                ('07_IAEST_Tipo de operacion', DCAT.tipo_operacion),
                ('08_IAEST_Tipologia de datos de origen', DCAT.tipologia_datos_origen),
                ('09_IAEST_Fuente', DCAT.fuente),
                ('11_IAEST_Tratamiento estadistico', DCAT.tratamiento_estadistico),
                ('5_IAEST_Legislacion UE', DCAT.legislacion_ue),                
                ('Data Dictionary URL0',DCAT.urlDictionary),                
                ('Granularity',DCAT.granularity),
                ('LangES',DCAT.language),                
                ('Spatial',DCT.spatial),
                ('TemporalFrom',DCT.temporalFrom),
                ('TemporalUntil',DCT.temporalUntil),
                ('nameAragopedia',DCAT.name_aragopedia),
                ('shortUriAragopedia',DCAT.short_uri_aragopedia),
                ('typeAragopedia',DCAT.type_aragopedia),
                ('uriAragopedia',DCAT.uri_aragopedia),               
                ):
            value = self._object_value(dataset_ref, predicate)
            log.debug(' Key: %s Value:%s',key,value)
            if value:
                dataset_dict['extras'].append({'key': key, 'value': value})
                if key == 'Data Dictionary URL0':
                    dataset_dict['extras'].append({'key': 'Data Dictionary', 'value': 'El diccionario del dato se encuentra en la siguiente url'})

        #Obtener frecuency del nodo accrualPeridicity

        # Dataset URI (explicitly show the missing ones)
        dataset_uri = (unicode(dataset_ref)
                       if isinstance(dataset_ref, rdflib.term.URIRef)
                       else '')
        #dataset_dict['extras'].append({'key': 'uri', 'value': dataset_uri})

       
        # License
       
        license_id_final,license_title_final = self._license(dataset_ref)
        log.debug('Licencias obtenidas %s,%s',license_id_final,license_title_final)
        dataset_dict['license_id'] = license_id_final
        dataset_dict['license_title'] = license_title_final 

       
        log.debug('Tratando themes: ...')
        for theme in self._themes(dataset_ref):
            theme_id = self._object_value(theme, DCT.identifier)
            log.debug('identifier: %s',theme_id)
            if theme_id:
                log.debug('Grupo incluido en RDF: %s',theme_id)
                group = Group.get(theme_id)

                log.debug('Grupo id: %s',group.id )
                dataset_dict['groups'].append({'id':group.id})
                log.debug('dataset_dict[groups]: %s',dataset_dict['groups'])

        log.debug('Procesando resources')
        # Resources
        for distribution in self._distributions(dataset_ref):

            resource_dict = {}

            #  Simple values
            for key, predicate in (
                    ('name', DCT.title),
                    ('description', DCT.description),
                    ('download_url', DCAT.downloadURL),
                    ('issued', DCT.issued),
                    ('modified', DCT.modified),
                    ('status', ADMS.status),
                    ('rights', DCT.rights),
                    ('license', DCT.license),
                    ):
                value = self._object_value(distribution, predicate)
                if value:
                    resource_dict[key] = value

            resource_dict['url'] = (self._object_value(distribution,
                                                       DCAT.accessURL) or
                                    self._object_value(distribution,
                                                       DCAT.downloadURL))
            #  Lists
            for key, predicate in (
                    ('language', DCT.language),
                    ('documentation', FOAF.page),
                    ('conforms_to', DCT.conformsTo),
                    ):
                values = self._object_value_list(distribution, predicate)
                if values:
                    resource_dict[key] = json.dumps(values)

            # Format and media type
            normalize_ckan_format = config.get(
                'ckanext.iaest.normalize_ckan_format', True)
            imt, label = self._distribution_format(distribution,
                                                   normalize_ckan_format)

            if imt:
                resource_dict['mimetype'] = imt

            if label:
                resource_dict['format'] = label
            elif imt:
                resource_dict['format'] = imt

            # Size
            size = self._object_value_int(distribution, DCAT.byteSize)
            if size is not None:
                resource_dict['size'] = size

            # Checksum
            for checksum in self.g.objects(distribution, SPDX.checksum):
                algorithm = self._object_value(checksum, SPDX.algorithm)
                checksum_value = self._object_value(checksum, SPDX.checksumValue)
                if algorithm:
                    resource_dict['hash_algorithm'] = algorithm
                if checksum_value:
                    resource_dict['hash'] = checksum_value

            # Distribution URI (explicitly show the missing ones)
            resource_dict['uri'] = (unicode(distribution)
                                    if isinstance(distribution,
                                                  rdflib.term.URIRef)
                                    else '')

            dataset_dict['resources'].append(resource_dict)

        if self.compatibility_mode:
            # Tweak the resulting dict to make it compatible with previous
            # versions of the ckanext-dcat parsers
            for extra in dataset_dict['extras']:
                if extra['key'] in ('issued', 'modified', 'publisher_name',
                                    'publisher_email',):

                    extra['key'] = 'dcat_' + extra['key']

                if extra['key'] == 'language':
                    extra['value'] = ','.join(
                        sorted(json.loads(extra['value'])))

        return dataset_dict

    def graph_from_dataset(self, dataset_dict, dataset_ref):

        log.debug('Iniciando graph_from_dataset')
        g = self.g

        for prefix, namespace in namespaces.iteritems():
            log.debug('Binding namespace %s with prefix %s',namespace,prefix)
            g.bind(prefix, namespace)

        g.add((dataset_ref, RDF.type, DCAT.Dataset))

        log.debug('Insertando title')
        #Insertamos el titulo con lang es
        title = dataset_dict.get('title')
        g.add((dataset_ref, DCT.title, Literal(title,lang='es')))

        log.debug('Insertando description')
        #Insertamos el titulo con lang es
        notes = dataset_dict.get('notes')
        g.add((dataset_ref, DCT.description, Literal(notes,lang='es')))

        log.debug('Insertando theme')
        #Insertamos los grupos
        #TODO En el RDF original se anade un rdf:resource
        for group in dataset_dict.get('groups'):
             g.add((dataset_ref, DCAT.theme, Literal(group['display_name'])))
        
        # Tags
        for tag in dataset_dict.get('tags', []):
            g.add((dataset_ref, DCAT.keyword, Literal(tag['name'],lang='es')))

        #Identifier
        #TODO Pasar la url por configuracion
        dataset_name = dataset_dict.get('name')
        dataset_identifier = '{0}/catalogo/{1}'.format(catalog_uri().rstrip('/'),dataset_name)
        g.add((dataset_ref, DCT.identifier, Literal(dataset_identifier,datatype='http://www.w3.org/2001/XMLSchema#anyURI')))

        # Dates
        items = [
            ('issued', DCT.issued, ['metadata_created'], Literal),
            ('modified', DCT.modified, ['metadata_modified'], Literal),
        ]
        self._add_date_triples_from_dict(dataset_dict, dataset_ref, items)

        publisher_uri = '{0}/catalogo/{1}'.format(catalog_uri().rstrip('/'),dataset_dict['organization']['name'])
            
        if publisher_uri:
            publisher_details = URIRef(publisher_uri)
        else:
            # No organization nor publisher_uri
            publisher_details = BNode()

        g.add((dataset_ref, DCT.publisher, publisher_details))


        #License
        license_url =  dataset_dict.get('license_url')
        g.add((dataset_ref, DCT.license, URIRef(license_url)))

        #Spatial
        #TODO Revisar los namespaces
        spatial = BNode()
        
        spatial_title = 'aragon'
        spatial_comunidad = 'aragon2'
        spatial_url = 'http://opendata.aragon.es/recurso/territorio/ComunidadAutonoma/Aragon?api_key=e103dc13eb276ad734e680f5855f20c6'

        g.add((spatial, DCT.title, Literal(spatial_title,lang='es')))
        g.add((spatial, ARAGODEF.ComunidadAutonoma, Literal(spatial_comunidad,lang='es')))
        g.add((spatial, RDF.resource, Literal(spatial_url)))
        g.add((dataset_ref, DCT.spatial, spatial))

        #Temporal
        #TODO Introduce nodos Description y no utiliza los prefijos para los namespaces custom
        start = self._get_dataset_value(dataset_dict, 'TemporalFrom')
        end = self._get_dataset_value(dataset_dict, 'TemporalUntil')
        if start or end:
            temporal_extent = BNode()
            timeinterval_extent = BNode()
            

            g.add((temporal_extent, TIME.Interval, timeinterval_extent))
            g.add((timeinterval_extent, RDF.type, URIRef('http://purl.org/dc/terms/PeriodOfTime')))
            
            if start:
                hasBeginning = BNode()
                g.add((timeinterval_extent, TIME.hasBeginning, hasBeginning))

                instant_begin = BNode()
                g.add((hasBeginning, TIME.Instant, instant_begin))
                g.add((instant_begin, TIME.inXSDDate, Literal(start,datatype='http://www.w3.org/2001/XMLSchema#date')))
            if end:
                hasEnd = BNode()
                g.add((timeinterval_extent, TIME.hasEnd, hasEnd))

                instant_end = BNode()
                g.add((hasEnd, TIME.Instant, instant_end))
                g.add((instant_end, TIME.inXSDDate, Literal(end,datatype='http://www.w3.org/2001/XMLSchema#date')))

            g.add((dataset_ref, DCT.temporal, temporal_extent))

        #Incluimos el extra Granularity
        granularity = self._get_dataset_value(dataset_dict, 'Granularity')
        if granularity:
            ref_granularity_extent = BNode()

            g.add((ref_granularity_extent, RDFS.label, Literal('Granularity',lang='es')))
            g.add((ref_granularity_extent, RDFS.value, Literal(granularity,lang='es')))

            g.add((dataset_ref, DCT.references, ref_granularity_extent))

        #incluimos el extra Diccionario de datos y Data Dictionary URL0
        data_dictionary = self._get_dataset_value(dataset_dict, 'Data Dictionary')
        data_dictionary_url = self._get_dataset_value(dataset_dict, 'Data Dictionary URL0')
        if data_dictionary and data_dictionary_url:
            ref_dictionary_extent = BNode()

            g.add((ref_dictionary_extent, RDFS.label, Literal('Data Dictionary',lang='es')))
            g.add((ref_dictionary_extent, RDFS.value, Literal(data_dictionary,lang='es')))
            g.add((ref_dictionary_extent, RDF.resource, Literal(data_dictionary_url)))

            g.add((dataset_ref, DCT.references, ref_dictionary_extent))
        

        # Resources
        for resource_dict in dataset_dict.get('resources', []):

            distribution = URIRef(resource_uri(resource_dict))

            g.add((dataset_ref, DCAT.Distribution, distribution))

            #Identifier
            identifier = resource_uri(resource_dict)
            g.add((distribution, DCT.identifier, Literal(identifier,datatype='http://www.w3.org/2001/XMLSchema#anyURI')))

            #title
            title = resource_dict.get('name')
            g.add((distribution, DCT.title, Literal(title,lang='es')))

            #Description
            description = resource_dict.get('description')
            g.add((distribution, DCT.description, Literal(description,lang='es')))

            #accessUrl
             # URL
            url = resource_dict.get('url')
            download_url = resource_dict.get('download_url')
            if download_url:
                g.add((distribution, DCAT.downloadURL, Literal(download_url,datatype='http://www.w3.org/2001/XMLSchema#anyURI')))
            if (url and not download_url) or (url and url != download_url):
                g.add((distribution, DCAT.accessURL, Literal(url,datatype='http://www.w3.org/2001/XMLSchema#anyURI')))

            #format
            format_res = resource_dict.get('format')
            #TODO En el importador nos se esta rellenando el mimetype_inner
            mimetype_inner_res = resource_dict.get('mimetype_inner')
            if format_res:

                format_extent = BNode()
                mediatype_extent = BNode()

                g.add((mediatype_extent, RDFS.value, Literal(mimetype_inner_res)))
                g.add((mediatype_extent, RDFS.label, Literal(format_res)))

                g.add((format_extent, DCT.MediaType, mediatype_extent))
                g.add((distribution, DCT['format'], format_extent))
                

        
    def graph_from_catalog(self, catalog_dict, catalog_ref):

        g = self.g

        log.debug('Generando RDF IAEST')
        for prefix, namespace in namespaces.iteritems():
            g.bind(prefix, namespace)

        g.add((catalog_ref, RDF.type, DCAT.Catalog))

        # Basic fields
        items = [
            ('title', DCT.title, config.get('ckan.site_title'), Literal),
            ('description', DCT.description, config.get('ckan.site_description'), Literal),
            ('homepage', FOAF.homepage, config.get('ckan.site_url'), URIRef),
            ('language', DCT.language, config.get('ckan.locale_default', 'en'), Literal),
        ]
        for item in items:
            key, predicate, fallback, _type = item
            if catalog_dict:
                value = catalog_dict.get(key, fallback)
            else:
                value = fallback
            if value:
                g.add((catalog_ref, predicate, _type(value)))

        # Dates
        modified = self._last_catalog_modification()
        if modified:
            self._add_date_triple(catalog_ref, DCT.modified, modified)
