from setuptools import setup, find_packages

setup(
    name="rest-framework-django-cassandra-engine", 
    version = "0.1", 
    packages = ['rest_framework_cassandra_engine'], #find_packages(),
    requires = ['djangorestframework', 'cqlengine'],
)
