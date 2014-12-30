from rest_framework import mixins
from rest_framework.viewsets import ViewSetMixin
from rest_framework_django_cassandra.generics import CassandraAPIView


class CassandraGenericViewSet(ViewSetMixin, CassandraAPIView):
    #include base generic view behavior
    pass


class CassandraViewSet(mixins.CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin,
                   mixins.DestroyModelMixin,
                   mixins.ListModelMixin,
                   CassandraGenericViewSet):
    #viewset that implements default 'CRUD' actions
    pass


class ReadOnlyModelViewSet(mixins.RetrieveModelMixin,
                           mixins.ListModelMixin,
                           CassandraGenericViewSet):
   
   #viewset to implement list() and retrieve() actions.
  
    pass