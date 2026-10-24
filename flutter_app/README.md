# Rooms Rental Web

Flutter web customer interface for the Rooms rental marketplace. It uses the
Django app at the repository root for same-origin rental APIs and leaves the
existing Django staff and owner portals in place.

For setup and deployment instructions, see the repository
[README](../README.md).

To run the Flutter checks:

```powershell
flutter pub get
flutter analyze
flutter test
flutter build web --release --base-href=/
```
