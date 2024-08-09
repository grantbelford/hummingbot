import json
import time
from collections import OrderedDict
from typing import Any, Dict

import jwt

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class BigoneAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        if request.method == RESTMethod.POST:
            request.data = self.add_auth_to_params(params=json.loads(request.data))
        else:
            request.params = self.add_auth_to_params(params=request.params)
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self._get_auth_headers())
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        request.payload["authenticateCustomerRequest"] = self._get_auth_headers_ws(payload=request.payload)
        return request

    def add_auth_to_params(self,
                           params: Dict[str, Any]):
        request_params = OrderedDict(params or {})

        return request_params

    def _get_auth_headers_ws(self) -> Dict[str, str]:
        nonce = int(time.time() * 1e9)
        # JWT payload
        payload = {
            "type": "OpenAPIV2",
            "sub": self.api_key,
            "nonce": nonce,
        }
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return {"token": f"Bearer {token}"}

    def _get_auth_headers(self) -> Dict[str, str]:
        nonce = int(time.time() * 1e9)
        # JWT payload
        payload = {
            "type": "OpenAPIV2",
            "sub": f"{self.api_key}",
            "nonce": str(nonce)
        }
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        header = {
            "Authorization": f'Bearer {token}'
        }
        return header
