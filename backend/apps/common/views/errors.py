"""Class-based error handlers. Never expose stack traces or internal details."""

from django.views.generic import TemplateView


class _ErrorView(TemplateView):
    status = 500
    title = "Error"
    message = "Something went wrong."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(status=self.status, title=self.title, message=self.message)
        return ctx

    def dispatch(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response.status_code = self.status
        response.render()  # type: ignore[attr-defined]
        return response


class BadRequestView(_ErrorView):
    template_name = "errors/error.html"
    status, title, message = 400, "Bad request", "The request could not be understood."


class PermissionDeniedView(_ErrorView):
    template_name = "errors/error.html"
    status, title, message = 403, "Forbidden", "You do not have permission to view this page."


class NotFoundView(_ErrorView):
    template_name = "errors/error.html"
    status, title, message = 404, "Not found", "The page you requested does not exist."


class ServerErrorView(_ErrorView):
    template_name = "errors/error.html"
    status, title, message = 500, "Server error", "An unexpected error occurred."


bad_request = BadRequestView.as_view()
permission_denied = PermissionDeniedView.as_view()
not_found = NotFoundView.as_view()
server_error = ServerErrorView.as_view()
