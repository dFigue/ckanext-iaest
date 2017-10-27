Clone for: https://github.com/ckan/ckanext-dcat.git#egg=ckanext-dcat

## Installation

1.  Install ckanext-harvest ([https://github.com/ckan/ckanext-harvest#installation](https://github.com/ckan/ckanext-harvest#installation)) (Only if you want to use the RDF harvester)

2.  Install the extension on your virtualenv:

        (pyenv) $ pip install -e git+https://github.com/dFigue/ckanext-iaest.git#egg=ckanext-iaest

3.  Install the extension requirements:

        (pyenv) $ pip install -r ckanext-dcat/requirements.txt

4.  Enable the required plugins in your ini file:

        ckan.plugins = dcat dcat_rdf_harvester dcat_json_harvester dcat_json_interface
