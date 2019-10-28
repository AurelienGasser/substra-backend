from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.state import api_settings


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        super().validate(attrs)
        refresh = self.get_token(self.user)

        return refresh


class CustomTokenRefreshSerializer(serializers.Serializer):

    def validate(self, attrs):

        if 'refresh' not in self.context['request'].COOKIES:
            raise ValidationError('refresh cookie is not present')

        refresh_cookie = self.context['request'].COOKIES['refresh']

        refresh = RefreshToken(refresh_cookie)

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    # Attempt to blacklist the given refresh token
                    refresh.blacklist()
                except AttributeError:
                    # If blacklist app not installed, `blacklist` method will
                    # not be present
                    pass

            refresh.set_jti()
            refresh.set_exp()

        return refresh
