from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('blog', '0003_photocontent_phototag_phototextline')]
    operations = [
        migrations.DeleteModel(name='DecorLayout'),
        migrations.DeleteModel(name='Gallery'),
    ]
