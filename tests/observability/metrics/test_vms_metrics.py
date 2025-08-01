import logging
from datetime import datetime, timezone

import bitmath
import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.metrics.constants import (
    KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI,
    KUBEVIRT_VM_DISK_ALLOCATED_SIZE_BYTES,
    KUBEVIRT_VMI_MEMORY_AVAILABLE_BYTES,
    KUBEVIRT_VMI_PHASE_TRANSITION_TIME_FROM_DELETION_SECONDS_SUM_SUCCEEDED,
    KUBEVIRT_VMSNAPSHOT_PERSISTENTVOLUMECLAIM_LABELS,
    KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI,
)
from tests.observability.metrics.utils import (
    compare_metric_file_system_values_with_vm_file_system_values,
    expected_metric_labels_and_values,
    get_metric_labels_non_empty_value,
    get_pvc_size_bytes,
    timestamp_to_seconds,
    validate_metric_value_greater_than_initial_value,
    validate_metric_value_within_range,
    validate_metric_vm_container_free_memory_bytes_based_on_working_set_rss_bytes,
    validate_vnic_info,
)
from tests.observability.utils import validate_metrics_value
from tests.os_params import FEDORA_LATEST_LABELS, RHEL_LATEST
from utilities.constants import (
    CAPACITY,
    LIVE_MIGRATE,
    MIGRATION_POLICY_VM_LABEL,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_30SEC,
    USED,
)
from utilities.infra import get_node_selector_dict
from utilities.monitoring import get_metrics_value
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)


def get_last_transition_time(vm):
    for condition in vm.instance.get("status", {}).get("conditions"):
        if condition.get("type") == vm.Condition.READY:
            last_transition_time = condition.get("lastTransitionTime")
            return int(
                (datetime.strptime(last_transition_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).timestamp()
            )


def check_vm_last_transition_metric_value(prometheus, metric, vm):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_30SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=f"{metric}{{name='{vm.name}'}}",
    )
    sample, last_transition_time = None, None
    try:
        for sample in samples:
            if sample:
                last_transition_time = get_last_transition_time(vm=vm)
                if int(sample) == last_transition_time:
                    break
    except TimeoutExpiredError:
        LOGGER.error(f"Metric value: {sample} does not match vm's last transition timestamp: {last_transition_time}")
        raise


@pytest.fixture()
def stopped_vm_metric_1(vm_metric_1):
    vm_metric_1.stop(wait=True)


@pytest.fixture()
def vm_in_error_state(namespace):
    vm_name = "vm-in-error-state"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=fedora_vm_body(name=vm_name),
        node_selector=get_node_selector_dict(node_selector="non-existent-node"),
    ) as vm:
        vm.start()
        vm.wait_for_specific_status(status=VirtualMachine.Status.ERROR_UNSCHEDULABLE)
        yield vm


@pytest.fixture()
def pvc_for_vm_in_starting_state(namespace):
    with PersistentVolumeClaim(
        name="vm-in-starting-state-pvc",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWX,
        size="1Gi",
        pvlabel="non-existent-pv",
    ) as pvc:
        yield pvc


@pytest.fixture()
def vm_in_starting_state(namespace, pvc_for_vm_in_starting_state):
    vm_name = "vm-in-starting-state"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=fedora_vm_body(name=vm_name),
        pvc=pvc_for_vm_in_starting_state,
    ) as vm:
        vm.start()
        vm.wait_for_specific_status(status=VirtualMachine.Status.WAITING_FOR_VOLUME_BINDING)
        yield vm


@pytest.fixture(scope="class")
def vm_metric_1(namespace, unprivileged_client, cluster_common_node_cpu):
    vm_name = "vm-metrics-1"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        cpu_model=cluster_common_node_cpu,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def vm_metric_1_vmim(vm_metric_1):
    with VirtualMachineInstanceMigration(
        name="vm-metric-1-vmim",
        namespace=vm_metric_1.namespace,
        vmi_name=vm_metric_1.vmi.name,
    ) as vmim:
        vmim.wait_for_status(status=vmim.Status.RUNNING, timeout=TIMEOUT_3MIN)
        yield


