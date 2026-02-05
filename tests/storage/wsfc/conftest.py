"""
Pytest conftest file for Windows Server Failover Clustering (WSFC) tests
"""

import base64
import logging

import pytest
from ocp_resources.config_map import ConfigMap
from ocp_resources.secret import Secret
from utilities.artifactory import get_artifactory_config_map, get_artifactory_secret

from .utils import create_wsfc_lun_pvc, create_l2_cluster_nad, create_trident_iscsi_storage_class

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def wsfc_namespace(admin_client):
    """Create a dedicated namespace for WSFC tests."""
    from utilities.infra import create_ns
    from ocp_resources.namespace import Namespace
    
    # Check if namespace already exists
    existing_ns = Namespace(name="wsfc-test", client=admin_client)
    if existing_ns.exists:
        print(f"✓ Namespace wsfc-test already exists")
        yield existing_ns
    else:
        print(f"Creating namespace wsfc-test")
        yield from create_ns(
            name="wsfc-test",
            admin_client=admin_client,
            teardown=True,
        )


@pytest.fixture(scope="module")
def trident_iscsi_storage_class(admin_client):
    """Create Trident iSCSI StorageClass for WSFC tests."""
    with create_trident_iscsi_storage_class(
        name="trident-csi-iscsi",
        client=admin_client,
        is_default_class=True,
        is_default_virt_class=True,
        backend_type="ontap-san",
    ) as sc:
        yield sc

@pytest.fixture(scope="module")
def artifactory_secret_wsfc(wsfc_namespace):
    """Create artifactory secret for WSFC namespace."""
    artifactory_secret = get_artifactory_secret(namespace=wsfc_namespace.name)
    yield artifactory_secret
    if artifactory_secret.exists:
        artifactory_secret.clean_up()


@pytest.fixture(scope="module")
def artifactory_config_map_wsfc(wsfc_namespace):
    """Create artifactory config map for WSFC namespace."""
    artifactory_config_map = get_artifactory_config_map(namespace=wsfc_namespace.name)
    yield artifactory_config_map
    if artifactory_config_map.exists:
        artifactory_config_map.clean_up()


@pytest.fixture(scope="module") 
def pvc_lun1(wsfc_namespace, unprivileged_client, trident_iscsi_storage_class):
    """Create scsi-pvc-bm1 LUN for WSFC cluster using Trident iSCSI storage class."""
    with create_wsfc_lun_pvc(
        pvc_name="scsi-pvc-bm1",
        namespace=wsfc_namespace.name,
        client=unprivileged_client,
        storage_class=trident_iscsi_storage_class.name,
        size="70Gi",
    ) as pvc:
        yield pvc


@pytest.fixture(scope="module")
def pvc_lun2(wsfc_namespace, unprivileged_client, trident_iscsi_storage_class):
    """Create scsi-pvc-bm2 LUN for WSFC cluster using Trident iSCSI storage class."""
    with create_wsfc_lun_pvc(
        pvc_name="scsi-pvc-bm2",
        namespace=wsfc_namespace.name,
        client=unprivileged_client,
        storage_class=trident_iscsi_storage_class.name,
        size="50Gi",
    ) as pvc:
        yield pvc


@pytest.fixture(scope="module")
def l2_cluster_nad1(unprivileged_client):
    """Create first L2 cluster NAD for WSFC tests in default namespace."""
    with create_l2_cluster_nad(
        name="l2-cluster-net1",
        namespace="default",
        client=unprivileged_client,
        config_name="l2-cluster-net1",
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def l2_cluster_nad2(unprivileged_client):
    """Create second L2 cluster NAD for WSFC tests in default namespace."""
    with create_l2_cluster_nad(
        name="l2-cluster-net2",
        namespace="default", 
        client=unprivileged_client,
        config_name="l2-cluster-net2",
    ) as nad:
        yield nad





