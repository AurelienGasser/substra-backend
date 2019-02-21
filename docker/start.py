import os
import json
import argparse

from subprocess import call, check_output

dir_path = os.path.dirname(os.path.realpath(__file__))


def generate_docker_compose_file(conf, launch_settings):
    try:
        from ruamel import yaml
    except ImportError:
        import yaml

    # Docker compose config
    docker_compose = {'substrabac_services': {},
                      'substrabac_tools': {'postgresql': {'container_name': 'postgresql',
                                                          'image': 'library/postgres:10.5',
                                                          'restart': 'unless-stopped',
                                                          'environment': ['POSTGRES_USER=substrabac',
                                                                          'USER=substrabac',
                                                                          'POSTGRES_PASSWORD=substrabac',
                                                                          'POSTGRES_DB=substrabac'],
                                                          'volumes': [
                                                              '/substra/backup/postgres-data:/var/lib/postgresql/data',
                                                              f'{dir_path}/postgresql/init.sh:/docker-entrypoint-initdb.d/init.sh'],
                                                          },
                                           'celerybeat': {'container_name': 'celerybeat',
                                                          'hostname': 'celerybeat',
                                                          'image': 'substra/celerybeat',
                                                          'restart': 'unless-stopped',
                                                          'command': '/bin/bash -c "while ! { nc -z rabbit 5672 2>&1; }; do sleep 1; done; while ! { nc -z postgresql 5432 2>&1; }; do sleep 1; done; celery -A substrabac beat -l info -b rabbit"',
                                                          'logging': {'driver': 'json-file', 'options': {'max-size': '20m', 'max-file': '5'}},
                                                          'environment': ['PYTHONUNBUFFERED=1',
                                                                          f'DJANGO_SETTINGS_MODULE=substrabac.settings.{launch_settings}'],
                                                          'volumes': ['/substra:/substra'],
                                                          'depends_on': ['postgresql', 'rabbit']
                                                          },
                                           'rabbit': {'container_name': 'rabbit',
                                                      'hostname': 'rabbitmq',     # Must be set to be able to recover from volume
                                                      'restart': 'unless-stopped',
                                                      'image': 'rabbitmq:3',
                                                      'environment': ['RABBITMQ_DEFAULT_USER=guest',
                                                                      'RABBITMQ_DEFAULT_PASS=guest',
                                                                      'HOSTNAME=rabbitmq',
                                                                      'RABBITMQ_NODENAME=rabbitmq'],
                                                      'volumes': ['/substra/backup/rabbit-data:/var/lib/rabbitmq']
                                                      },
                                           },
                      'path': os.path.join(dir_path, './docker-compose-dynamic.yaml')}

    for org in conf['orgs']:
        org_name = org['name']
        org_name_stripped = org_name.replace('-', '')

        port = 8000
        if org_name_stripped == 'chunantes':
            port = 8001

        backend = {'container_name': f'{org_name_stripped}.substrabac',
                   'image': 'substra/substrabac',
                   'restart': 'unless-stopped',
                   'ports': [f'{port}:{port}'],
                   'command': f'/bin/bash -c "while ! {{ nc -z postgresql 5432 2>&1; }}; do sleep 1; done; yes | python manage.py migrate --settings=substrabac.settings.{launch_settings}.{org_name_stripped}; python3 manage.py collectstatic --noinput; python3 manage.py runserver 0.0.0.0:{port}"',
                   'logging': {'driver': 'json-file', 'options': {'max-size': '20m', 'max-file': '5'}},
                   'environment': ['DATABASE_HOST=postgresql',
                                   f'DJANGO_SETTINGS_MODULE=substrabac.settings.{launch_settings}.{org_name_stripped}',
                                   'PYTHONUNBUFFERED=1',
                                   f"BACK_AUTH_USER={os.environ.get('BACK_AUTH_USER', '')}",
                                   f"BACK_AUTH_PASSWORD={os.environ.get('BACK_AUTH_PASSWORD', '')}",
                                   f"FABRIC_CFG_PATH_ENV={org['peers'][0]['docker_core_dir']}",
                                   f"CORE_PEER_ADDRESS_ENV={org['peers'][0]['host']}:{org['peers'][0]['port']}",
                                   f"SITE_HOST={os.environ.get('SITE_HOST', 'localhost')}",
                                   f"SITE_PORT={os.environ.get('BACK_PORT', 9000)}",],
                   'volumes': ['/substra:/substra',
                               '/substra/static:/usr/src/app/substrabac/statics',
                               f'/substra/data/orgs/{org_name}/user/msp:/opt/gopath/src/github.com/hyperledger/fabric/peer/msp'],
                   'depends_on': ['postgresql', 'rabbit']}

        # Celery worker and scheduler concurrency
        celeryd_concurrency = int(os.environ.get('CELERYD_CONCURRENCY', 1))

        scheduler = {'container_name': f'{org_name_stripped}.scheduler',
                     'hostname': f'{org_name}.scheduler',
                     'image': 'substra/celeryworker',
                     'restart': 'unless-stopped',
                     'command': f'/bin/bash -c "while ! {{ nc -z rabbit 5672 2>&1; }}; do sleep 1; done; while ! {{ nc -z postgresql 5432 2>&1; }}; do sleep 1; done; celery -A substrabac worker -l info -c {celeryd_concurrency} -n {org_name_stripped} -Q {org_name},scheduler,celery -b rabbit --hostname {org_name}.scheduler"',
                     'logging': {'driver': 'json-file', 'options': {'max-size': '20m', 'max-file': '5'}},
                     'environment': [f'ORG={org_name_stripped}',
                                     f'DJANGO_SETTINGS_MODULE=substrabac.settings.{launch_settings}.{org_name_stripped}',
                                     'PYTHONUNBUFFERED=1',
                                     f"CELERYD_CONCURRENCY={celeryd_concurrency}",
                                     f"BACK_AUTH_USER={os.environ.get('BACK_AUTH_USER', '')}",
                                     f"BACK_AUTH_PASSWORD={os.environ.get('BACK_AUTH_PASSWORD', '')}",
                                     f"SITE_HOST={os.environ.get('SITE_HOST', 'localhost')}",
                                     f"SITE_PORT={os.environ.get('BACK_PORT', 9000)}",
                                     'DATABASE_HOST=postgresql',
                                     f"FABRIC_CFG_PATH_ENV={org['peers'][0]['docker_core_dir']}",
                                     f"CORE_PEER_ADDRESS_ENV={org['peers'][0]['host']}:{org['peers'][0]['port']}"],
                     'volumes': ['/substra:/substra',
                                 '/var/run/docker.sock:/var/run/docker.sock',
                                 f'/substra/data/orgs/{org_name}/user/msp:/opt/gopath/src/github.com/hyperledger/fabric/peer/msp'],
                     'depends_on': [f'substrabac{org_name_stripped}', 'postgresql', 'rabbit']}

        worker = {'container_name': f'{org_name_stripped}.worker',
                  'hostname': f'{org_name}.worker',
                  'image': 'substra/celeryworker',
                  'restart': 'unless-stopped',
                  'command': f'/bin/bash -c "while ! {{ nc -z rabbit 5672 2>&1; }}; do sleep 1; done; while ! {{ nc -z postgresql 5432 2>&1; }}; do sleep 1; done; celery -A substrabac worker -l info -c {celeryd_concurrency} -n {org_name_stripped} -Q {org_name},{org_name}.worker,celery -b rabbit --hostname {org_name}.worker"',
                  'logging': {'driver': 'json-file', 'options': {'max-size': '20m', 'max-file': '5'}},
                  'environment': [f'ORG={org_name_stripped}',
                                  f'DJANGO_SETTINGS_MODULE=substrabac.settings.{launch_settings}.{org_name_stripped}',
                                  'PYTHONUNBUFFERED=1',
                                  f"CELERYD_CONCURRENCY={celeryd_concurrency}",
                                  f"BACK_AUTH_USER={os.environ.get('BACK_AUTH_USER', '')}",
                                  f"BACK_AUTH_PASSWORD={os.environ.get('BACK_AUTH_PASSWORD', '')}",
                                  f"SITE_HOST={os.environ.get('SITE_HOST', 'localhost')}",
                                  f"SITE_PORT={os.environ.get('BACK_PORT', 9000)}",
                                  'DATABASE_HOST=postgresql',
                                  f"FABRIC_CFG_PATH_ENV={org['peers'][0]['docker_core_dir']}",
                                  f"CORE_PEER_ADDRESS_ENV={org['peers'][0]['host']}:{org['peers'][0]['port']}"],
                  'volumes': ['/substra:/substra',
                              '/var/run/docker.sock:/var/run/docker.sock',
                              f'/substra/data/orgs/{org_name}/user/msp:/opt/gopath/src/github.com/hyperledger/fabric/peer/msp'],
                  'depends_on': [f'substrabac{org_name_stripped}', 'rabbit']}

        dryrunner = {'container_name': f'{org_name_stripped}.dryrunner',
                     'hostname': f'{org_name}.dryrunner',
                     'image': 'substra/celeryworker',
                     'restart': 'unless-stopped',
                     'command': f'/bin/bash -c "while ! {{ nc -z rabbit 5672 2>&1; }}; do sleep 1; done; while ! {{ nc -z postgresql 5432 2>&1; }}; do sleep 1; done; celery -A substrabac worker -l info -c {celeryd_concurrency} -n {org_name_stripped} -Q {org_name},{org_name}.dryrunner,celery -b rabbit --hostname {org_name}.dryrunner"',
                     'logging': {'driver': 'json-file', 'options': {'max-size': '20m', 'max-file': '5'}},
                     'environment': [f'ORG={org_name_stripped}',
                                     f'DJANGO_SETTINGS_MODULE=substrabac.settings.{launch_settings}.{org_name_stripped}',
                                     'PYTHONUNBUFFERED=1',
                                     f"CELERYD_CONCURRENCY={celeryd_concurrency}",
                                     f"BACK_AUTH_USER={os.environ.get('BACK_AUTH_USER', '')}",
                                     f"BACK_AUTH_PASSWORD={os.environ.get('BACK_AUTH_PASSWORD', '')}",
                                     f"SITE_HOST={os.environ.get('SITE_HOST', 'localhost')}",
                                     f"SITE_PORT={os.environ.get('BACK_PORT', 9000)}",
                                     'DATABASE_HOST=postgresql',
                                     f"FABRIC_CFG_PATH_ENV={org['peers'][0]['docker_core_dir']}",
                                     f"CORE_PEER_ADDRESS_ENV={org['peers'][0]['host']}:{org['peers'][0]['port']}"],
                     'volumes': ['/substra:/substra',
                                 '/var/run/docker.sock:/var/run/docker.sock',
                                 f'/substra/data/orgs/{org_name}/user/msp:/opt/gopath/src/github.com/hyperledger/fabric/peer/msp'],
                     'depends_on': [f'substrabac{org_name_stripped}', 'rabbit']}

        # Check if we have nvidia docker
        if 'nvidia' in check_output(['docker', 'system', 'info', '-f', '"{{.Runtimes}}"']).decode('utf-8'):
            worker['runtime'] = 'nvidia'

        if launch_settings == 'dev':
            media_root = f'MEDIA_ROOT=/substra/medias/{org_name_stripped}'
            worker['environment'].append(media_root)
            dryrunner['environment'].append(media_root)
            backend['environment'].append(media_root)

        docker_compose['substrabac_services']['substrabac' + org_name_stripped] = backend
        docker_compose['substrabac_services']['scheduler' + org_name_stripped] = scheduler
        docker_compose['substrabac_services']['worker' + org_name_stripped] = worker
        docker_compose['substrabac_services']['dryrunner' + org_name_stripped] = dryrunner
    # Create all services along to conf

    COMPOSITION = {'services': {}, 'version': '2.3', 'networks': {'default': {'external': {'name': 'net_substra'}}}}

    for name, dconfig in docker_compose['substrabac_services'].items():
        COMPOSITION['services'][name] = dconfig

    for name, dconfig in docker_compose['substrabac_tools'].items():
        COMPOSITION['services'][name] = dconfig

    with open(docker_compose['path'], 'w+') as f:
        f.write(yaml.dump(COMPOSITION, default_flow_style=False, indent=4, line_break=None))

    return docker_compose


