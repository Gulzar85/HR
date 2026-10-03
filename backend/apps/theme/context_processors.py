from .services import ThemeAssetService, ThemeService, render_css_variables


def theme(request):
    resolved = ThemeService.resolve(request)
    return {
        "theme": resolved,
        "theme_css": render_css_variables(resolved),
        "theme_logo_url": ThemeAssetService.url("logo"),
        "theme_favicon_url": ThemeAssetService.url("favicon"),
    }
