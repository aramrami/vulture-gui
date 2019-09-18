# Generated by Django 2.1.3 on 2019-04-01 08:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('darwin', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='filterpolicy',
            name='cache_size',
            field=models.PositiveIntegerField(default=1000, help_text='The cache size to use for caching darwin requests.', verbose_name='Cache size'),
        ),
    ]