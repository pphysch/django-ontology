# Generated by Django 4.0.5 on 2022-06-17 22:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attribute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.SlugField()),
                ('value', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Entity',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('updated_time', models.DateTimeField(auto_now=True)),
                ('deleted_time', models.DateTimeField(blank=True, db_index=True, editable=False, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('attrs', models.ManyToManyField(blank=True, related_name='entities', to='ontology.attribute', verbose_name='attributes')),
                ('content_types', models.ManyToManyField(editable=False, to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name_plural': 'entities',
            },
        ),
        migrations.CreateModel(
            name='Domain',
            fields=[
                ('entity', models.OneToOneField(editable=False, on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='ontology.entity')),
                ('deleted', models.BooleanField(db_index=True, default=False, editable=False, help_text="True indicates the component has been soft-deleted and won't appear in most queries.")),
                ('slug', models.SlugField(unique=True)),
                ('entities', models.ManyToManyField(blank=True, related_name='domains', to='ontology.entity')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='attribute',
            name='domain',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='ontology.domain'),
        ),
        migrations.AddIndex(
            model_name='attribute',
            index=models.Index(fields=['domain', 'key', 'value'], name='ontology_at_domain__e999c2_idx'),
        ),
        migrations.AddConstraint(
            model_name='attribute',
            constraint=models.UniqueConstraint(fields=('key', 'value', 'domain'), name='ontology_attribute_unique'),
        ),
    ]
