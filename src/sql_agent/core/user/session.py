"""Optional gateway-issued signed session; local mode remains explicit."""
import base64
import hashlib
import hmac
import json
import os
import time
from sql_agent.core.user.models import User
from sql_agent.core.user.resolver import FixedUserResolver, UserResolver


class SignedSessionResolver(UserResolver):
    def __init__(self, secret):
        if len(secret) < 32:
            raise ValueError('SQL_AGENT_AUTH_SECRET 至少需要 32 个字符')
        self.secret = secret.encode()

    async def resolve_user(self, request_context):
        try:
            payload, signature = request_context.get_cookie('sql_agent_session', '').split('.')
            expected = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError('signature')
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
            if float(claims['exp']) <= time.time() or not isinstance(claims['sub'], str) or not claims['sub']:
                raise ValueError('expired')
            groups = claims.get('groups', ['user'])
            if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
                raise ValueError('groups')
            return User(id=claims['sub'], username=claims.get('name'), group_memberships=groups)
        except (ValueError, KeyError, TypeError) as error:
            raise PermissionError('请通过已连接的身份网关登录后访问') from error


def build_user_resolver():
    secret = os.getenv('SQL_AGENT_AUTH_SECRET', '')
    return SignedSessionResolver(secret) if secret else FixedUserResolver(group_memberships=['user', 'admin'])
