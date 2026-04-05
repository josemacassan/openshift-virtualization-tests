from kubernetes.dynamic import DynamicClient

from libs.net.vmspec import add_network_interface
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Interface, Metadata, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.localnet.liblocalnet import LOCALNET_IPAM_LOGICAL_NETWORK, LOCALNET_TEST_LABEL


def localnet_ipam_vm(
    namespace: str,
    name: str,
    nad_name: str,
    client: DynamicClient,
) -> BaseVirtualMachine:
    """
    Create a Fedora-based Virtual Machine connected to a localnet IPAM-backed network.

    The VM attaches to a Multus network using a bridge interface without static cloud-init
    IP config, relying on IPAM (internal DHCPv4) for address assignment.
    """
    spec = base_vmspec()
    spec.template.metadata = spec.template.metadata or Metadata()
    spec.template.metadata.labels = spec.template.metadata.labels or {}
    spec.template.metadata.labels.update(LOCALNET_TEST_LABEL)
    vmi_spec = add_network_interface(
        vmi_spec=spec.template.spec,
        network=Network(name=LOCALNET_IPAM_LOGICAL_NETWORK, multus=Multus(networkName=nad_name)),
        interface=Interface(name=LOCALNET_IPAM_LOGICAL_NETWORK, bridge={}),
    )
    vmi_spec.affinity = new_pod_anti_affinity(label=next(iter(LOCALNET_TEST_LABEL.items())))
    vmi_spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].namespaceSelector = {}
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)
