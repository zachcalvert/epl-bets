from django.contrib.auth import get_user_model
from rest_framework import serializers

from website.models import SiteSettings

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name", "first_name", "last_name")
        read_only_fields = ("id",)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "email", "password", "display_name", "first_name", "last_name")
        read_only_fields = ("id",)

    def validate(self, attrs):
        site = SiteSettings.load()
        if site.max_users and User.objects.count() >= site.max_users:
            raise serializers.ValidationError(
                "Registration is currently closed — we've hit our user cap."
            )
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
