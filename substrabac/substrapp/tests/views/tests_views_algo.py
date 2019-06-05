import os
import shutil
import logging

import mock

from django.urls import reverse
from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase


from substrapp.serializers import LedgerAlgoSerializer

from substrapp.utils import JsonException
from substrapp.utils import get_hash

from ..common import get_sample_algo
from ..common import FakeRequest
from ..assets import objective, datamanager, algo, traintuple, model

MEDIA_ROOT = "/tmp/unittests_views/"


# APITestCase
@override_settings(MEDIA_ROOT=MEDIA_ROOT)
@override_settings(DRYRUN_ROOT=MEDIA_ROOT)
@override_settings(SITE_HOST='localhost')
@override_settings(LEDGER={'name': 'test-org', 'peer': 'test-peer'})
class AlgoViewTests(APITestCase):

    def setUp(self):
        if not os.path.exists(MEDIA_ROOT):
            os.makedirs(MEDIA_ROOT)

        self.algo, self.algo_filename = get_sample_algo()

        self.extra = {
            'HTTP_ACCEPT': 'application/json;version=0.0'
        }
        self.logger = logging.getLogger('django.request')
        self.previous_level = self.logger.getEffectiveLevel()
        self.logger.setLevel(logging.ERROR)

    def tearDown(self):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

        self.logger.setLevel(self.previous_level)

    def test_algo_list_empty(self):
        url = reverse('substrapp:algo-list')
        with mock.patch('substrapp.views.algo.query_ledger') as mquery_ledger:
            mquery_ledger.side_effect = [(None, status.HTTP_200_OK),
                                         (['ISIC'], status.HTTP_200_OK)]

            response = self.client.get(url, **self.extra)
            r = response.json()
            self.assertEqual(r, [[]])

            response = self.client.get(url, **self.extra)
            r = response.json()
            self.assertEqual(r, [['ISIC']])

    def test_algo_list_filter_fail(self):
        url = reverse('substrapp:algo-list')
        with mock.patch('substrapp.views.algo.query_ledger') as mquery_ledger:
            mquery_ledger.side_effect = [(algo, status.HTTP_200_OK)]

            search_params = '?search=algERRORo'
            response = self.client.get(url + search_params, **self.extra)
            r = response.json()

            self.assertIn('Malformed search filters', r['message'])

    def test_algo_list_filter_name(self):
        url = reverse('substrapp:algo-list')
        with mock.patch('substrapp.views.algo.query_ledger') as mquery_ledger:
            mquery_ledger.side_effect = [(algo, status.HTTP_200_OK)]

            search_params = '?search=algo%253Aname%253ALogistic%2520regression'
            response = self.client.get(url + search_params, **self.extra)
            r = response.json()

            self.assertEqual(len(r[0]), 1)

    def test_algo_list_filter_datamanager_fail(self):
        url = reverse('substrapp:algo-list')
        with mock.patch('substrapp.views.algo.query_ledger') as mquery_ledger, \
                mock.patch('substrapp.views.filters_utils.query_ledger') as mquery_ledger2:
            mquery_ledger.side_effect = [(algo, status.HTTP_200_OK)]
            mquery_ledger2.side_effect = [(datamanager, status.HTTP_200_OK)]

            search_params = '?search=dataset%253Aname%253ASimplified%2520ISIC%25202018'
            response = self.client.get(url + search_params, **self.extra)
            r = response.json()

            self.assertIn('Malformed search filters', r['message'])

    def test_algo_list_filter_objective_fail(self):
        url = reverse('substrapp:algo-list')
        with mock.patch('substrapp.views.algo.query_ledger') as mquery_ledger, \
                mock.patch('substrapp.views.filters_utils.query_ledger') as mquery_ledger2:
            mquery_ledger.side_effect = [(algo, status.HTTP_200_OK)]
            mquery_ledger2.side_effect = [(objective, status.HTTP_200_OK)]

            search_params = '?search=objective%253Aname%253ASkin%2520Lesion%2520Classification%2520Objective'
            response = self.client.get(url + search_params, **self.extra)
            r = response.json()

            self.assertIn('Malformed search filters', r['message'])

    def test_algo_list_filter_model(self):
        url = reverse('substrapp:algo-list')
        with mock.patch('substrapp.views.algo.query_ledger') as mquery_ledger, \
                mock.patch('substrapp.views.filters_utils.query_ledger') as mquery_ledger2:
            mquery_ledger.side_effect = [(algo, status.HTTP_200_OK)]
            mquery_ledger2.side_effect = [(traintuple, status.HTTP_200_OK)]

            pkhash = model[0]['traintuple']['outModel']['hash']
            search_params = f'?search=model%253Ahash%253A{pkhash}'
            response = self.client.get(url + search_params, **self.extra)
            r = response.json()

            self.assertEqual(len(r[0]), 1)

    def test_algo_retrieve(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        algo_hash = get_hash(os.path.join(dir_path, '../../../../fixtures/chunantes/algos/algo4/algo.tar.gz'))
        url = reverse('substrapp:algo-list')
        algo_response = [a for a in algo if a['key'] == algo_hash][0]
        with mock.patch('substrapp.views.algo.get_object_from_ledger') as mget_object_from_ledger, \
                mock.patch('substrapp.views.algo.get_from_node') as mrequestsget:

            with open(os.path.join(dir_path,
                                   '../../../../fixtures/chunantes/algos/algo4/description.md'), 'rb') as f:
                content = f.read()
            mget_object_from_ledger.return_value = algo_response

            mrequestsget.return_value = FakeRequest(status=status.HTTP_200_OK,
                                                    content=content)

            search_params = f'{algo_hash}/'
            response = self.client.get(url + search_params, **self.extra)
            r = response.json()

            self.assertEqual(r, algo_response)

    def test_algo_retrieve_fail(self):

        dir_path = os.path.dirname(os.path.realpath(__file__))
        url = reverse('substrapp:algo-list')

        # PK hash < 64 chars
        search_params = '42303efa663015e729159833a12ffb510ff/'
        response = self.client.get(url + search_params, **self.extra)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # PK hash not hexa
        search_params = 'X' * 64 + '/'
        response = self.client.get(url + search_params, **self.extra)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        with mock.patch('substrapp.views.algo.get_object_from_ledger') as mget_object_from_ledger:
            mget_object_from_ledger.side_effect = JsonException('TEST')

            file_hash = get_hash(os.path.join(dir_path,
                                              "../../../../fixtures/owkin/objectives/objective0/description.md"))
            search_params = f'{file_hash}/'
            response = self.client.get(url + search_params, **self.extra)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_algo_create(self):
        url = reverse('substrapp:algo-list')

        dir_path = os.path.dirname(os.path.realpath(__file__))

        algo_path = os.path.join(dir_path, '../../../../fixtures/chunantes/algos/algo3/algo.tar.gz')
        description_path = os.path.join(dir_path, '../../../../fixtures/chunantes/algos/algo3/description.md')

        pkhash = get_hash(algo_path)

        data = {'name': 'Logistic regression',
                'file': open(algo_path, 'rb'),
                'description': open(description_path, 'rb'),
                'objective_key': get_hash(os.path.join(
                    dir_path, '../../../../fixtures/chunantes/objectives/objective0/description.md')),
                'permissions': 'all'}

        with mock.patch.object(LedgerAlgoSerializer, 'create') as mcreate:

            mcreate.return_value = ({},
                                    status.HTTP_201_CREATED)

            response = self.client.post(url, data=data, format='multipart', **self.extra)

        self.assertEqual(response.data['pkhash'], pkhash)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data['description'].close()
        data['file'].close()
