from contextlib import contextmanager

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from tests.global_config import py_config


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
    if not storage_class:
        storage_class = py_config["default_storage_class"]

    with PersistentVolumeClaim(
        client=client,
        name=pvc_name,
        namespace=namespace,
        accessmodes=access_mode,
        size=size,
        volume_mode=volume_mode,
        storage_class=storage_class,
    ) as pvc:
        pvc.wait()
        yield pvc