@pytest.fixture(scope="class")
def vm_metric_2(namespace, unprivileged_client):
    vm_name = "vm-metrics-2"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture(scope="class")
def number_of_running_vmis(admin_client):
    return len(list(VirtualMachineInstance.get(dyn_client=admin_client)))


def check_vmi_metric(prometheus):
    response = prometheus.query(query="cnv:vmi_status_running:count")
    assert response["status"] == "success"
    return sum(int(node["value"][1]) for node in response["data"]["result"])


def check_vmi_count_metric(expected_vmi_count, prometheus):
    LOGGER.info(f"Check VMI metric expected: {expected_vmi_count}")
    samples = TimeoutSampler(
        wait_timeout=100,
        sleep=5,
        func=check_vmi_metric,
        prometheus=prometheus,
    )
    for sample in samples:
        if sample == expected_vmi_count:
            return True


class TestVMICountMetric:
    @pytest.mark.polarion("CNV-3048")
    def test_vmi_count_metric_increase(
        self,
        prometheus,
        number_of_running_vmis,
        vm_metric_1,
        vm_metric_2,
    ):
        assert check_vmi_count_metric(number_of_running_vmis + 2, prometheus)

    @pytest.mark.polarion("CNV-3589")
    def test_vmi_count_metric_decrease(
        self,
        prometheus,
        number_of_running_vmis,
        vm_metric_1,
        vm_metric_2,
    ):
        vm_metric_2.stop(wait=True)
        assert check_vmi_count_metric(number_of_running_vmis + 1, prometheus)


class TestVMStatusLastTransitionMetrics:
    @pytest.mark.polarion("CNV-9661")
    def test_vm_running_status_metrics(self, prometheus, vm_metric_1):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric="kubevirt_vm_running_status_last_transition_timestamp_seconds",
            vm=vm_metric_1,
        )

    @pytest.mark.polarion("CNV-9662")
    def test_vm_error_status_metrics(self, prometheus, vm_in_error_state):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric="kubevirt_vm_error_status_last_transition_timestamp_seconds",
            vm=vm_in_error_state,
        )

    @pytest.mark.polarion("CNV-9665")
    def test_vm_migrating_status_metrics(
        self, skip_if_no_common_cpu, prometheus, vm_metric_1, migration_policy_with_bandwidth, vm_metric_1_vmim
    ):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric="kubevirt_vm_migrating_status_last_transition_timestamp_seconds",
            vm=vm_metric_1,
        )

    @pytest.mark.polarion("CNV-9664")
    def test_vm_non_running_status_metrics(self, prometheus, vm_metric_1, stopped_vm_metric_1):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric="kubevirt_vm_non_running_status_last_transition_timestamp_seconds",
            vm=vm_metric_1,
        )

    @pytest.mark.polarion("CNV-9751")
    def test_vm_starting_status_metrics(self, prometheus, vm_in_starting_state):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric="kubevirt_vm_starting_status_last_transition_timestamp_seconds",
            vm=vm_in_starting_state,
        )


