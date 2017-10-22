# ckan-iaest

Extension of https://github.com/ckan/ckanext-dcat

Installation


Install ckanext-harvest (https://github.com/ckan/ckanext-harvest#installation) (Only if you want to use the RDF harvester)

Install the extension on your virtualenv:

(pyenv) $ pip install -e git+https://github.com/ckan/ckanext-dcat.git#egg=ckanext-dcat
Install the extension requirements:

(pyenv) $ pip install -r ckanext-dcat/requirements.txt
Enable the required plugins in your ini file:

ckan.plugins = dcat dcat_rdf_harvester dcat_json_harvester dcat_json_interface
