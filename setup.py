from setuptools import setup, find_packages

version = '0.1.0'

setup(
    name='ckanext-iaest',
    version=version,
    description="Aragon Opendata IAEST Harvester for CKAN",
    long_description="",
    classifiers=[],  # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
    keywords='',
    author='dFigue - Aragon Opendata',
    author_email='david.figueroa.alejandro@gmail.com',
    url='https://github.com/dFigue/ckanext-iaest.git',
    license='AGPL',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    namespace_packages=['ckanext', 'ckanext.iaest'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'ckanext-harvest'
    ],
    entry_points="""
        [ckan.plugins]
        iaeset=ckanext.iaest.plugin:IAESTPlugin
        iaest_harvester=ckanext.iaest.harvester:IAESTHarvester        
        """,
)
