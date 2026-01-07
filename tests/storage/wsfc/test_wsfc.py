"""
Tests for Windows Server Failover Clustering (WSFC) functionality
"""

import logging

import pytest
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine import VirtualMachine

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from utilities.constants import Images, TIMEOUT_2MIN, TIMEOUT_4MIN
from utilities.storage import check_disk_count_in_vm
from utilities.virt import (
    VirtualMachineForTests,
    running_vm,
    wait_for_windows_vm,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.sno,
]


class TestWSFCResources:
    """Basic WSFC resource creation tests."""
    
    @pytest.mark.polarion("CNV-WSFC-SMOKE")  
    def test_wsfc_resources_creation(
        self,
        wsfc_namespace,
        pvc_lun1,
        pvc_lun2,
        l2_cluster_nad1,
        l2_cluster_nad2,
        trident_iscsi_storage_class,
        unprivileged_client,
    ):
        """Smoke test to verify all WSFC resources are created successfully."""
        LOGGER.info("Testing WSFC resources creation")
        

        import pdb; pdb.set_trace()
        
        # Verify namespace exists
        assert wsfc_namespace.exists, f"Namespace {wsfc_namespace.name} should exist"
        LOGGER.info(f"✓ Namespace {wsfc_namespace.name} exists")
        
        # Verify PVC LUN1
        assert pvc_lun1.exists, f"PVC {pvc_lun1.name} should exist"
        assert pvc_lun1.status == PersistentVolumeClaim.Status.BOUND, (
            f"PVC {pvc_lun1.name} should be bound, got {pvc_lun1.status}"
        )
        assert pvc_lun1.volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK, (
            f"PVC {pvc_lun1.name} should have block volume mode"
        )
        LOGGER.info(f"✓ PVC {pvc_lun1.name} exists and is bound")
        
        # Verify PVC LUN2
        assert pvc_lun2.exists, f"PVC {pvc_lun2.name} should exist"
        assert pvc_lun2.status == PersistentVolumeClaim.Status.BOUND, (
            f"PVC {pvc_lun2.name} should be bound, got {pvc_lun2.status}"
        )
        assert pvc_lun2.volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK, (
            f"PVC {pvc_lun2.name} should have block volume mode"
        )
        LOGGER.info(f"✓ PVC {pvc_lun2.name} exists and is bound")
        
        # Verify NAD1
        assert l2_cluster_nad1.exists, f"NAD {l2_cluster_nad1.name} should exist"
        assert l2_cluster_nad1.namespace == "default", (
            f"NAD {l2_cluster_nad1.name} should be in default namespace"
        )
        LOGGER.info(f"✓ NAD {l2_cluster_nad1.name} exists in namespace {l2_cluster_nad1.namespace}")
        
        # Verify NAD2  
        assert l2_cluster_nad2.exists, f"NAD {l2_cluster_nad2.name} should exist"
        assert l2_cluster_nad2.namespace == "default", (
            f"NAD {l2_cluster_nad2.name} should be in default namespace"
        )
        LOGGER.info(f"✓ NAD {l2_cluster_nad2.name} exists in namespace {l2_cluster_nad2.namespace}")
        
        # Verify StorageClass
        assert trident_iscsi_storage_class.exists, f"StorageClass {trident_iscsi_storage_class.name} should exist"
        assert trident_iscsi_storage_class.name == "trident-csi-iscsi", (
            f"StorageClass should be named trident-csi-iscsi, got {trident_iscsi_storage_class.name}"
        )
        assert trident_iscsi_storage_class.provisioner == "csi.trident.netapp.io", (
            f"StorageClass should have Trident provisioner"
        )
        LOGGER.info(f"✓ StorageClass {trident_iscsi_storage_class.name} exists with correct provisioner")
        
        # Verify both PVCs have different names
        assert pvc_lun1.name != pvc_lun2.name, (
            f"PVCs should have different names: {pvc_lun1.name} vs {pvc_lun2.name}"
        )
        
        # Log summary
        LOGGER.info("✅ All WSFC resources created successfully:")
        LOGGER.info(f"  - Namespace: {wsfc_namespace.name}")
        LOGGER.info(f"  - PVC LUN1: {pvc_lun1.name} ({pvc_lun1.size})")
        LOGGER.info(f"  - PVC LUN2: {pvc_lun2.name} ({pvc_lun2.size})")
        LOGGER.info(f"  - NAD1: {l2_cluster_nad1.name}")
        LOGGER.info(f"  - NAD2: {l2_cluster_nad2.name}")
        LOGGER.info(f"  - StorageClass: {trident_iscsi_storage_class.name}")



