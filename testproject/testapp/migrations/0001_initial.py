# Generated by Django 4.0.5 on 2022-06-17 22:01

from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('ontology', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Thing',
            fields=[
                ('entity', models.OneToOneField(editable=False, on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='ontology.entity')),
                ('deleted', models.BooleanField(db_index=True, default=False, editable=False, help_text="True indicates the component has been soft-deleted and won't appear in most queries.")),
                ('slug', models.SlugField(unique=True)),
            ],
            options={
                'permissions': [('can_use_thing', 'Can use thing')],
            },
        ),
        migrations.CreateModel(
            name='Place',
            fields=[
                ('entity', models.OneToOneField(editable=False, on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='ontology.entity')),
                ('deleted', models.BooleanField(db_index=True, default=False, editable=False, help_text="True indicates the component has been soft-deleted and won't appear in most queries.")),
                ('slug', models.SlugField(unique=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='testapp.place')),
            ],
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('entity', models.OneToOneField(editable=False, on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='ontology.entity')),
                ('deleted', models.BooleanField(db_index=True, default=False, editable=False, help_text="True indicates the component has been soft-deleted and won't appear in most queries.")),
                ('slug', models.SlugField(unique=True)),
                ('friends', models.ManyToManyField(blank=True, to='testapp.person')),
                ('items', models.ManyToManyField(blank=True, to='testapp.thing')),
                ('location', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='testapp.place')),
            ],
            options={
                'verbose_name_plural': 'people',
            },
        ),
        migrations.AddConstraint(
            model_name='place',
            constraint=models.CheckConstraint(check=models.Q(('entity', django.db.models.expressions.F('parent')), _negated=True), name='no_self_parent'),
        ),
    ]
