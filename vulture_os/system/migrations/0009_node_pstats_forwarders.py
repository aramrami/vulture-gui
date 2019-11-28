# Generated by Django 2.1.3 on 2019-11-23 00:47

from django.db import migrations
import djongo.models.fields
from system.cluster.models import Cluster


def forwards_func(apps, schema_editor):
    logomhiredis_model = apps.get_model("applications", "LogOMHIREDIS")
    db_alias = schema_editor.connection.alias
    node = Cluster.get_current_node()
    logomhiredis_objects = logomhiredis_model.objects.using(db_alias)

    try:
        redis_internal_dashboard = logomhiredis_objects.get(name="Internal_Dashboard", internal=True)
        node.pstats_forwarders.add(redis_internal_dashboard)
        node.save()
    except:
        print("Internal_Dashboard forwarder not found.")


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0008_auto_20191119_0339'),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='pstats_forwarders',
            field=djongo.models.fields.ArrayReferenceField(help_text='Log forwarders used to send impstats logs', null=True, on_delete=djongo.models.fields.ArrayReferenceField._on_delete, to='applications.LogOM', verbose_name='Send rsyslog pstats logs to'),
        ),
        migrations.RunPython(forwards_func, migrations.RunPython.noop)
    ]