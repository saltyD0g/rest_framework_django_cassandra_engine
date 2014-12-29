from __future__ import unicode_literals
import warnings

from cqlengine import models, columns
from rest_framework import fields, serializers

from django.db.models.fields import FieldDoesNotExist

from copy import deepcopy

from rest_framework.utils import model_meta
from rest_framework.utils.field_mapping import (
    get_url_kwargs, get_field_kwargs,
    get_relation_kwargs, get_nested_relation_kwargs,
    ClassLookupDict
)

from collections import OrderedDict

class ClassNameField(serializers.Field): #include this for error checking when we have to punt on serializing a field
    def get_attribute(self, obj):
        return obj

    def to_representation(self, obj):
        return obj.__class__.__name__



class CassandraEngineModelSerializer(serializers.ModelSerializer):
    _field_mapping = ClassLookupDict({
            columns.Float: fields.FloatField,
            columns.Decimal: fields.DecimalField,
            columns.Integer: fields.IntegerField,
            columns.BigInt: fields.IntegerField,
            columns.VarInt: fields.IntegerField,
            columns.DateTime: fields.DateTimeField,
            columns.Boolean: fields.BooleanField,
            columns.Bytes: fields.CharField,
            columns.Ascii: fields.CharField,
            columns.Text: fields.CharField,
            columns.UUID: fields.CharField,
            columns.TimeUUID: fields.CharField,
            columns.Counter: fields.IntegerField,
    })
    #_related_class = PrimaryKeyRelatedField

    def get_fields(self):
        declared_fields = deepcopy(self._declared_fields)

        ret = OrderedDict()
        model = getattr(self.Meta, 'model')
        fields = getattr(self.Meta, 'fields', None)
        exclude = getattr(self.Meta, 'exclude', None)
        depth = getattr(self.Meta, 'depth', 0)
        extra_kwargs = getattr(self.Meta, 'extra_kwargs', {})

        if fields and not isinstance(fields, (list, tuple)):
            raise TypeError(
                'The `fields` option must be a list or tuple. Got %s.' %
                type(fields).__name__
            )

        if exclude and not isinstance(exclude, (list, tuple)):
            raise TypeError(
                'The `exclude` option must be a list or tuple. Got %s.' %
                type(exclude).__name__
            )

        assert not (fields and exclude), "Cannot set both 'fields' and 'exclude'."

        extra_kwargs = self._include_additional_options(extra_kwargs)

        # Retrieve metadata about fields & relationships on the model class.
        #info = model_meta.get_field_info(model)
        
        print(dir(model))
         
        # Use the default set of field names if none is supplied explicitly.
        if fields is None:
            fields = self._get_default_field_names(declared_fields, info)
            exclude = getattr(self.Meta, 'exclude', None)
            if exclude is not None:
                for field_name in exclude:
                    fields.remove(field_name)

        # Determine the set of model fields, and the fields that they map to.
        # We actually only need this to deal with the slightly awkward case
        # of supporting `unique_for_date`/`unique_for_month`/`unique_for_year`.
        model_field_mapping = {}
        for field_name in fields:
            if field_name in declared_fields:
                field = declared_fields[field_name]
                source = field.source or field_name
            else:
                try:
                    source = extra_kwargs[field_name]['source']
                except KeyError:
                    source = field_name
            # Model fields will always have a simple source mapping,
            # they can't be nested attribute lookups.
            if '.' not in source and source != '*':
                model_field_mapping[source] = field_name

        # Determine if we need any additional `HiddenField` or extra keyword
        # arguments to deal with `unique_for` dates that are required to
        # be in the input data in order to validate it.
        hidden_fields = {}
        unique_constraint_names = set()

        """
        for model_field_name, field_name in model_field_mapping.items():
            try:
                model_field = model._get_column(model_field_name)#model._meta.get_field(model_field_name)
            except FieldDoesNotExist:
                continue

            # Include each of the `unique_for_*` field names.
            unique_constraint_names |= set([
                model_field.unique_for_date,
                model_field.unique_for_month,
                model_field.unique_for_year
            ])

        unique_constraint_names -= set([None])
        
        # Include each of the `unique_together` field names,
        # so long as all the field names are included on the serializer.
        for parent_class in [model] + list(model._meta.parents.keys()):
            for unique_together_list in parent_class._meta.unique_together:
                if set(fields).issuperset(set(unique_together_list)):
                    unique_constraint_names |= set(unique_together_list)
        """
        # Now we have all the field names that have uniqueness constraints
        # applied, we can add the extra 'required=...' or 'default=...'
        # arguments that are appropriate to these fields, or add a `HiddenField` for it.
        for unique_constraint_name in unique_constraint_names:
            # Get the model field that is referred too.
            unique_constraint_field = model._meta.get_field(unique_constraint_name)

            if getattr(unique_constraint_field, 'auto_now_add', None):
                default = CreateOnlyDefault(timezone.now)
            elif getattr(unique_constraint_field, 'auto_now', None):
                default = timezone.now
            elif unique_constraint_field.has_default():
                default = unique_constraint_field.default
            else:
                default = empty

            if unique_constraint_name in model_field_mapping:
                # The corresponding field is present in the serializer
                if unique_constraint_name not in extra_kwargs:
                    extra_kwargs[unique_constraint_name] = {}
                if default is empty:
                    if 'required' not in extra_kwargs[unique_constraint_name]:
                        extra_kwargs[unique_constraint_name]['required'] = True
                else:
                    if 'default' not in extra_kwargs[unique_constraint_name]:
                        extra_kwargs[unique_constraint_name]['default'] = default
            elif default is not empty:
                # The corresponding field is not present in the,
                # serializer. We have a default to use for it, so
                # add in a hidden field that populates it.
                hidden_fields[unique_constraint_name] = HiddenField(default=default)

        # Now determine the fields that should be included on the serializer.
        for field_name in fields:
            if field_name in declared_fields:
                # Field is explicitly declared on the class, use that.
                ret[field_name] = declared_fields[field_name]
                continue

            elif field_name in info.fields_and_pk:
                # Create regular model fields.
                model_field = info.fields_and_pk[field_name]
                field_cls = self._field_mapping[model_field]
                kwargs = get_field_kwargs(field_name, model_field)
                if 'choices' in kwargs:
                    # Fields with choices get coerced into `ChoiceField`
                    # instead of using their regular typed field.
                    field_cls = ChoiceField
                if not issubclass(field_cls, ModelField):
                    # `model_field` is only valid for the fallback case of
                    # `ModelField`, which is used when no other typed field
                    # matched to the model field.
                    kwargs.pop('model_field', None)
                if not issubclass(field_cls, CharField) and not issubclass(field_cls, ChoiceField):
                    # `allow_blank` is only valid for textual fields.
                    kwargs.pop('allow_blank', None)

            elif field_name in info.relations:
                # Create forward and reverse relationships.
                relation_info = info.relations[field_name]
                if depth:
                    field_cls = self._get_nested_class(depth, relation_info)
                    kwargs = get_nested_relation_kwargs(relation_info)
                else:
                    field_cls = self._related_class
                    kwargs = get_relation_kwargs(field_name, relation_info)
                    # `view_name` is only valid for hyperlinked relationships.
                    if not issubclass(field_cls, HyperlinkedRelatedField):
                        kwargs.pop('view_name', None)

            elif hasattr(model, field_name):
                # Create a read only field for model methods and properties.
                field_cls = ReadOnlyField
                kwargs = {}

            elif field_name == api_settings.URL_FIELD_NAME:
                # Create the URL field.
                field_cls = HyperlinkedIdentityField
                kwargs = get_url_kwargs(model)

            else:
                raise ImproperlyConfigured(
                    'Field name `%s` is not valid for model `%s`.' %
                    (field_name, model.__class__.__name__)
                )

            # Check that any fields declared on the class are
            # also explicitly included in `Meta.fields`.
            missing_fields = set(declared_fields.keys()) - set(fields)
            if missing_fields:
                missing_field = list(missing_fields)[0]
                raise ImproperlyConfigured(
                    'Field `%s` has been declared on serializer `%s`, but '
                    'is missing from `Meta.fields`.' %
                    (missing_field, self.__class__.__name__)
                )

            # Populate any kwargs defined in `Meta.extra_kwargs`
            extras = extra_kwargs.get(field_name, {})
            if extras.get('read_only', False):
                for attr in [
                    'required', 'default', 'allow_blank', 'allow_null',
                    'min_length', 'max_length', 'min_value', 'max_value',
                    'validators', 'queryset'
                ]:
                    kwargs.pop(attr, None)

            if extras.get('default') and kwargs.get('required') is False:
                kwargs.pop('required')

            kwargs.update(extras)

            # Create the serializer field.
            ret[field_name] = field_cls(**kwargs)

        for field_name, field in hidden_fields.items():
            ret[field_name] = field

        return ret
        
    def get_validators(self):
            # If the validators have been declared explicitly then use that.
            validators = getattr(getattr(self, 'Meta', None), 'validators', None)
            if validators is not None:
                return validators

            # Determine the default set of validators.
            validators = []
            model_class = self.Meta.model
            field_names = set([
                field.source for field in self.fields.values()
                if (field.source != '*') and ('.' not in field.source)
            ])

            # Note that we make sure to check `unique_together` both on the
            # base model class, but also on any parent classes.
            """
            for parent_class in [model_class]:# + #list(model_class._meta.parents.keys()):
                for unique_together in parent_class._meta.unique_together:
                    if field_names.issuperset(set(unique_together)):
                        validator = UniqueTogetherValidator(
                            queryset=parent_class._default_manager,
                            fields=unique_together
                        )
                        validators.append(validator)

            # Add any unique_for_date/unique_for_month/unique_for_year constraints.
            info = model_meta.get_field_info(model_class)
            for field_name, field in info.fields_and_pk.items():
                if field.unique_for_date and field_name in field_names:
                    validator = UniqueForDateValidator(
                        queryset=model_class._default_manager,
                        field=field_name,
                        date_field=field.unique_for_date
                    )
                    validators.append(validator)

                if field.unique_for_month and field_name in field_names:
                    validator = UniqueForMonthValidator(
                        queryset=model_class._default_manager,
                        field=field_name,
                        date_field=field.unique_for_month
                    )
                    validators.append(validator)

                if field.unique_for_year and field_name in field_names:
                    validator = UniqueForYearValidator(
                        queryset=model_class._default_manager,
                        field=field_name,
                        date_field=field.unique_for_year
                    )
                    validators.append(validator)
            """
            return validators

