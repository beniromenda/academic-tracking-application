from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_alter_assessmenttask_options_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='assessmentresult',
                    name='assessment_date',
                    field=models.DateField(default=django.utils.timezone.localdate),
                ),
            ],
            database_operations=[],
        ),
    ]
