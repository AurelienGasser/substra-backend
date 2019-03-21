import json
import ntpath
import os

from checksumdir import dirhash
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from rest_framework import status

from substrapp.serializers.data import AdminDataSerializer, DataSerializer
from substrapp.views import DataViewSet
from substrapp.utils import get_hash, get_dir_hash
from substrapp.views.data import LedgerException


def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


class Command(BaseCommand):
    help = '''
    Bulk create data
    python ./manage.py bulkcreatedata '{"files": ["./data1.zip", "./data2.zip"], "dataset_keys": ["bcfdad31dbe9163e9f254a2b9a485f2dd5d035ecce4a1331788039f2bccdf7af"], "test_only": false}'
    python ./manage.py bulkcreatedata '{"paths": ["./train/data", "./train/data2"], "dataset_key": "b4d2deeb9a59944d608e612abc8595c49186fa24075c4eb6f5e6050e4f9affa0", "test_only": false}'
    python ./manage.py bulkcreatedata data.json
    # data.json:
    # {"files": ["./data1.zip", "./data2.zip"], "dataset_keys": ["bcfdad31dbe9163e9f254a2b9a485f2dd5d035ecce4a1331788039f2bccdf7af"], "test_only": false}
    # {"paths": ["./train/data", "./train/data2"], "dataset_key": "b4d2deeb9a59944d608e612abc8595c49186fa24075c4eb6f5e6050e4f9affa0", "test_only": false}
    '''

    def add_arguments(self, parser):
        parser.add_argument('data', type=str)

    def handle(self, *args, **options):

        # load args
        args = options['data']
        try:
            data = json.loads(args)
        except:
            try:
                with open(args, 'r') as f:
                    data = json.load(f)
            except:
                raise CommandError('Invalid args. Please review help')
        else:
            if not isinstance(data, dict):
                raise CommandError('Invalid args. Please provide a valid json file.')

        dataset_keys = data.get('dataset_keys', [])
        if not type(dataset_keys) == list:
            return self.stderr.write('The dataset_keys you provided is not an array')

        test_only = data.get('test_only', False)
        data_files = data.get('files', None)
        paths = data.get('paths', [])

        try:
            DataViewSet.check_datasets(dataset_keys)
        except Exception as e:
            self.stderr.write(str(e))
        else:
            files = {}
            if data_files and type(data_files) == list:
                for file in data_files:
                    if os.path.exists(file):
                        with open(file, 'rb') as f:
                            filename = path_leaf(file)
                            files[filename] = ContentFile(f.read(), filename)
                    else:
                        return self.stderr.write(f'File: {file} does not exist.')
            # bulk
            if files:
                l = []
                for x in files:
                    file = files[path_leaf(x)]
                    try:
                        pkhash = get_dir_hash(file)
                    except Exception as e:
                        return self.stderr.write(str(e))
                    else:
                        # check pkhash does not belong to the list
                        for x in l:
                            if pkhash == x['pkhash']:
                                return self.stderr.write({'message': f'Your data archives contain same files leading to same pkhash, please review the content of your achives. Archives {file} and {x["file"]} are the same'})
                        l.append({
                            'pkhash': pkhash,
                            'file': file
                        })

                many = True

                #[{'path': x, 'pkhash': dirhash(x, 'sha256')} for x in paths]
                serializer = DataSerializer(data=l, many=many)
                try:
                    serializer.is_valid(raise_exception=True)
                except Exception as e:
                    return self.stderr.write(str(e))
                else:
                    # create on ledger + db
                    ledger_data = {'test_only': test_only,
                                   'dataset_keys': dataset_keys}
                    try:
                        data, st = DataViewSet.commit(serializer, ledger_data, many)
                    except LedgerException as e:
                        if e.st == status.HTTP_408_REQUEST_TIMEOUT:
                            self.stdout.write(self.style.WARNING(json.dumps(e.data, indent=2)))
                        else:
                            self.stderr.write(json.dumps(e.data, indent=2))
                    except Exception as e:
                        self.stderr.write(str(e))
                    else:
                        msg = f'Succesfully added data via bulk with status code {st} and data: {json.dumps(data, indent=4)}'
                        self.stdout.write(self.style.SUCCESS(msg))
