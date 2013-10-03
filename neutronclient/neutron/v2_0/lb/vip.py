# Copyright 2013 Mirantis Inc.
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
# @author: Ilya Shakhat, Mirantis Inc.
#
# vim: tabstop=4 shiftwidth=4 softtabstop=4

import logging

from neutronclient.neutron import v2_0 as neutronV20


class ListVip(neutronV20.ListCommand):
    """List vips that belong to a given tenant."""

    resource = 'vip'
    log = logging.getLogger(__name__ + '.ListVip')
    list_columns = ['id', 'name', 'algorithm', 'address', 'protocol',
                    'admin_state_up', 'status']
    pagination_support = True
    sorting_support = True


class ShowVip(neutronV20.ShowCommand):
    """Show information of a given vip."""

    resource = 'vip'
    log = logging.getLogger(__name__ + '.ShowVip')


class CreateVip(neutronV20.CreateCommand):
    """Create a vip."""

    resource = 'vip'
    log = logging.getLogger(__name__ + '.CreateVip')

    def add_known_arguments(self, parser):
        parser.add_argument(
            'pool_id', metavar='POOL',
            help='Pool id or name this vip belongs to')
        parser.add_argument(
            '--address',
            help='IP address of the vip')
        parser.add_argument(
            '--admin-state-down',
            dest='admin_state', action='store_false',
            help='set admin state up to false')
        parser.add_argument(
            '--connection-limit',
            help='the maximum number of connections per second allowed for '
                 'the vip. Positive integer or -1 for unlimited (default)')
        parser.add_argument(
            '--description',
            help='description of the vip')
        parser.add_argument(
            '--name',
            required=True,
            help='name of the vip')
        parser.add_argument(
            '--protocol-port',
            required=True,
            help='TCP port on which to listen for client traffic that is '
                 'associated with the vip address')
        parser.add_argument(
            '--protocol',
            required=True, choices=['TCP', 'HTTP', 'HTTPS'],
            help='protocol for balancing')
        parser.add_argument(
            '--subnet-id', metavar='SUBNET',
            required=True,
            help='the subnet on which to allocate the vip address')

    def args2body(self, parsed_args):
        _pool_id = neutronV20.find_resourceid_by_name_or_id(
            self.get_client(), 'pool', parsed_args.pool_id)
        _subnet_id = neutronV20.find_resourceid_by_name_or_id(
            self.get_client(), 'subnet', parsed_args.subnet_id)

        body = {
            self.resource: {
                'pool_id': _pool_id,
                'admin_state_up': parsed_args.admin_state,
                'subnet_id': _subnet_id,
            },
        }
        neutronV20.update_dict(parsed_args, body[self.resource],
                               ['address', 'connection_limit', 'description',
                                'name', 'protocol_port', 'protocol',
                                'tenant_id'])
        return body


class UpdateVip(neutronV20.UpdateCommand):
    """Update a given vip."""

    resource = 'vip'
    log = logging.getLogger(__name__ + '.UpdateVip')


class DeleteVip(neutronV20.DeleteCommand):
    """Delete a given vip."""

    resource = 'vip'
    log = logging.getLogger(__name__ + '.DeleteVip')