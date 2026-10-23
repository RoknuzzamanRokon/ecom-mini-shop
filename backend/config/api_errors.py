"""
DRF exception handling for every API view (REST_FRAMEWORK["EXCEPTION_HANDLER"]).
"""

from django.db import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# MySQL rolled the transaction back to break a lock cycle (1213), or gave up
# waiting for a lock (1205). Nothing was written, so the request can simply be
# sent again; answer 409 instead of a 500 (BUG-058).
RETRYABLE_MYSQL_ERRORS = frozenset({1205, 1213})

RETRY_MESSAGE = "Another request was changing the same records at the same time. Nothing was saved; please try again."


def exception_handler(exc, context):
    if isinstance(exc, OperationalError) and exc.args and exc.args[0] in RETRYABLE_MYSQL_ERRORS:
        return Response({"detail": RETRY_MESSAGE}, status=status.HTTP_409_CONFLICT)
    return drf_exception_handler(exc, context)