def stop(docker_compose=None):
    print('stopping container', flush=True)

    if docker_compose is not None:
        call(['docker-compose', '-f', docker_compose['path'], '--project-directory',
              os.path.join(dir_path, '../'), 'down', '--remove-orphans'])
    else:
        call(['docker-compose', '-f', os.path.join(dir_path, './docker-compose.yaml'), '--project-directory',
              os.path.join(dir_path, '../'), 'down', '--remove-orphans'])


def start(conf, launch_settings, no_backup):
    print('Generate docker-compose file\n')
    docker_compose = generate_docker_compose_file(conf, launch_settings)

    stop(docker_compose)

    if no_backup:
        print('Clean medias directory\n')
        call(['sh', os.path.join(dir_path, '../substrabac/scripts/clean_media.sh')])
        print('Remove postgresql database\n')
        call(['rm', '-rf', '/substra/backup/postgres-data'])
        print('Remove rabbit database\n')
        call(['rm', '-rf', '/substra/backup/rabbit-data'])

    print('start docker-compose', flush=True)
    call(['docker-compose', '-f', docker_compose['path'], '--project-directory',
          os.path.join(dir_path, '../'), 'up', '-d', '--remove-orphans', '--build'])
    call(['docker', 'ps', '-a'])


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dev', action='store_true', default=False,
                        help="use dev settings")
    parser.add_argument('--no-backup', action='store_true', default=False,
                        help="Remove backup binded volume, medias and db data. Launch from scratch")
    args = vars(parser.parse_args())

    if args['dev']:
        launch_settings = 'dev'
    else:
        launch_settings = 'prod'

    no_backup = args['no_backup']

    conf = json.load(open('/substra/conf/conf.json', 'r'))

    print('Build substrabac for : ', flush=True)
    print('  Organizations :', flush=True)
    for org in conf['orgs']:
        print('   -', org['name'], flush=True)

    print('', flush=True)

    start(conf, launch_settings, no_backup)
