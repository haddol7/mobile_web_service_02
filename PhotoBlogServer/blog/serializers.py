from rest_framework import serializers
from .models import Post


class OptionalPhotoContentField(serializers.JSONField):
    def get_value(self, dictionary):
        from rest_framework.utils import html
        # The browsable API renders optional JSON as an empty/null text box.
        # Treat that HTML form value as an omitted optional analysis packet.
        if html.is_html_input(dictionary) and dictionary.get(self.field_name, "").strip() in ("", "null"):
            return serializers.empty
        return super().get_value(dictionary)


class PostSerializer(serializers.ModelSerializer):
    photo_content = OptionalPhotoContentField(write_only=True, required=False)

    def validate_photo_content(self, value):
        from .content_rules import validate_packet
        validate_packet(value)
        return value

    class Meta:
        model = Post
        fields = ("id", "author", "title", "text", "created_date", "published_date", "image", "photo_content")
        read_only_fields = ("id", "author", "created_date", "published_date")

