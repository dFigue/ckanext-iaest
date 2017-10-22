import logging

log = logging.getLogger(__name__)


def iaest_to_ckan(iaest_dict):

    package_dict = {}

    package_dict['title'] = iaest_dict.get('title')
    package_dict['notes'] = iaest_dict.get('description')
    package_dict['url'] = iaest_dict.get('landingPage')


    package_dict['tags'] = []
    for keyword in iaest_dict.get('keyword', []):
        package_dict['tags'].append({'name': keyword})

    package_dict['extras'] = []
    for key in ['issued', 'modified']:
        package_dict['extras'].append({'key': 'iaest_{0}'.format(key), 'value': iaest_dict.get(key)})

    package_dict['extras'].append({'key': 'guid', 'value': iaest_dict.get('identifier')})

    #PRUEBA
    package_dict['extras'].append({'key': 'miKey', 'value': 'Esta es mi KEY'})

    iaest_publisher = iaest_dict.get('publisher')
    if isinstance(iaest_publisher, basestring):
        package_dict['extras'].append({'key': 'iaest_publisher_name', 'value': iaest_publisher})
    elif isinstance(iaest_publisher, dict) and iaest_publisher.get('name'):
        package_dict['extras'].append({'key': 'iaest_publisher_name', 'value': iaest_publisher.get('name')})
        package_dict['extras'].append({'key': 'iaest_publisher_email', 'value': iaest_publisher.get('mbox')})

    package_dict['extras'].append({
        'key': 'language',
        'value': ','.join(iaest_dict.get('language', []))
    })

    package_dict['resources'] = []
    for distribution in iaest_dict.get('distribution', []):
        resource = {
            'name': distribution.get('title'),
            'description': distribution.get('description'),
            'url': distribution.get('downloadURL') or distribution.get('accessURL'),
            'format': distribution.get('format'),
        }

        if distribution.get('byteSize'):
            try:
                resource['size'] = int(distribution.get('byteSize'))
            except ValueError:
                pass
        package_dict['resources'].append(resource)

    return package_dict


def ckan_to_iaest(package_dict):

    iaest_dict = {}

    iaest_dict['title'] = package_dict.get('title')
    iaest_dict['description'] = package_dict.get('notes')
    iaest_dict['landingPage'] = package_dict.get('url')


    iaest_dict['keyword'] = []
    for tag in package_dict.get('tags', []):
        iaest_dict['keyword'].append(tag['name'])


    iaest_dict['publisher'] = {}

    for extra in package_dict.get('extras', []):
        if extra['key'] in ['iaest_issued', 'iaest_modified']:
            iaest_dict[extra['key'].replace('iaest_', '')] = extra['value']

        elif extra['key'] == 'language':
            iaest_dict['language'] = extra['value'].split(',')

        elif extra['key'] == 'iaest_publisher_name':
            iaest_dict['publisher']['name'] = extra['value']

        elif extra['key'] == 'iaest_publisher_email':
            iaest_dict['publisher']['mbox'] = extra['value']

        elif extra['key'] == 'guid':
            iaest_dict['identifier'] = extra['value']

    if not iaest_dict['publisher'].get('name') and package_dict.get('maintainer'):
        iaest_dict['publisher']['name'] = package_dict.get('maintainer')
        if package_dict.get('maintainer_email'):
            iaest_dict['publisher']['mbox'] = package_dict.get('maintainer_email')

    iaest_dict['distribution'] = []
    for resource in package_dict.get('resources', []):
        distribution = {
            'title': resource.get('name'),
            'description': resource.get('description'),
            'format': resource.get('format'),
            'byteSize': resource.get('size'),
            # TODO: downloadURL or accessURL depending on resource type?
            'accessURL': resource.get('url'),
            'license':'cc-by-4.0'
        }
        iaest_dict['distribution'].append(distribution)

    return iaest_dict
