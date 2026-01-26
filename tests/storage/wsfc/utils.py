from contextlib import contextmanager

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.storage_class import StorageClass
from libs.net import netattachdef
from utilities.constants import TIMEOUT_1MIN
from utilities.storage import get_default_storage_class


@contextmanager
def create_wsfc_lun_pvc(
    pvc_name,
    namespace,
    client,
    size="50Gi",
    access_mode=PersistentVolumeClaim.AccessMode.RWX,
    volume_mode=PersistentVolumeClaim.VolumeMode.BLOCK,
    storage_class=None,
):
    # Check if PVC already exists
    existing_pvc = PersistentVolumeClaim(
        client=client,
        name=pvc_name,
        namespace=namespace,
    )
    
    if existing_pvc.exists:
        print(f"✓ PVC {pvc_name} already exists in namespace {namespace}")
        yield existing_pvc
    else:
        print(f"Creating PVC {pvc_name} in namespace {namespace}")
        if not storage_class:
            storage_class = get_default_storage_class(client).name

        with PersistentVolumeClaim(
            client=client,
            name=pvc_name,
            namespace=namespace,
            accessmodes=access_mode,
            size=size,
            volume_mode=volume_mode,
            storage_class=storage_class,
        ) as pvc:
            pvc.wait_for_status(
                status=PersistentVolumeClaim.Status.BOUND,
                timeout=TIMEOUT_1MIN, 
            )
            yield pvc


@contextmanager
def create_l2_cluster_nad(
    name="l2-cluster-net",
    namespace="default",
    client=None,
    topology="layer2",
    config_name=None,
):
    """Create L2 cluster NetworkAttachmentDefinition for WSFC testing."""
    # Check if NAD already exists
    existing_nad = netattachdef.NetworkAttachmentDefinition(
        name=name,
        namespace=namespace,
        config=netattachdef.NetConfig(name=config_name, plugins=[]),
        client=client,
    )
    
    if existing_nad.exists:
        print(f"✓ NAD {name} already exists in namespace {namespace}")
        yield existing_nad
    else:
        print(f"Creating NAD {name} in namespace {namespace}")
        with netattachdef.NetworkAttachmentDefinition(
            name=name,
            namespace=namespace,
            config=netattachdef.NetConfig(
                name=config_name,
                plugins=[
                    netattachdef.CNIPluginOvnK8sConfig(
                        topology=topology,
                        netAttachDefName=f"{namespace}/{name}",
                    )
                ],
            ),
            client=client,
        ) as nad:
            yield nad


@contextmanager
def create_trident_iscsi_storage_class(
    name="trident-csi-iscsi",
    client=None,
    is_default_class=True,
    is_default_virt_class=True,
    backend_type="ontap-san",
):
    """Create Trident iSCSI StorageClass for WSFC testing."""
    # Check if StorageClass already exists
    existing_sc = StorageClass(name=name, client=client)
    
    if existing_sc.exists:
        print(f"✓ StorageClass {name} already exists")
        yield existing_sc
    else:
        print(f"Creating StorageClass {name}")
        
        # Prepare annotations
        annotations = {}
        if is_default_class:
            annotations["storageclass.kubernetes.io/is-default-class"] = "true"
        if is_default_virt_class:
            annotations["storageclass.kubevirt.io/is-default-virt-class"] = "true"
        
        # Add kubectl last-applied-configuration annotation
        last_applied_config = {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "StorageClass", 
            "metadata": {
                "annotations": {},
                "name": name
            },
            "parameters": {
                "backendType": backend_type
            },
            "provisioner": "csi.trident.netapp.io"
        }
        
        import json
        annotations["kubectl.kubernetes.io/last-applied-configuration"] = json.dumps(last_applied_config, separators=(',', ':'))
            
        with StorageClass(
            name=name,
            provisioner="csi.trident.netapp.io",
            reclaim_policy=StorageClass.ReclaimPolicy.DELETE,
            volume_binding_mode=StorageClass.VolumeBindingMode.Immediate,
            annotations=annotations,
            parameters={
                "backendType": backend_type
            },
            client=client,
        ) as sc:
            yield sc
