import 'video_fullscreen_stub.dart'
    if (dart.library.js_interop) 'video_fullscreen_web.dart' as platform;

Future<void> enterVideoFullscreen() => platform.enterVideoFullscreen();

Future<void> exitVideoFullscreen() => platform.exitVideoFullscreen();
