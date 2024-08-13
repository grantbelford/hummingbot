import asyncio
import unittest
from collections import OrderedDict
from unittest.mock import patch

from typing_extensions import Awaitable

from hummingbot.connector.exchange.bigone.bigone_auth import BigoneAuth
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.connections.data_types import RESTRequest


class TestBigoneAuth(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_api_key"
        self.secret_key = "test_secret_key"
        self.time_synchronizer = TimeSynchronizer()
        self.auth = BigoneAuth(self.api_key, self.secret_key, self.time_synchronizer)

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    @patch('time.time', return_value=1234567890)
    @patch('jwt.encode')
    def test_get_auth_headers_ws(self, mock_jwt_encode, mock_time):
        # Prepare expected values
        nonce = int(mock_time.return_value * 1e9)
        expected_payload = {
            "type": "OpenAPIV2",
            "sub": self.api_key,
            "nonce": nonce
        }
        expected_token = "mocked_jwt_token"
        mock_jwt_encode.return_value = expected_token

        # Expected header
        expected_headers = {"token": f"Bearer {expected_token}"}

        # Call the method
        headers = self.auth._get_auth_headers_ws()

        # Assertions
        mock_jwt_encode.assert_called_once_with(expected_payload, self.secret_key, algorithm="HS256")
        self.assertEqual(headers, expected_headers)

    @patch('time.time', return_value=1234567890)
    @patch('jwt.encode')
    def test_get_auth_headers(self, mock_jwt_encode, mock_time):
        # Prepare expected values
        nonce = int(mock_time.return_value * 1e9)
        expected_payload = {
            "type": "OpenAPIV2",
            "sub": self.api_key,
            "nonce": str(nonce)
        }
        expected_token = "mocked_jwt_token"
        mock_jwt_encode.return_value = expected_token

        # Expected header
        expected_headers = {"Authorization": f"Bearer {expected_token}"}

        # Call the method
        headers = self.auth._get_auth_headers()

        # Assertions
        mock_jwt_encode.assert_called_once_with(expected_payload, self.secret_key, algorithm="HS256")
        self.assertEqual(headers, expected_headers)

    def test_add_auth_to_params(self):
        # Test empty params
        params = {}
        result = self.auth.add_auth_to_params(params)
        expected = OrderedDict()
        self.assertEqual(result, expected)

        # Test with existing params
        params = {"param1": "value1", "param2": "value2"}
        result = self.auth.add_auth_to_params(params)
        expected = OrderedDict([("param1", "value1"), ("param2", "value2")])
        self.assertEqual(result, expected)

    @patch('hummingbot.connector.exchange.bigone.bigone_auth.BigoneAuth._get_auth_headers')  # Replace 'your_module' with the actual module name
    def test_rest_authenticate(self, mock_get_auth_headers):
        # Setup
        mock_get_auth_headers.return_value = {"Authorization": "Bearer test_token"}
        request = RESTRequest("GET", "/some_endpoint", headers={"Some-Header": "some_value"})

        # Call the method
        result_request = self.async_run_with_timeout(self.auth.rest_authenticate(request))

        # Expected headers
        expected_headers = {
            "Some-Header": "some_value",
            "Authorization": "Bearer test_token"
        }

        # Assertions
        self.assertEqual(result_request.headers, expected_headers)