@pytest.mark.parametrize(
    "vm_for_test",
    [pytest.param("console-vm-test")],
    indirect=True,
)
@pytest.mark.usefixtures("vm_for_test")
class TestVmConsolesAndVmCreateDateTimestampMetrics:
    @pytest.mark.polarion("CNV-11024")
    def test_kubevirt_console_active_connections(self, prometheus, vm_for_test, connected_vm_console_successfully):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI.format(vm_name=vm_for_test.name),
            expected_value="1",
        )

    @pytest.mark.polarion("CNV-10842")
    def test_kubevirt_vnc_active_connections(self, prometheus, vm_for_test, connected_vnc_console):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI.format(vm_name=vm_for_test.name),
            expected_value="1",
        )

    @pytest.mark.polarion("CNV-11805")
    def test_metric_kubevirt_vm_create_date_timestamp_seconds(self, prometheus, vm_for_test):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_create_date_timestamp_seconds{{name='{vm_for_test.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=vm_for_test.instance.metadata.creationTimestamp)),
        )


class TestVmiMemoryCachedBytes:
    @pytest.mark.parametrize(
        "vm_for_test",
        [pytest.param("test-vm-memory-cached", marks=pytest.mark.polarion("CNV-11031"))],
        indirect=True,
    )
    def test_kubevirt_vmi_memory_cached_bytes(
        self,
        prometheus,
        vm_for_test,
        memory_cached_sum_from_vm_console,
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            expected_value=memory_cached_sum_from_vm_console,
            metric_name=f"kubevirt_vmi_memory_cached_bytes{{name='{vm_for_test.name}'}}",
        )


@pytest.mark.parametrize("vm_for_test", [pytest.param("file-system-metrics")], indirect=True)
class TestVmiFileSystemMetricsLinux:
    @pytest.mark.parametrize(
        "file_system_metric_mountpoints_existence, capacity_or_used",
        [
            pytest.param(
                CAPACITY,
                CAPACITY,
                marks=pytest.mark.polarion("CNV-11406"),
                id="test_metric_kubevirt_vmi_filesystem_capacity_bytes",
            ),
            pytest.param(
                USED,
                USED,
                marks=pytest.mark.polarion("CNV-11407"),
                id="test_metric_kubevirt_vmi_filesystem_used_bytes",
            ),
        ],
        indirect=["file_system_metric_mountpoints_existence"],
    )
    def test_metric_kubevirt_vmi_filesystem_capacity_used_bytes_linux(
        self,
        prometheus,
        vm_for_test,
        file_system_metric_mountpoints_existence,
        disk_file_system_info_linux,
        capacity_or_used,
    ):
        compare_metric_file_system_values_with_vm_file_system_values(
            prometheus=prometheus,
            vm_for_test=vm_for_test,
            mount_point=[*disk_file_system_info_linux][0],
            capacity_or_used=capacity_or_used,
        )


@pytest.mark.tier3
class TestVmiFileSystemMetricsWindows:
    @pytest.mark.parametrize(
        "capacity_or_used",
        [
            pytest.param(
                CAPACITY,
                marks=pytest.mark.polarion("CNV-11917"),
                id="test_metric_kubevirt_vmi_filesystem_capacity_bytes",
            ),
            pytest.param(
                USED,
                marks=pytest.mark.polarion("CNV-11918"),
                id="test_metric_kubevirt_vmi_filesystem_used_bytes",
            ),
        ],
    )
    def test_metric_kubevirt_vmi_filesystem_capacity_used_bytes_windows(
        self,
        prometheus,
        windows_vm_for_test,
        disk_file_system_info_windows,
        capacity_or_used,
    ):
        compare_metric_file_system_values_with_vm_file_system_values(
            prometheus=prometheus,
            vm_for_test=windows_vm_for_test,
            mount_point=[*disk_file_system_info_windows][0],
            capacity_or_used=capacity_or_used,
        )


class TestVmiMemoryAvailableBytes:
    @pytest.mark.parametrize(
        "vm_for_test",
        [pytest.param("available-mem-test", marks=pytest.mark.polarion("CNV-11497"))],
        indirect=True,
    )
    def test_kubevirt_vmi_memory_available_bytes(self, prometheus, vm_for_test, vmi_memory_available_memory):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_MEMORY_AVAILABLE_BYTES.format(vm_name=vm_for_test.name),
            expected_value=vmi_memory_available_memory,
        )


