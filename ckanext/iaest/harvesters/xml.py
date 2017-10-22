from ckan import plugins as p


msg = '''
[ckanext-iaest] The XML harvester (iaest_xml_harvester) is DEPRECATED, please use
the generic RDF harvester (iaest_rdf_harvester) instead. Check the following for
more details:
   https://github.com/ckan/ckanext-iaest#xml-iaest-harvester-deprecated
'''


class IAESTXMLHarvester(p.SingletonPlugin):

    p.implements(p.IConfigurer, inherit=True)

    def update_config(self, config):

        raise Exception(msg)
