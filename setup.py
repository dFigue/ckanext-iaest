from setuptools import setup, find_packages

version = '0.0.6'

setup(
    name='ckanext-iaest',
    version=version,
    description="Plugins for exposing and consuming IAEST metadata on CKAN",
    long_description='''\
    ''',
    classifiers=[],
    keywords='',
    author='Open Knowledge Foundation',
    author_email='info@ckan.org',
    url='https://github.com/okfn/ckanext-iaest',
    license='AGPL',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    namespace_packages=['ckanext', 'ckanext.iaest'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        # -*- Extra requirements: -*-
    ],
    entry_points='''

    [ckan.plugins]
    iaest_xml_harvester=ckanext.iaest.harvesters:IAESTXMLHarvester
    iaest_json_harvester=ckanext.iaest.harvesters:IAESTJSONHarvester

    iaest_rdf_harvester=ckanext.iaest.harvesters:IAESTRDFHarvester

    iaest_json_interface=ckanext.iaest.plugins:IAESTJSONInterface

    iaest=ckanext.iaest.plugins:IAESTPlugin

    # Test plugins
    test_rdf_harvester=ckanext.iaest.tests.test_harvester:TestRDFHarvester
    test_rdf_null_harvester=ckanext.iaest.tests.test_harvester:TestRDFNullHarvester
    test_rdf_exception_harvester=ckanext.iaest.tests.test_harvester:TestRDFExceptionHarvester

    [ckan.rdf.profiles]
    euro_iaest_ap=ckanext.iaest.profiles:EuropeanIAESTAPProfile

    [paste.paster_command]
    generate_static = ckanext.iaest.commands:GenerateStaticIAESTCommand

    [babel.extractors]
    ckan = ckan.lib.extract:extract_ckan
    ''',
    message_extractors={
        'ckanext': [
            ('**.py', 'python', None),
            ('**.js', 'javascript', None),
            ('**/templates/**.html', 'ckan', None),
        ],
    },
)
