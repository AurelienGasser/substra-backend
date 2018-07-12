from rest_framework import serializers, status

from substrapp.conf import conf
from substrapp.models import Algo
from substrapp.models.utils import compute_hash
from substrapp.utils import invokeLedger


class LedgerAlgoSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=60)
    challenge_key = serializers.CharField(min_length=1, max_length=256)
    permissions = serializers.CharField(min_length=1, max_length=60)

    def create(self, validated_data):
        instance = self.initial_data.get('instance')
        name = validated_data.get('name')
        permissions = validated_data.get('permissions')
        challenge_key = validated_data.get('challenge_key')

        # TODO use asynchrone task for calling ledger

        # TODO put in settings
        org = conf['orgs']['chu-nantes']
        peer = org['peers'][0]

        args = '"%(name)s", "%(algoHash)s", "%(storageAddress)s", "%(descriptionHash)s", "%(descriptionStorageAddress)s", "%(associatedChallenge)s", "%(permissions)s"' % {
            'name': name,
            'algoHash': compute_hash(instance.file),
            'storageAddress': instance.file.path,
            'descriptionHash': compute_hash(instance.description),
            'descriptionStorageAddress': instance.description.path,
            'associatedChallenge': challenge_key,
            'permissions': permissions
        }

        options = {
            'org': org,
            'peer': peer,
            'args': '{"Args":["registerAlgo", ' + args + ']}'
        }
        data, st = invokeLedger(options)

        # TODO : remove when using celery tasks
        #  if not created on ledger, delete from local db
        if st != status.HTTP_201_CREATED:
            Algo.objects.get(pk=instance.pkhash).delete()
        else:
            instance.validated = True
            instance.save()
            # pass instance to validated True if ok, else create cron that delete instance.validated = False older than x days

        return data, st
