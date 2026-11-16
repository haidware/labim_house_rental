import 'package:web/web.dart' as web;

class WhatsAppWindow {
  WhatsAppWindow(this._window);

  final web.Window _window;

  bool get closed => _window.closed;

  void navigate(String uri) {
    _window.location.href = uri;
  }
}

WhatsAppWindow? openWhatsAppWindow() {
  final window = web.window.open('about:blank', '_blank');
  if (window == null) return null;
  window.opener = null;
  return WhatsAppWindow(window);
}
