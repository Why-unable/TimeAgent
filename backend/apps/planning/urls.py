from django.urls import path

from apps.planning.adaptive_views import (
    LocalReplanApplyView,
    LocalReplanPreviewView,
    ScheduleDisruptionDetectionView,
)
from apps.planning.automation_views import AutomationPolicyDetailView, AutomationPolicyListView
from apps.planning.change_views import ScheduleChangeBatchRevertView
from apps.planning.recommendation_views import FreeTimeRecommendationView
from apps.planning.views import (
    SchedulePlanAbandonView,
    SchedulePlanApplyView,
    SchedulePlanCompareView,
    SchedulePlanEditView,
    SchedulePlanListView,
    SchedulePlanRegenerateView,
    SchedulePlanValidateView,
)

urlpatterns = [
    path("automation-policies/", AutomationPolicyListView.as_view(), name="automation-policies"),
    path(
        "automation-policies/<uuid:policy_id>/",
        AutomationPolicyDetailView.as_view(),
        name="automation-policy-detail",
    ),
    path(
        "disruptions/detect/",
        ScheduleDisruptionDetectionView.as_view(),
        name="schedule-disruption-detect",
    ),
    path(
        "plans/local-replan-preview/",
        LocalReplanPreviewView.as_view(),
        name="local-replan-preview",
    ),
    path(
        "plans/local-replan-apply/",
        LocalReplanApplyView.as_view(),
        name="local-replan-apply",
    ),
    path(
        "change-batches/<uuid:batch_id>/revert/",
        ScheduleChangeBatchRevertView.as_view(),
        name="schedule-change-batch-revert",
    ),
    path("plans/", SchedulePlanListView.as_view(), name="schedule-plans"),
    path("plans/compare/", SchedulePlanCompareView.as_view(), name="schedule-plan-compare"),
    path(
        "plans/<uuid:plan_id>/apply/",
        SchedulePlanApplyView.as_view(),
        name="schedule-plan-apply",
    ),
    path(
        "plans/<uuid:plan_id>/regenerate/",
        SchedulePlanRegenerateView.as_view(),
        name="schedule-plan-regenerate",
    ),
    path(
        "plans/<uuid:plan_id>/edit/",
        SchedulePlanEditView.as_view(),
        name="schedule-plan-edit",
    ),
    path(
        "plans/<uuid:plan_id>/validate/",
        SchedulePlanValidateView.as_view(),
        name="schedule-plan-validate",
    ),
    path(
        "plans/<uuid:plan_id>/abandon/",
        SchedulePlanAbandonView.as_view(),
        name="schedule-plan-abandon",
    ),
    path(
        "free-time-recommendations/",
        FreeTimeRecommendationView.as_view(),
        name="free-time-recommendations",
    ),
]
