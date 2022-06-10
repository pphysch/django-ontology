# Generated by Django 4.0.5 on 2022-06-10 22:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ontology', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='domain_entities',
            name='domain',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='ontology.domain'),
        ),
        migrations.AlterField(
            model_name='domain_entities',
            name='entity',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='ontology.entity'),
        ),
    ]
