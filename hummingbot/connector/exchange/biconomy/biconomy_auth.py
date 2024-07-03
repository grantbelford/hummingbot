import hashlib
import hmac
import json
from collections import OrderedDict
from typing import Any, Dict
from urllib.parse import urlencode

from urllib3 import encode_multipart_formdata

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest

# from urllib3 import encode_multipart_formdata


class BiconomyAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    def get_hmac_sha256(self, source: str) -> str:
        """
        :param source: the source string
        :return: HMAC-SHA256 string
        """
        hmac_sha256 = hmac.new(self.secret_key.encode(encoding='utf-8'), source.encode(encoding='utf-8'), hashlib.sha256)
        return hmac_sha256.hexdigest()

    def get_md5_32(self, source: str) -> str:
        """
        :param source: the source string
        :return: md5 string
        """
        md5 = hashlib.md5()
        md5.update(source.encode(encoding='utf-8'))
        return md5.hexdigest()

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        headers = {}
        if request.method == RESTMethod.POST and request.data is not None:
            body, content_type = self.add_auth_params(
                params=json.loads(request.data))
            request.data = body
            request.headers["Content-Type"] = content_type
        else:
            request.params = self.add_auth_to_params(params=request.params)

        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self.header_for_authentication())
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. Biconomy does not use this
        functionality
        """
        return request  # pass-through

    def add_auth_to_params(self,
                           params: Dict[str, Any]):

        request_params = OrderedDict(params or {})
        request_params["api_key"] = self.api_key
        request_params["secret_key"] = self.secret_key

        params_string = self.build_parameters(request_params)

        params_sign = {
            "api_key": self.api_key,
            "sign": str.upper(self.get_hmac_sha256(params_string))
        }

        return params_sign

    def add_auth_params(self, params: Dict[str, Any]):
        request_params = OrderedDict(params or {})
        request_params["api_key"] = self.api_key

        sign_string = self.build_parameters(request_params) + "&secret_key=" + self.secret_key
        params_sign = str.upper(self.get_hmac_sha256(sign_string))
        request_params["sign"] = params_sign

        # Convert all values to strings
        param = {k: str(v) for k, v in request_params.items()}

        # Encode request parameters for multipart form data
        body, content_type = encode_multipart_formdata(param)
        return body, content_type

    def build_parameters(self, params: dict):
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{key}={params[key]}" for key in keys])

    def header_for_authentication(self) -> Dict[str, str]:
        headers = {
            "X-SITE-ID": "127",
        }
        return headers

    def _generate_signature(self, params: Dict[str, Any]) -> str:

        encoded_params_str = urlencode(params)
        digest = hmac.new(self.secret_key.encode(
            "utf8"), encoded_params_str.encode("utf8"), hashlib.sha256).hexdigest()
        return digest