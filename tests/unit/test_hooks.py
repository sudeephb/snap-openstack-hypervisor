# Copyright 2022 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from unittest import mock

import pytest

from openstack_hypervisor import hooks


class TestHooks:
    """Contains tests for openstack_hypervisor.hooks."""

    def test_install_hook(self, snap, os_makedirs):
        """Tests the install hook."""
        hooks.install(snap)

    def test_get_template(self, mocker, snap):
        """Tests retrieving the template."""
        mock_fs_loader = mocker.patch.object(hooks, "FileSystemLoader")
        mocker.patch.object(hooks, "Environment")
        hooks._get_template(snap, "foo.bar")
        mock_fs_loader.assert_called_once_with(searchpath=str(snap.paths.snap / "templates"))

    def test_configure_hook(
        self, mocker, snap, os_makedirs, check_call, link_lookup, split, addr, link, ip_interface
    ):
        """Tests the configure hook."""
        mock_template = mocker.Mock()
        mocker.patch.object(hooks, "_get_template", return_value=mock_template)
        mock_file = mocker.patch("builtins.open", mocker.mock_open())

        hooks.configure(snap)

        mock_template.render.assert_called()
        mock_file.assert_called()

    def test_configure_hook_exception(self, mocker, snap, os_makedirs, check_call):
        """Tests the configure hook raising an exception while writing file."""
        mock_template = mocker.Mock()
        mocker.patch.object(hooks, "_get_template", return_value=mock_template)
        mock_file = mocker.patch("builtins.open", mocker.mock_open())
        mock_file.side_effect = FileNotFoundError

        with pytest.raises(FileNotFoundError):
            hooks.configure(snap)

    def test_services(self):
        """Test getting a list of managed services."""
        assert hooks.services() == [
            "libvirtd",
            "neutron-ovn-metadata-agent",
            "nova-api-metadata",
            "nova-compute",
            "virtlogd",
        ]

    def test_section_complete(self):
        assert hooks._section_complete("identity", {"identity": {"password": "foo"}})
        assert hooks._section_complete(
            "identity", {"identity": {"username": "user", "password": "foo"}}
        )
        assert not hooks._section_complete(
            "identity", {"identity": {"username": "user", "password": ""}}
        )
        assert not hooks._section_complete("identity", {"identity": {"password": ""}})
        assert not hooks._section_complete("identity", {"rabbitmq": {"url": "rabbit://sss"}})

    def test_check_config_present(self):
        assert hooks._check_config_present("identity.password", {"identity": {"password": "foo"}})
        assert hooks._check_config_present("identity", {"identity": {"password": "foo"}})
        assert not hooks._check_config_present(
            "identity.password", {"rabbitmq": {"url": "rabbit://sss"}}
        )

    def test_services_not_ready(self, snap):
        config = {}
        assert hooks._services_not_ready(config) == [
            "neutron-ovn-metadata-agent",
            "nova-api-metadata",
            "nova-compute",
        ]
        config["identity"] = {"username": "user", "password": "pass"}
        assert hooks._services_not_ready(config) == [
            "neutron-ovn-metadata-agent",
            "nova-api-metadata",
            "nova-compute",
        ]
        config["rabbitmq"] = {"url": "rabbit://localhost:5672"}
        config["node"] = {"fqdn": "myhost.maas"}
        assert hooks._services_not_ready(config) == [
            "neutron-ovn-metadata-agent",
            "nova-api-metadata",
        ]
        config["network"] = {
            "external-bridge-address": "10.0.0.10",
            "ovn_cert": "cert",
            "ovn_key": "key",
            "ovn_cacert": "cacert",
        }
        assert hooks._services_not_ready(config) == ["neutron-ovn-metadata-agent"]
        config["credentials"] = {"ovn_metadata_proxy_shared_secret": "secret"}
        assert hooks._services_not_ready(config) == []

    def test_list_bridge_ifaces(self, check_output):
        check_output.return_value = b"int1\nint2\n"
        assert hooks._list_bridge_ifaces("br1") == ["int1", "int2"]
        check_output.assert_called_once_with(["ovs-vsctl", "--retry", "list-ifaces", "br1"])

    def test_add_interface_to_bridge(self, check_call, check_output):
        check_output.return_value = b"int1\nint2\n"
        hooks._add_interface_to_bridge("br1", "int3")
        check_call.assert_called_once_with(
            [
                "ovs-vsctl",
                "--retry",
                "add-port",
                "br1",
                "int3",
                "--",
                "set",
                "Port",
                "int3",
                "external-ids:microstack-function=ext-port",
            ]
        )

    def test_add_interface_to_bridge_noop(self, check_call, check_output):
        check_output.return_value = b"int1\nint2\n"
        hooks._add_interface_to_bridge("br1", "int2")
        assert not check_call.called

    def test_del_interface_from_bridge(self, check_call, check_output):
        check_output.return_value = b"int1\nint2\n"
        hooks._del_interface_from_bridge("br1", "int2")
        check_call.assert_called_once_with(["ovs-vsctl", "--retry", "del-port", "br1", "int2"])

    def test_del_interface_from_bridge_noop(self, check_call, check_output):
        check_output.return_value = b"int1\nint2\n"
        hooks._del_interface_from_bridge("br1", "int3")
        assert not check_call.called

    def test_get_external_ports_on_bridge(self, check_output, mocker):
        port_data = {
            "data": [
                [
                    ["uuid", "efd95c01-d658-4847-8506-664eec95e653"],
                    ["set", []],
                    0,
                    False,
                    ["set", []],
                    0,
                    ["set", []],
                    ["map", [["microk8s-function", "external-nic"]]],
                    False,
                    ["uuid", "92f62f7c-53f2-4362-bbd5-9b46b8f88632"],
                    ["set", []],
                    ["set", []],
                    "enp6s0",
                    ["map", []],
                    False,
                    ["set", []],
                    ["map", []],
                    ["map", []],
                    ["map", []],
                    ["map", []],
                    ["set", []],
                    ["set", []],
                    ["set", []],
                ]
            ],
            "headings": [
                "_uuid",
                "bond_active_slave",
                "bond_downdelay",
                "bond_fake_iface",
                "bond_mode",
                "bond_updelay",
                "cvlans",
                "external_ids",
                "fake_bridge",
                "interfaces",
                "lacp",
                "mac",
                "name",
                "other_config",
                "protected",
                "qos",
                "rstp_statistics",
                "rstp_status",
                "statistics",
                "status",
                "tag",
                "trunks",
                "vlan_mode",
            ],
        }

        check_output.return_value = str.encode(json.dumps(port_data))
        mock_list_ifaces = mocker.patch.object(hooks, "_list_bridge_ifaces")
        mock_list_ifaces.return_value = ["enp6s0"]
        assert hooks._get_external_ports_on_bridge("br-ex") == ["enp6s0"]
        mock_list_ifaces.return_value = []
        assert hooks._get_external_ports_on_bridge("br-ex") == []

    def test_ensure_single_nic_on_bridge(self, mocker):
        mock_get_external_ports_on_bridge = mocker.patch.object(
            hooks, "_get_external_ports_on_bridge"
        )
        mock_add_interface_to_bridge = mocker.patch.object(hooks, "_add_interface_to_bridge")
        mock_del_interface_from_bridge = mocker.patch.object(hooks, "_del_interface_from_bridge")
        mock_get_external_ports_on_bridge.return_value = ["eth0", "eth1"]
        hooks._ensure_single_nic_on_bridge("br-ex", "eth1")
        assert not mock_add_interface_to_bridge.called
        mock_del_interface_from_bridge.assert_called_once_with("br-ex", "eth0")

        mock_get_external_ports_on_bridge.reset_mock()
        mock_add_interface_to_bridge.reset_mock()
        mock_del_interface_from_bridge.reset_mock()
        mock_get_external_ports_on_bridge.return_value = []
        hooks._ensure_single_nic_on_bridge("br-ex", "eth1")
        mock_add_interface_to_bridge.assert_called_once_with("br-ex", "eth1")
        assert not mock_del_interface_from_bridge.called

    def test_del_external_nics_from_bridge(self, mocker):
        mock_get_external_ports_on_bridge = mocker.patch.object(
            hooks, "_get_external_ports_on_bridge"
        )
        mock_del_interface_from_bridge = mocker.patch.object(hooks, "_del_interface_from_bridge")
        mock_get_external_ports_on_bridge.return_value = ["eth0", "eth1"]
        hooks._del_external_nics_from_bridge("br-ex")
        expect = [mock.call("br-ex", "eth0"), mock.call("br-ex", "eth1")]
        mock_del_interface_from_bridge.assert_has_calls(expect)
