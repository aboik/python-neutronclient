# Copyright 2012 NEC Corporation
# All Rights Reserved
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import json
import uuid

import fixtures
from mox3 import mox
from oslo.serialization import jsonutils
import requests
import requests_mock
import six
import testtools

from keystoneclient.auth.identity import v2 as ks_v2_auth
from keystoneclient.auth.identity import v3 as ks_v3_auth
from keystoneclient import exceptions as ks_exceptions
from keystoneclient import fixture
from keystoneclient import session

from neutronclient import client
from neutronclient.common import exceptions
from neutronclient.common import utils


USERNAME = 'testuser'
USER_ID = 'testuser_id'
TENANT_NAME = 'testtenant'
TENANT_ID = 'testtenant_id'
PASSWORD = 'password'
ENDPOINT_URL = 'localurl'
PUBLIC_ENDPOINT_URL = 'public_%s' % ENDPOINT_URL
ADMIN_ENDPOINT_URL = 'admin_%s' % ENDPOINT_URL
INTERNAL_ENDPOINT_URL = 'internal_%s' % ENDPOINT_URL
ENDPOINT_OVERRIDE = 'otherurl'
TOKENID = uuid.uuid4().hex
REGION = 'RegionOne'
NOAUTH = 'noauth'

KS_TOKEN_RESULT = fixture.V2Token()
KS_TOKEN_RESULT.set_scope()
_s = KS_TOKEN_RESULT.add_service('network', 'Neutron Service')
_s.add_endpoint(ENDPOINT_URL, region=REGION)

ENDPOINTS_RESULT = {
    'endpoints': [{
        'type': 'network',
        'name': 'Neutron Service',
        'region': REGION,
        'adminURL': ENDPOINT_URL,
        'internalURL': ENDPOINT_URL,
        'publicURL': ENDPOINT_URL
    }]
}

BASE_URL = "http://keystone.example.com:5000/"

V2_URL = "%sv2.0" % BASE_URL
V3_URL = "%sv3" % BASE_URL

_v2 = fixture.V2Discovery(V2_URL)
_v3 = fixture.V3Discovery(V3_URL)

V3_VERSION_LIST = jsonutils.dumps({'versions': {'values': [_v2, _v3]}})

V2_VERSION_ENTRY = {'version': _v2}
V3_VERSION_ENTRY = {'version': _v3}


def get_response(status_code, headers=None):
    response = mox.Mox().CreateMock(requests.Response)
    response.headers = headers or {}
    response.status_code = status_code
    return response


def setup_keystone_v2(mrequests):
    v2_token = fixture.V2Token(token_id=TOKENID)
    service = v2_token.add_service('network')
    service.add_endpoint(PUBLIC_ENDPOINT_URL, region=REGION)

    mrequests.register_uri('POST',
                           '%s/tokens' % (V2_URL),
                           json=v2_token)

    auth_session = session.Session()
    auth_plugin = ks_v2_auth.Password(V2_URL, 'xx', 'xx')
    return auth_session, auth_plugin


def setup_keystone_v3(mrequests):
    mrequests.register_uri('GET',
                           V3_URL,
                           json=V3_VERSION_ENTRY)

    v3_token = fixture.V3Token()
    service = v3_token.add_service('network')
    service.add_standard_endpoints(public=PUBLIC_ENDPOINT_URL,
                                   admin=ADMIN_ENDPOINT_URL,
                                   internal=INTERNAL_ENDPOINT_URL,
                                   region=REGION)

    mrequests.register_uri('POST',
                           '%s/auth/tokens' % (V3_URL),
                           text=json.dumps(v3_token),
                           headers={'X-Subject-Token': TOKENID})

    auth_session = session.Session()
    auth_plugin = ks_v3_auth.Password(V3_URL,
                                      username='xx',
                                      user_id='xx',
                                      user_domain_name='xx',
                                      user_domain_id='xx')
    return auth_session, auth_plugin


AUTH_URL = V2_URL


