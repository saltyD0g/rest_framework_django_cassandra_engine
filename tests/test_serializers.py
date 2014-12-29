from datetime import datetime 
from cqlengine.models import Model as cem
from cqlengine import columns as cec

from unittest import TestCase
from rest_framework_django_cassandra_engine.serializers import CassandraEngineModelSerializer
from rest_framework import serializers as s


class Job(cem):
    id = cec.TimeUUID(primary_key=True)
    title = cec.Text()
    status = cec.Text()
    notes = cec.Text(required=False)
    on = cec.DateTime(default=datetime.utcnow)
    weight = cec.Integer(default=0)
    
    class Meta:
        ordering = ('on',)


class JobSerializer(CassandraEngineModelSerializer):
    id = s.Field()
    title = s.CharField()
    status = s.ChoiceField(read_only=True, choices=('draft', 'published'))
    sort_weight = s.IntegerField(source='weight')


    class Meta:
        model = Job 
        fields = ('id', 'title','status', 'sort_weight')



class TestReadonlyRestore(TestCase):

    def test_restore_object(self):
        job = Job(title='original title', status='draft', notes='secure')
        data = {
            'title': 'updated title ...',
            'status': 'published',  # this one is read only
            'notes': 'hacked', # this field should not update
            'sort_weight': 10 # mapped to a field with differet name
        }

        serializer = JobSerializer(job, data=data, partial=True)
        
        self.assertTrue(serializer.is_valid())
        print (dir(serializer), serializer.data, serializer.get_fields())
        obj = serializer#.object 
        self.assertEqual(data['title'], obj.title)
        self.assertEqual('draft', obj.status)
        self.assertEqual('secure', obj.notes)

        self.assertEqual(10, obj.weight)





