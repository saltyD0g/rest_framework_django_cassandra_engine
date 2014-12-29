from django.core.exceptions import ImproperlyConfigured
from rest_framework import mixins
from rest_framework.generics import GenericAPIView
from django.shortcuts import get_object_or_404

class CassandraAPIView(GenericAPIView):
    queryset = None
    serializer_class = None
    lookup_field = 'id'

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset.clone()

        if self.model is not None:
            return self.get_serializer().opts.model.objects.all()

        raise ImproperlyConfigured("'%s' must define 'queryset' or 'model'"
                                    % self.__class__.__name__)
    
    def get_object(self, queryset=None):
        query_key = self.lookup_url_kwarg or self.lookup_field
        query_kwargs = {query_key: self.kwargs[query_key]}
        queryset = self.get_queryset()

        obj = get_object_or_404(queryset, **query_kwargs)
        
        self.check_object_permissions(self.request, obj)

        return obj


class CreateAPIView(mixins.CreateModelMixin,
                    CassandraAPIView):

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class ListAPIView(mixins.ListModelMixin,
                  CassandraAPIView):
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class ListCreateAPIView(mixins.ListModelMixin,
                        mixins.CreateModelMixin,
                        CassandraAPIView):
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class RetrieveAPIView(mixins.RetrieveModelMixin,
                      CassandraAPIView):
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class UpdateAPIView(mixins.UpdateModelMixin,
                    CassandraAPIView):

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class RetrieveUpdateAPIView(mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin,
                            CassandraAPIView):
    
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class RetrieveDestroyAPIView(mixins.RetrieveModelMixin,
                             mixins.DestroyModelMixin,
                             CassandraAPIView):
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class RetrieveUpdateDestroyAPIView(mixins.RetrieveModelMixin,
                                   mixins.UpdateModelMixin,
                                   mixins.DestroyModelMixin,
                                   CassandraAPIView):
    
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)