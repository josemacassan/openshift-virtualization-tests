"""
Storage migration cleanup tests for storage migration plans.

Tests verify the retentionPolicy field functionality, which controls whether source DataVolumes/PVCs
are kept (keepSource) or deleted (deleteSource) after successful VM storage migration.

The retentionPolicy field can be configured at:
- Namespace level for MultiNamespaceVirtualMachineStorageMigrationPlan
- Plan level (spec) for MultiNamespaceVirtualMachineStorageMigrationPlan
- Combination of namespace and plan level for MultiNamespaceVirtualMachineStorageMigrationPlan
  (namespace-level overrides plan-level when both are configured)

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_cleanup.md
"""

import pytest
from pytest_testconfig import config as py_config

from tests.storage.constants import STORAGE_CLASS_A, STORAGE_CLASS_B
from tests.storage.storage_migration.constants import (
    DELETE_SOURCE,
    KEEP_SOURCE,
    MIGRATION_MODE_COMBINED,
    MIGRATION_MODE_OFFLINE,
    MIGRATION_MODE_ONLINE,
)
from tests.storage.storage_migration.utils import (
    verify_source_dvs_deleted,
    verify_source_dvs_exist,
    verify_vm_storage_class_updated,
)


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, migration_mode",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            MIGRATION_MODE_ONLINE,
            id="online",
        ),
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            MIGRATION_MODE_OFFLINE,
            id="offline",
        ),
    ],
    indirect=["source_storage_class", "target_storage_class", "migration_mode"],
)
class TestStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0, P1)

    Parametrize:
        - migration_mode:
            - online (VM running during migration)
            - offline (VM stopped during migration)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.parametrize(
        "retention_policy_mig_plan",
        [pytest.param({}, id="default")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16297")
    @pytest.mark.usefixtures("retention_policy_mig_migration")
    def test_retention_policy_default_behavior(
        self,
        ready_retention_policy_vm,
        target_storage_class,
        source_dv_names_before_migration,
        retention_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=ready_retention_policy_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_retention_policy_vm, source_dv_names=source_dv_names_before_migration)

    @pytest.mark.parametrize(
        "retention_policy_mig_plan",
        [pytest.param({"ns_retention_policy": DELETE_SOURCE}, id="ns_delete")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16298")
    @pytest.mark.usefixtures("retention_policy_mig_migration")
    def test_namespace_level_retention_policy_delete_source(
        self,
        ready_retention_policy_vm,
        target_storage_class,
        source_dv_names_before_migration,
        retention_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=ready_retention_policy_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=ready_retention_policy_vm, source_dv_names=source_dv_names_before_migration)
        assert retention_policy_mig_plan.exists, (
            f"Migration plan {retention_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "retention_policy_mig_plan",
        [pytest.param({"spec_retention_policy": DELETE_SOURCE}, id="spec_delete")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16299")
    @pytest.mark.usefixtures("retention_policy_mig_migration")
    def test_spec_level_retention_policy_delete_source(
        self,
        ready_retention_policy_vm,
        target_storage_class,
        source_dv_names_before_migration,
        retention_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=ready_retention_policy_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=ready_retention_policy_vm, source_dv_names=source_dv_names_before_migration)
        assert retention_policy_mig_plan.exists, (
            f"Migration plan {retention_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "retention_policy_mig_plan",
        [pytest.param({"ns_retention_policy": KEEP_SOURCE}, id="ns_keep")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16301")
    @pytest.mark.usefixtures("retention_policy_mig_migration")
    def test_namespace_level_retention_policy_keep_source(
        self,
        ready_retention_policy_vm,
        target_storage_class,
        source_dv_names_before_migration,
        retention_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=ready_retention_policy_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_retention_policy_vm, source_dv_names=source_dv_names_before_migration)

    @pytest.mark.parametrize(
        "retention_policy_mig_plan",
        [pytest.param({"spec_retention_policy": KEEP_SOURCE}, id="spec_keep")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16302")
    @pytest.mark.usefixtures("retention_policy_mig_migration")
    def test_spec_level_retention_policy_keep_source(
        self,
        ready_retention_policy_vm,
        target_storage_class,
        source_dv_names_before_migration,
        retention_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=ready_retention_policy_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_retention_policy_vm, source_dv_names=source_dv_names_before_migration)


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestStorageMigrationRetentionPolicyCombinedMode:
    """
    Test retentionPolicy functionality with combined online+offline migration mode.

    Verifies retention policies when migrating both a running VM (online) and a stopped VM (offline)
    in the same plan. Covers the online+offline migration mode required by the STP for default,
    namespace-level, and plan-level retention policy scenarios.

    STP Traceability: CNV-73509 (P0, P1)

    Preconditions:
      - Running VM (online migration) with source PVC/DataVolume
      - Stopped VM (offline migration) with source PVC/DataVolume
    """

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({}, id="default")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16558")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_retention_policy_default_behavior_combined_mode(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
    ):
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs)

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"ns_retention_policy": DELETE_SOURCE}, id="ns_delete")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16559")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_namespace_level_retention_policy_delete_source_combined_mode(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
        combined_mode_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs
        )
        assert combined_mode_mig_plan.exists, (
            f"Migration plan {combined_mode_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"ns_retention_policy": KEEP_SOURCE}, id="ns_keep")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16560")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_namespace_level_retention_policy_keep_source_combined_mode(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
    ):
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs)

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"spec_retention_policy": DELETE_SOURCE}, id="spec_delete")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16561")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_spec_level_retention_policy_delete_source_combined_mode(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
        combined_mode_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs
        )
        assert combined_mode_mig_plan.exists, (
            f"Migration plan {combined_mode_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"spec_retention_policy": KEEP_SOURCE}, id="spec_keep")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16562")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_spec_level_retention_policy_keep_source_combined_mode(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
    ):
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs)


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, migration_mode",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            MIGRATION_MODE_ONLINE,
            id="online",
        ),
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            MIGRATION_MODE_OFFLINE,
            id="offline",
        ),
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            MIGRATION_MODE_COMBINED,
            id="combined",
        ),
    ],
    indirect=["source_storage_class", "target_storage_class", "migration_mode"],
)
class TestStorageMigrationCombinedRetentionPolicy:
    """
    Test combination of retentionPolicy for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0)
    Note: Namespace-level policy overrides plan-level policy for that namespace.

    Parametrize:
        - migration_mode:
            - online (both VMs running during migration)
            - offline (both VMs stopped during migration)
            - online+offline (one VM running, one VM stopped during migration)

    Preconditions:
      - Two VMs with source PVCs/DataVolumes in separate namespaces
    """

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": KEEP_SOURCE, "ns_override_retention_policy": DELETE_SOURCE},
                id="spec_keep_ns_delete",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16305")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_delete_overrides_plan_keep(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
        combined_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )
        assert combined_policy_mig_plan.exists, (
            f"Migration plan {combined_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": DELETE_SOURCE, "ns_override_retention_policy": KEEP_SOURCE},
                id="spec_delete_ns_keep",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16306")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_keep_overrides_plan_delete(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
        combined_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )
        assert combined_policy_mig_plan.exists, (
            f"Migration plan {combined_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": DELETE_SOURCE, "ns_override_retention_policy": DELETE_SOURCE},
                id="both_delete",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16307")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_and_plan_level_delete_source_retention_policy(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
        combined_policy_mig_plan,
    ):
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )
        assert combined_policy_mig_plan.exists, (
            f"Migration plan {combined_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": KEEP_SOURCE, "ns_override_retention_policy": KEEP_SOURCE},
                id="both_keep",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16308")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_and_plan_level_keep_source_retention_policy(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
    ):
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )


@pytest.mark.parametrize(
    "source_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            id="source_a",
        ),
    ],
    indirect=True,
)
class TestStorageMigrationFailureRetentionPolicy:
    """
    [NEGATIVE] Test retentionPolicy behavior when migration fails.
    Source volumes should be retained regardless of retentionPolicy setting.

    STP Traceability: CNV-73509 (P2)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.parametrize(
        "failure_mig_plan",
        [pytest.param({"retention_policy": DELETE_SOURCE}, id="delete_source")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16309")
    @pytest.mark.usefixtures("failure_mig_migration")
    def test_failed_migration_with_delete_source_policy(
        self,
        failure_test_vm,
        failure_source_dv_names,
    ):
        verify_source_dvs_exist(vm=failure_test_vm, source_dv_names=failure_source_dv_names)

    @pytest.mark.parametrize(
        "failure_mig_plan",
        [pytest.param({"retention_policy": KEEP_SOURCE}, id="keep_source")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16310")
    @pytest.mark.usefixtures("failure_mig_migration")
    def test_failed_migration_with_keep_source_policy(
        self,
        failure_test_vm,
        failure_source_dv_names,
    ):
        verify_source_dvs_exist(vm=failure_test_vm, source_dv_names=failure_source_dv_names)