"""
#from django.core.exceptions import ValidationError
#from rest_framework import serializers
#from rest_framework import fields
#from django.core.paginator import Page
#from django.db import models
#from django.forms import widgets
#from django.utils.datastructures import SortedDict
#from rest_framework.compat import get_concrete_model
#from .fields import ReferenceField, ListField#, DynamicField


def get_concrete_model(model_cls):
    try:
        return model_cls._meta.concrete_model
    except AttributeError:
        return model_cls
        
#class CassandraEngineModelSerializerOptions(serializers.ModelSerializerOptions):
   # Meta class options for CassandraEngineModelSerializer
   
    #def __init__(self, meta):
    #    super(CassandraEngineModelSerializerOptions, self).__init__(meta)
    #    self.depth = getattr(meta, 'depth', 5)
    


class OldCassandraEngineModelSerializer(serializers.ModelSerializer):
    pass
    

    Model Serializer that supports CassandraEngine
    
    #_options_class = CassandraEngineModelSerializerOptions
    
    #def get_fields(self):
    #    return copy.deepcopy( 
    
    
    
    def run_validation(self, attrs):
       
        #Rest Framework built-in validation + related model validations
        
        for field_name, field in self.fields.items():
            if field_name in self._errors:
                continue

            source = field.source or field_name
            if self.partial and source not in attrs:
                continue

            if field_name in attrs and hasattr(field, 'model_field'):
                try:
                    field.model_field.validate(attrs[field_name])
                except ValidationError as err:
                    self._errors[field_name] = str(err)

            try:
                validate_method = getattr(self, 'validate_%s' % field_name, None)
                if validate_method:
                    attrs = validate_method(attrs, source)
            except serializers.ValidationError as err:
                self._errors[field_name] = self._errors.get(field_name, []) + list(err.messages)

        if not self._errors:
            try:
                attrs = self.validate(attrs)
            except serializers.ValidationError as err:
                if hasattr(err, 'message_dict'):
                    for field_name, error_messages in err.message_dict.items():
                        self._errors[field_name] = self._errors.get(field_name, []) + list(error_messages)
                elif hasattr(err, 'messages'):
                    self._errors['non_field_errors'] = err.messages

        return attrs
        
    def create(self, validated_data):
        pass
        #return self.from_native(validated_data)
     
    def update(self, instance, validated_data):
        pass 
            
    
    def deprecated_restore_object(self, attrs, instance=None):
        if instance is None:
            instance = self.opts.model()

        dynamic_fields = self.get_dynamic_fields(instance)
        all_fields = dict(dynamic_fields, **self.fields)

        for key, val in attrs.items():
            field = all_fields.get(key)
            if not field or field.read_only:
                continue

            if isinstance(field, serializers.Serializer):                
                many = field.many

                def _restore(field, item):
                    # looks like a bug, sometimes there are decerialized objects in attrs
                    # sometimes they are just dicts 
                    #if isinstance(item, BaseDocument):
                    #    return item 
                    return field.from_native(item)

                if many:                    
                    val = [_restore(field, item) for item in val] 
                else:
                    val = _restore(field, val) 

            key = getattr(field, 'source', None) or key
            try:
                setattr(instance, key, val)
            except ValueError:
                self._errors[key] = self.error_messages['required']

        return instance

    def get_default_fields(self):
        cls = self.opts.model
        opts = get_concrete_model(cls)
        fields = []
        fields += [getattr(opts, field) for field in cls._fields_ordered]

        ret = SortedDict()

        for model_field in fields:
            field = self.get_field(model_field)

            if field:
                field.initialize(parent=self, field_name=model_field.name)
                ret[model_field.name] = field

        for field_name in self.opts.read_only_fields:
            assert field_name in ret,\
            "read_only_fields on '%s' included invalid item '%s'" %\
            (self.__class__.__name__, field_name)
            ret[field_name].read_only = True

        return ret

    def get_dynamic_fields(self, obj):
        dynamic_fields = {}
        if obj is not None and obj._dynamic:
            for key, value in obj._dynamic_fields.items():
                dynamic_fields[key] = self.get_field(value)
        return dynamic_fields

    def get_field(self, model_field):
        kwargs = {}

        if model_field.__class__ in (columns.Set, columns.List, columns.Map):
            kwargs['model_field'] = model_field
            kwargs['depth'] = self.opts.depth

        #if not model_field.__class__ == mongoengine.ObjectIdField:
        kwargs['required'] = model_field.required

        

        if model_field.default:
            kwargs['required'] = False
            kwargs['default'] = model_field.default

        if model_field.__class__ == models.TextField:
            kwargs['widget'] = widgets.Textarea

        field_mapping = {
            columns.Float: fields.FloatField,
            columns.Decimal: fields.DecimalField,
            columns.Integer: fields.IntegerField,
            columns.BigInt: fields.IntegerField,
            columns.VarInt: fields.IntegerField,
            columns.DateTime: fields.DateTimeField,
            columns.Boolean: fields.BooleanField,
            columns.Bytes: fields.CharField,
            columns.Ascii: fields.CharField,
            columns.Text: fields.CharField,
            columns.UUID: fields.CharField,
            columns.TimeUUID: fields.CharField,
            columns.Counter: fields.IntegerField,
        }

        attribute_dict = {
            columns.Map: ['key_type', 'value_type'],
            columns.List: ['value_type'],
            columns.Set: ['strict', 'value_type'],
            columns.Text: ['min_length', 'max_length'],
            columns.Float: ['double_precision'],
            
        }

        if model_field.__class__ in attribute_dict:
            attributes = attribute_dict[model_field.__class__]
            for attribute in attributes:
                kwargs.update({attribute: getattr(model_field, attribute)})

        try:
            return field_mapping[model_field.__class__](**kwargs)
        except KeyError:
            # Defaults to WritableField if not in field mapping
            return ClassNameField(**kwargs)

    def to_native(self, obj):
        
        #Rest framework built-in to_native + transform_object
       
        ret = self._dict_class()
        ret.fields = self._dict_class()

        #Dynamic Document Support
        dynamic_fields = self.get_dynamic_fields(obj)
        all_fields = self._dict_class()
        all_fields.update(self.fields)
        all_fields.update(dynamic_fields)

        for field_name, field in all_fields.items():
            if field.read_only and obj is None:
                continue
            field.initialize(parent=self, field_name=field_name)
            key = self.get_field_key(field_name)
            value = field.field_to_native(obj, field_name)
            #Override value with transform_ methods
            method = getattr(self, 'transform_%s' % field_name, None)
            if callable(method):
                value = method(obj, value)
            if not getattr(field, 'write_only', False):
                ret[key] = value
            ret.fields[key] = self.augment_field(field, field_name, key, value)

        return ret

    def from_native(self, data, files=None):
        self._errors = {}

        if data is not None or files is not None:
            attrs = self.restore_fields(data, files)
            for key in data.keys():
                if key not in attrs:
                    attrs[key] = data[key]
            if attrs is not None:
                attrs = self.perform_validation(attrs)
        else:
            self._errors['non_field_errors'] = ['No input provided']

        if not self._errors:
            return self.update( instance=getattr(self, 'object', None), validated_data=attrs)
            #return self.restore_object(attrs, instance=getattr(self, 'object', None))

    @property
    def data(self):
       
        #Returns the serialized data on the serializer.
        
        if self._data is None:
            obj = self.object

            if self.many is not None:
                many = self.many
            else:
                many = hasattr(obj, '__iter__') and not isinstance(obj, (Page, dict))#(BaseDocument, Page, dict))
                if many:
                    warnings.warn('Implicit list/queryset serialization is deprecated. '
                                  'Use the `many=True` flag when instantiating the serializer.',
                                  DeprecationWarning, stacklevel=2)

            if many:
                self._data = [self.to_native(item) for item in obj]
            else:
                self._data = self.to_native(obj)

        return self._data
  """