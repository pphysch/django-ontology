from django.apps import AppConfig


class OntologyAuthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ontology_auth'

    def ready(self) -> None:
        from . import signals
        return super().ready()