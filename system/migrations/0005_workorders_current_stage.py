# Generated by Django 5.2 on 2025-06-18 16:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0004_workorderitems_serialized_part_number_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='workorders',
            name='current_stage',
            field=models.CharField(choices=[('ensamble', 'Ensamble'), ('pintura', 'Pintura'), ('empaque', 'Empaque')], default='ensamble', max_length=10),
        ),
    ]
