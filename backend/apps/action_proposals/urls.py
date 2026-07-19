from django.urls import path

from apps.action_proposals.views import (
    ActionProposalDetailView,
    ActionProposalListView,
    ProposalApproveView,
    ProposalEditView,
    ProposalRejectView,
)

urlpatterns = [
    path("", ActionProposalListView.as_view(), name="action-proposal-list"),
    path("<uuid:proposal_id>/", ActionProposalDetailView.as_view(), name="action-proposal-detail"),
    path(
        "<uuid:proposal_id>/approve/",
        ProposalApproveView.as_view(),
        name="action-proposal-approve",
    ),
    path("<uuid:proposal_id>/edit/", ProposalEditView.as_view(), name="action-proposal-edit"),
    path("<uuid:proposal_id>/reject/", ProposalRejectView.as_view(), name="action-proposal-reject"),
]