class CLITestAuthNoAuth(testtools.TestCase):

    def setUp(self):
        """Prepare the test environment."""
        super(CLITestAuthNoAuth, self).setUp()
        self.mox = mox.Mox()
        self.client = client.HTTPClient(username=USERNAME,
                                        tenant_name=TENANT_NAME,
                                        password=PASSWORD,
                                        endpoint_url=ENDPOINT_URL,
                                        auth_strategy=NOAUTH,
                                        region_name=REGION)
        self.addCleanup(self.mox.VerifyAll)
        self.addCleanup(self.mox.UnsetStubs)

    def test_get_noauth(self):
        self.mox.StubOutWithMock(self.client, "request")

        res200 = get_response(200)

        self.client.request(
            mox.StrContains(ENDPOINT_URL + '/resource'), 'GET',
            headers=mox.IsA(dict),
        ).AndReturn((res200, ''))
        self.mox.ReplayAll()

        self.client.do_request('/resource', 'GET')
        self.assertEqual(self.client.endpoint_url, ENDPOINT_URL)


class CLITestAuthKeystone(testtools.TestCase):

    def setUp(self):
        """Prepare the test environment."""
        super(CLITestAuthKeystone, self).setUp()
        self.mox = mox.Mox()

        for var in ('http_proxy', 'HTTP_PROXY'):
            self.useFixture(fixtures.EnvironmentVariableFixture(var))

        self.client = client.construct_http_client(
            username=USERNAME,
            tenant_name=TENANT_NAME,
            password=PASSWORD,
            auth_url=AUTH_URL,
            region_name=REGION)

        self.addCleanup(self.mox.VerifyAll)
        self.addCleanup(self.mox.UnsetStubs)

    def test_reused_token_get_auth_info(self):
        """Test that Client.get_auth_info() works even if client was
           instantiated with predefined token.
        """
        token_id = uuid.uuid4().hex
        client_ = client.HTTPClient(username=USERNAME,
                                    tenant_name=TENANT_NAME,
                                    token=token_id,
                                    password=PASSWORD,
                                    auth_url=AUTH_URL,
                                    region_name=REGION)
        expected = {'auth_token': token_id,
                    'auth_tenant_id': None,
                    'auth_user_id': None,
                    'endpoint_url': self.client.endpoint_url}
        self.assertEqual(client_.get_auth_info(), expected)

    @requests_mock.Mocker()
    def test_get_token(self, mrequests):
        auth_session, auth_plugin = setup_keystone_v2(mrequests)

        self.client = client.construct_http_client(
            username=USERNAME,
            tenant_name=TENANT_NAME,
            password=PASSWORD,
            auth_url=AUTH_URL,
            region_name=REGION,
            session=auth_session,
            auth=auth_plugin)

        self.mox.StubOutWithMock(self.client, "request")
        res200 = get_response(200)

        self.client.request(
            '/resource', 'GET',
            authenticated=True
        ).AndReturn((res200, ''))

        self.mox.ReplayAll()

        self.client.do_request('/resource', 'GET')

    def test_refresh_token(self):
        self.mox.StubOutWithMock(self.client, "request")

        token_id = uuid.uuid4().hex
        self.client.auth_token = token_id
        self.client.endpoint_url = ENDPOINT_URL

        res200 = get_response(200)
        res401 = get_response(401)

        # If a token is expired, neutron server retruns 401
        self.client.request(
            mox.StrContains(ENDPOINT_URL + '/resource'), 'GET',
            headers=mox.ContainsKeyValue('X-Auth-Token', token_id)
        ).AndReturn((res401, ''))
        self.client.request(
            AUTH_URL + '/tokens', 'POST',
            body=mox.IsA(str), headers=mox.IsA(dict)
        ).AndReturn((res200, json.dumps(KS_TOKEN_RESULT)))
        self.client.request(
            mox.StrContains(ENDPOINT_URL + '/resource'), 'GET',
            headers=mox.ContainsKeyValue('X-Auth-Token',
                                         KS_TOKEN_RESULT.token_id)
        ).AndReturn((res200, ''))
        self.mox.ReplayAll()
        self.client.do_request('/resource', 'GET')

    def test_refresh_token_no_auth_url(self):
        self.mox.StubOutWithMock(self.client, "request")
        self.client.auth_url = None

        token_id = uuid.uuid4().hex
        self.client.auth_token = token_id
        self.client.endpoint_url = ENDPOINT_URL

        res401 = get_response(401)

        # If a token is expired, neutron server returns 401
        self.client.request(
            mox.StrContains(ENDPOINT_URL + '/resource'), 'GET',
            headers=mox.ContainsKeyValue('X-Auth-Token', token_id)
        ).AndReturn((res401, ''))
        self.mox.ReplayAll()
        self.assertRaises(exceptions.NoAuthURLProvided,
                          self.client.do_request,
                          '/resource',
                          'GET')

    def test_get_endpoint_url_with_invalid_auth_url(self):
        # Handle the case when auth_url is not provided
        self.client.auth_url = None
        self.assertRaises(exceptions.NoAuthURLProvided,
                          self.client._get_endpoint_url)

    def test_get_endpoint_url(self):
        self.mox.StubOutWithMock(self.client, "request")

        token_id = uuid.uuid4().hex
        self.client.auth_token = token_id

        res200 = get_response(200)

        self.client.request(
            mox.StrContains(AUTH_URL + '/tokens/%s/endpoints' % token_id),
            'GET', headers=mox.IsA(dict)
        ).AndReturn((res200, json.dumps(ENDPOINTS_RESULT)))
        self.client.request(
            mox.StrContains(ENDPOINT_URL + '/resource'), 'GET',
            headers=mox.ContainsKeyValue('X-Auth-Token', token_id)
        ).AndReturn((res200, ''))
        self.mox.ReplayAll()
        self.client.do_request('/resource', 'GET')

    def test_use_given_endpoint_url(self):
        self.client = client.HTTPClient(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION,
            endpoint_url=ENDPOINT_OVERRIDE)
        self.assertEqual(self.client.endpoint_url, ENDPOINT_OVERRIDE)

        self.mox.StubOutWithMock(self.client, "request")

        token_id = uuid.uuid4().hex

        self.client.auth_token = token_id
        res200 = get_response(200)

        self.client.request(
            mox.StrContains(ENDPOINT_OVERRIDE + '/resource'), 'GET',
            headers=mox.ContainsKeyValue('X-Auth-Token', token_id)
        ).AndReturn((res200, ''))
        self.mox.ReplayAll()
        self.client.do_request('/resource', 'GET')
        self.assertEqual(self.client.endpoint_url, ENDPOINT_OVERRIDE)

    def test_get_endpoint_url_other(self):
        self.client = client.HTTPClient(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION, endpoint_type='otherURL')
        self.mox.StubOutWithMock(self.client, "request")

        token_id = uuid.uuid4().hex
        self.client.auth_token = token_id
        res200 = get_response(200)

        self.client.request(
            mox.StrContains(AUTH_URL + '/tokens/%s/endpoints' % token_id),
            'GET', headers=mox.IsA(dict)
        ).AndReturn((res200, json.dumps(ENDPOINTS_RESULT)))
        self.mox.ReplayAll()
        self.assertRaises(exceptions.EndpointTypeNotFound,
                          self.client.do_request,
                          '/resource',
                          'GET')

    def test_get_endpoint_url_failed(self):
        self.mox.StubOutWithMock(self.client, "request")

        token_id = uuid.uuid4().hex
        self.client.auth_token = token_id

        res200 = get_response(200)
        res401 = get_response(401)

        self.client.request(
            mox.StrContains(AUTH_URL + '/tokens/%s/endpoints' % token_id),
            'GET', headers=mox.IsA(dict)
        ).AndReturn((res401, ''))
        self.client.request(
            AUTH_URL + '/tokens', 'POST',
            body=mox.IsA(str), headers=mox.IsA(dict)
        ).AndReturn((res200, json.dumps(KS_TOKEN_RESULT)))
        self.client.request(
            mox.StrContains(ENDPOINT_URL + '/resource'), 'GET',
            headers=mox.ContainsKeyValue('X-Auth-Token',
                                         KS_TOKEN_RESULT.token_id)
        ).AndReturn((res200, ''))
        self.mox.ReplayAll()
        self.client.do_request('/resource', 'GET')

    @requests_mock.Mocker()
    def test_endpoint_type(self, mrequests):
        auth_session, auth_plugin = setup_keystone_v3(mrequests)

        # Test default behavior is to choose public.
        self.client = client.construct_http_client(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION,
            session=auth_session, auth=auth_plugin)

        self.client.authenticate()
        self.assertEqual(self.client.endpoint_url, PUBLIC_ENDPOINT_URL)

        # Test admin url
        self.client = client.construct_http_client(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION, endpoint_type='adminURL',
            session=auth_session, auth=auth_plugin)

        self.client.authenticate()
        self.assertEqual(self.client.endpoint_url, ADMIN_ENDPOINT_URL)

        # Test public url
        self.client = client.construct_http_client(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION, endpoint_type='publicURL',
            session=auth_session, auth=auth_plugin)

        self.client.authenticate()
        self.assertEqual(self.client.endpoint_url, PUBLIC_ENDPOINT_URL)

        # Test internal url
        self.client = client.construct_http_client(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION, endpoint_type='internalURL',
            session=auth_session, auth=auth_plugin)

        self.client.authenticate()
        self.assertEqual(self.client.endpoint_url, INTERNAL_ENDPOINT_URL)

        # Test url that isn't found in the service catalog
        self.client = client.construct_http_client(
            username=USERNAME, tenant_name=TENANT_NAME, password=PASSWORD,
            auth_url=AUTH_URL, region_name=REGION, endpoint_type='privateURL',
            session=auth_session, auth=auth_plugin)

        self.assertRaises(
            ks_exceptions.EndpointNotFound,
            self.client.authenticate)

    def test_strip_credentials_from_log(self):
        def verify_no_credentials(kwargs):
            return ('REDACTED' in kwargs['body']) and (
                self.client.password not in kwargs['body'])

        def verify_credentials(body):
            return 'REDACTED' not in body and self.client.password in body

        self.mox.StubOutWithMock(self.client, "request")
        self.mox.StubOutWithMock(utils, "http_log_req")

        res200 = get_response(200)

        utils.http_log_req(mox.IgnoreArg(), mox.IgnoreArg(), mox.Func(
            verify_no_credentials))
        self.client.request(
            mox.IsA(six.string_types), mox.IsA(six.string_types),
            body=mox.Func(verify_credentials),
            headers=mox.IgnoreArg()
        ).AndReturn((res200, json.dumps(KS_TOKEN_RESULT)))
        utils.http_log_req(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.client.request(
            mox.IsA(six.string_types), mox.IsA(six.string_types),
            headers=mox.IsA(dict)
        ).AndReturn((res200, ''))
        self.mox.ReplayAll()

        self.client.do_request('/resource', 'GET')


class CLITestAuthKeystoneWithId(CLITestAuthKeystone):

    def setUp(self):
        """Prepare the test environment."""
        super(CLITestAuthKeystoneWithId, self).setUp()
        self.client = client.HTTPClient(user_id=USER_ID,
                                        tenant_id=TENANT_ID,
                                        password=PASSWORD,
                                        auth_url=AUTH_URL,
                                        region_name=REGION)


class CLITestAuthKeystoneWithIdandName(CLITestAuthKeystone):

    def setUp(self):
        """Prepare the test environment."""
        super(CLITestAuthKeystoneWithIdandName, self).setUp()
        self.client = client.HTTPClient(username=USERNAME,
                                        user_id=USER_ID,
                                        tenant_id=TENANT_ID,
                                        tenant_name=TENANT_NAME,
                                        password=PASSWORD,
                                        auth_url=AUTH_URL,
                                        region_name=REGION)


class TestKeystoneClientVersions(testtools.TestCase):

    def setUp(self):
        """Prepare the test environment."""
        super(TestKeystoneClientVersions, self).setUp()
        self.mox = mox.Mox()
        self.addCleanup(self.mox.VerifyAll)
        self.addCleanup(self.mox.UnsetStubs)

    @requests_mock.Mocker()
    def test_v2_auth(self, mrequests):
        auth_session, auth_plugin = setup_keystone_v2(mrequests)
        res200 = get_response(200)

        self.client = client.construct_http_client(
            username=USERNAME,
            tenant_name=TENANT_NAME,
            password=PASSWORD,
            auth_url=AUTH_URL,
            region_name=REGION,
            session=auth_session,
            auth=auth_plugin)

        self.mox.StubOutWithMock(self.client, "request")

        self.client.request(
            '/resource', 'GET',
            authenticated=True
        ).AndReturn((res200, ''))

        self.mox.ReplayAll()
        self.client.do_request('/resource', 'GET')

    @requests_mock.Mocker()
    def test_v3_auth(self, mrequests):
        auth_session, auth_plugin = setup_keystone_v3(mrequests)
        res200 = get_response(200)

        self.client = client.construct_http_client(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            password=PASSWORD,
            auth_url=V3_URL,
            region_name=REGION,
            session=auth_session,
            auth=auth_plugin)

        self.mox.StubOutWithMock(self.client, "request")

        self.client.request(
            '/resource', 'GET',
            authenticated=True
        ).AndReturn((res200, ''))

        self.mox.ReplayAll()
        self.client.do_request('/resource', 'GET')
