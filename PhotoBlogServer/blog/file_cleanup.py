"""Release replaced/deleted media only after the database transaction commits."""
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Post


def delete_after_commit(storage, name):
    if name:
        transaction.on_commit(lambda: storage.delete(name), robust=True)


@receiver(pre_save, sender=Post)
def remember_replaced_photo(sender, instance, **kwargs):
    instance._replaced_photo = None
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).only("image").first()
        if old and old.image.name != instance.image.name:
            instance._replaced_photo = (old.image.storage, old.image.name)


@receiver(post_save, sender=Post)
def release_replaced_photo(sender, instance, **kwargs):
    old = getattr(instance, "_replaced_photo", None)
    if old:
        delete_after_commit(*old)


@receiver(post_delete, sender=Post)
def release_deleted_photo(sender, instance, **kwargs):
    delete_after_commit(instance.image.storage, instance.image.name)

