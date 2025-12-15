"""
Pytest conftest file for Windows Server Failover Clustering (WSFC) tests
"""

import base64

import pytest
from ocp_resources.config_map import ConfigMap
from ocp_resources.secret import Secret
from utilities.artifactory import get_artifactory_config_map, get_artifactory_secret

from .utils import create_wsfc_lun_pvc

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def wsfc_namespace(unprivileged_client):
    """Create a dedicated namespace for WSFC tests."""
    from utilities.infra import create_ns
    
    with create_ns(
        name="wsfc-test",
        client=unprivileged_client,
        teardown=True,
    ) as ns:
        yield ns

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
def pvc_lun1(wsfc_namespace, unprivileged_client):
    """Create scsi-pvc-bm1 LUN for WSFC cluster."""
    with create_wsfc_lun_pvc(
        pvc_name="scsi-pvc-bm1",
        namespace=wsfc_namespace.name,
        client=unprivileged_client,
        storage_class="trident-csi-iscsi",
        size="70Gi",
    ) as pvc:
        yield pvc


@pytest.fixture(scope="module")
def pvc_lun2(wsfc_namespace, unprivileged_client):
    """Create scsi-pvc-bm2 LUN for WSFC cluster."""
    with create_wsfc_lun_pvc(
        pvc_name="scsi-pvc-bm2",
        namespace=wsfc_namespace.name,
        storage_class="trident-csi-iscsi",
        client=unprivileged_client,
        size="50Gi",
    ) as pvc:
        yield pvc