@pytest.mark.usefixtures("vm_with_cpu_spec")
class TestVmResourceRequests:
    @pytest.mark.polarion("CNV-11521")
    def test_metric_kubevirt_vm_resource_requests(
        self,
        prometheus,
        cnv_vm_resource_requests_units_matrix__function__,
        vm_with_cpu_spec,
        modified_vm_cpu_requests,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_resource_requests{{'name'='{vm_with_cpu_spec.name}',"
            f"'unit'='{cnv_vm_resource_requests_units_matrix__function__}'}}",
            expected_value=str(modified_vm_cpu_requests[cnv_vm_resource_requests_units_matrix__function__]),
        )


class TestVmiStatusAddresses:
    @pytest.mark.parametrize(
        "vm_for_test", [pytest.param("vmi-status-addresses", marks=pytest.mark.polarion("CNV-11534"))], indirect=True
    )
    def test_metric_kubevirt_vmi_status_addresses(
        self,
        prometheus,
        vm_for_test,
        metric_validate_metric_labels_values_ip_labels,
        vm_virt_controller_ip_address,
        vm_ip_address,
    ):
        instance_value = metric_validate_metric_labels_values_ip_labels.get("instance").split(":")[0]
        address_value = metric_validate_metric_labels_values_ip_labels.get("address")
        assert instance_value == vm_virt_controller_ip_address, (
            f"Expected value: {vm_virt_controller_ip_address}, Actual: {instance_value}"
        )
        assert address_value == vm_ip_address, f"Expected value: {vm_ip_address}, Actual: {address_value}"


class TestVmSnapshotSucceededTimeStamp:
    @pytest.mark.parametrize(
        "vm_for_test", [pytest.param("vm-snapshot-test", marks=pytest.mark.polarion("CNV-11536"))], indirect=True
    )
    def test_metric_kubevirt_vmsnapshot_succeeded_timestamp_seconds(
        self, prometheus, vm_for_test, vm_for_test_snapshot
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmsnapshot_succeeded_timestamp_seconds{{name='{vm_for_test.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=vm_for_test_snapshot.instance.status.creationTime)),
        )


class TestVmResourceLimits:
    @pytest.mark.polarion("CNV-11601")
    def test_metric_kubevirt_vm_resource_limits(
        self, prometheus, cnv_vm_resources_limits_matrix__function__, vm_for_test_with_resource_limits
    ):
        vm_for_test_with_resource_limits_instance = (
            vm_for_test_with_resource_limits.instance.spec.template.spec.domain.resources.limits
        )
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_resource_limits{{name='{vm_for_test_with_resource_limits.name}', "
            f"resource='{cnv_vm_resources_limits_matrix__function__}'}}",
            expected_value=vm_for_test_with_resource_limits_instance.cpu
            if cnv_vm_resources_limits_matrix__function__ == "cpu"
            else str(int(bitmath.parse_string_unsafe(vm_for_test_with_resource_limits_instance.memory).bytes)),
        )


@pytest.mark.parametrize("vm_for_test", [pytest.param("memory-working-set-vm")], indirect=True)
class TestVmFreeMemoryBytes:
    @pytest.mark.polarion("CNV-11692")
    def test_metric_kubevirt_vm_container_free_memory_bytes_based_on_working_set_bytes(self, prometheus, vm_for_test):
        validate_metric_vm_container_free_memory_bytes_based_on_working_set_rss_bytes(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_container_free_memory_bytes_based_on_working_set_bytes"
            f"{{pod='{vm_for_test.vmi.virt_launcher_pod.name}'}}",
            vm=vm_for_test,
            working_set=True,
        )

    @pytest.mark.polarion("CNV-11693")
    def test_metric_kubevirt_vm_container_free_memory_bytes_based_on_rss(
        self,
        prometheus,
        vm_for_test,
    ):
        validate_metric_vm_container_free_memory_bytes_based_on_working_set_rss_bytes(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_container_free_memory_bytes_based_on_rss"
            f"{{pod='{vm_for_test.privileged_vmi.virt_launcher_pod.name}'}}",
            vm=vm_for_test,
        )


class TestKubevirtVmiNonEvictable:
    @pytest.mark.parametrize(
        "data_volume_scope_function, vm_from_template_with_existing_dv",
        [
            pytest.param(
                {
                    "dv_name": "non-evictable-dv",
                    "image": RHEL_LATEST["image_path"],
                    "storage_class": py_config["default_storage_class"],
                    "dv_size": RHEL_LATEST["dv_size"],
                    "access_modes": DataVolume.AccessMode.RWO,
                },
                {
                    "vm_name": "non-evictable-vm",
                    "template_labels": FEDORA_LATEST_LABELS,
                    "ssh": False,
                    "guest_agent": False,
                    "eviction_strategy": LIVE_MIGRATE,
                },
                marks=pytest.mark.polarion("CNV-7484"),
            ),
        ],
        indirect=True,
    )
    def test_kubevirt_vmi_non_evictable(
        self,
        prometheus,
        data_volume_scope_function,
        vm_from_template_with_existing_dv,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_vmi_non_evictable",
            expected_value="1",
        )


class TestVmSnapshotPersistentVolumeClaimLabels:
    @pytest.mark.polarion("CNV-11762")
    def test_metric_kubevirt_vmsnapshot_persistentvolumeclaim_labels(
        self,
        prometheus,
        vm_for_snapshot_for_metrics_test,
        restored_vm_using_snapshot,
        snapshot_labels_for_testing,
    ):
        expected_metric_labels_and_values(
            expected_labels_and_values=snapshot_labels_for_testing,
            values_from_prometheus=get_metric_labels_non_empty_value(
                prometheus=prometheus,
                metric_name=KUBEVIRT_VMSNAPSHOT_PERSISTENTVOLUMECLAIM_LABELS.format(
                    vm_name=vm_for_snapshot_for_metrics_test.name
                ),
            ),
        )


class TestVmDiskAllocatedSizeLinux:
    @pytest.mark.polarion("CNV-11817")
    def test_metric_kubevirt_vm_disk_allocated_size_bytes(
        self,
        prometheus,
        vm_for_vm_disk_allocation_size_test,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VM_DISK_ALLOCATED_SIZE_BYTES.format(vm_name=vm_for_vm_disk_allocation_size_test.name),
            expected_value=get_pvc_size_bytes(vm=vm_for_vm_disk_allocation_size_test),
        )


@pytest.mark.tier3
class TestVmDiskAllocatedSizeWindows:
    @pytest.mark.polarion("CNV-11916")
    def test_metric_kubevirt_vm_disk_allocated_size_bytes_windows(self, prometheus, windows_vm_for_test):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VM_DISK_ALLOCATED_SIZE_BYTES.format(vm_name=windows_vm_for_test.name),
            expected_value=get_pvc_size_bytes(vm=windows_vm_for_test),
        )


class TestVmVnicInfo:
    @pytest.mark.parametrize(
        "vnic_info_from_vm_or_vmi, query",
        [
            pytest.param(
                "vm",
                "kubevirt_vm_vnic_info{{name='{vm_name}'}}",
                marks=pytest.mark.polarion("CNV-11812"),
            ),
            pytest.param(
                "vmi",
                "kubevirt_vmi_vnic_info{{name='{vm_name}'}}",
                marks=pytest.mark.polarion("CNV-11811"),
            ),
        ],
        indirect=["vnic_info_from_vm_or_vmi"],
    )
    def test_metric_kubevirt_vm_vnic_info(self, prometheus, running_metric_vm, vnic_info_from_vm_or_vmi, query):
        validate_vnic_info(
            prometheus=prometheus,
            vnic_info_to_compare=vnic_info_from_vm_or_vmi,
            metric_name=query.format(vm_name=running_metric_vm.name),
        )


class TestVmiPhaseTransitionFromDeletion:
    @pytest.mark.parametrize(
        "initial_metric_value",
        [
            pytest.param(
                KUBEVIRT_VMI_PHASE_TRANSITION_TIME_FROM_DELETION_SECONDS_SUM_SUCCEEDED,
                marks=pytest.mark.polarion("CNV-12067"),
            )
        ],
        indirect=True,
    )
    def test_kubevirt_vmi_phase_transition_from_deletion_seconds_sum_linux(
        self, prometheus, initial_metric_value, running_metric_vm, deleted_vmi
    ):
        validate_metric_value_greater_than_initial_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_PHASE_TRANSITION_TIME_FROM_DELETION_SECONDS_SUM_SUCCEEDED,
            initial_value=initial_metric_value,
        )

    @pytest.mark.parametrize(
        "initial_metric_value",
        [
            pytest.param(
                KUBEVIRT_VMI_PHASE_TRANSITION_TIME_FROM_DELETION_SECONDS_SUM_SUCCEEDED,
                marks=(pytest.mark.polarion("CNV-12204"), pytest.mark.tier3),
            )
        ],
        indirect=True,
    )
    def test_kubevirt_vmi_phase_transition_from_deletion_seconds_sum_windows(
        self, prometheus, initial_metric_value, windows_vm_for_test, deleted_windows_vmi
    ):
        validate_metric_value_greater_than_initial_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_PHASE_TRANSITION_TIME_FROM_DELETION_SECONDS_SUM_SUCCEEDED,
            initial_value=initial_metric_value,
        )
