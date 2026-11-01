"""
/api/admin/rules/: the Console Rules page. GET needs 'rules.view' (or
'rules.manage'); PATCH needs 'rules.manage'.
"""
from rest_framework import status
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.utils import get_client_ip
from rbac.services import has_user_permission
from .services import RuleError, RuleService, StaleRuleError

VIEW_PERMISSION = "rules.view"
MANAGE_PERMISSION = "rules.manage"


class CanUseRules(BasePermission):
    message = "You do not have permission to see the business rules ('rules.view' required)."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return has_user_permission(request.user, VIEW_PERMISSION) or has_user_permission(
                request.user, MANAGE_PERMISSION
            )
        self.message = "You do not have permission to change the business rules ('rules.manage' required)."
        return has_user_permission(request.user, MANAGE_PERMISSION)


class RulesView(APIView):
    permission_classes = [IsAuthenticated, CanUseRules]

    @staticmethod
    def _payload(request) -> dict:
        return {**RuleService.snapshot(), "can_manage": has_user_permission(request.user, MANAGE_PERMISSION)}

    def get(self, request):
        return Response(self._payload(request))

    def patch(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        try:
            changed = RuleService.update(
                data.get("changes"), data.get("reason"), actor=request.user, ip_address=get_client_ip(request)
            )
        except StaleRuleError as exc:
            return Response(
                {
                    "detail": "Someone changed these rules after you opened the page. Reload to see their values.",
                    "current": exc.current,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except RuleError as exc:
            return Response(
                {"detail": next(iter(exc.errors.values())), "errors": exc.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({**self._payload(request), "changed": changed})
