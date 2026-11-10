import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rooms_rental_web/main.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

class _TestVideoPlayerPlatform extends VideoPlayerPlatform {
  final Map<int, StreamController<VideoEvent>> _streams = {};
  int _nextPlayerId = 0;

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    final playerId = _nextPlayerId++;
    final events = StreamController<VideoEvent>();
    _streams[playerId] = events;
    events.add(
      VideoEvent(
        eventType: VideoEventType.initialized,
        duration: const Duration(seconds: 30),
        size: const Size(1920, 1080),
      ),
    );
    return playerId;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) => _streams[playerId]!.stream;

  @override
  Future<void> setLooping(int playerId, bool looping) async {}

  @override
  Future<void> setVolume(int playerId, double volume) async {}

  @override
  Future<void> setPlaybackSpeed(int playerId, double speed) async {}

  @override
  Future<void> play(int playerId) async {}

  @override
  Future<void> pause(int playerId) async {}

  @override
  Future<Duration> getPosition(int playerId) async => Duration.zero;

  @override
  Future<void> seekTo(int playerId, Duration position) async {}

  @override
  Widget buildView(int playerId) => const SizedBox.shrink();

  @override
  Future<void> dispose(int playerId) async {
    final events = _streams.remove(playerId);
    if (events != null) await events.close();
  }

  Future<void> disposeStreams() async {
    for (final stream in _streams.values) {
      await stream.close();
    }
    _streams.clear();
  }
}

void main() {
  test(
    'proxy mode prefixes rental API requests with its same-origin path',
    () async {
      final requests = <http.Request>[];
      final api = RentalApi(
        proxyPrefix: '/rentals',
        client: MockClient((request) async {
          requests.add(request);
          return _listingResponse();
        }),
      );

      await api.loadListings();

      expect(requests.single.url.path, '/rentals/api/public/listings/');
    },
  );

  testWidgets(
    'rental homepage matches Rooms categories and displays live data',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        MaterialApp(
          home: RentalHomePage(api: RentalApi(client: _mockClient())),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Rooms.'), findsOneWidget);
      expect(find.text('Hotels'), findsOneWidget);
      expect(find.text('Apartment'), findsOneWidget);
      expect(find.text('Homes'), findsOneWidget);
      expect(find.text('Land/Properties'), findsOneWidget);
      expect(find.byIcon(Icons.bed_outlined), findsWidgets);
      expect(find.byIcon(Icons.apartment_outlined), findsWidgets);
      expect(find.byIcon(Icons.home_outlined), findsWidgets);
      expect(find.byIcon(Icons.map_outlined), findsWidgets);
      expect(
        tester.getTopLeft(find.byIcon(Icons.bed_outlined).last).dy,
        tester.getTopLeft(find.byIcon(Icons.home_outlined).last).dy,
      );
      expect(find.text('Find your next home'), findsOneWidget);
      final listHomeButton = find.text('List a home for rent');
      expect(listHomeButton, findsOneWidget);
      expect(tester.getTopLeft(listHomeButton).dy, lessThan(844));
      expect(find.text('Own a property?'), findsNothing);
      await tester.scrollUntilVisible(
        find.text('Verified family home'),
        500,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(find.byType(PageView).first);
      await tester.pumpAndSettle();
      expect(find.text('Verified family home'), findsOneWidget);
      expect(find.text('₦100,000 / approx. month'), findsOneWidget);
      expect(find.byTooltip('Play property video'), findsOneWidget);
      expect(find.text('1/3'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('rental gallery places video before photos and plays inline', (
    tester,
  ) async {
    final previousPlatform = VideoPlayerPlatform.instance;
    final platform = _TestVideoPlayerPlatform();
    VideoPlayerPlatform.instance = platform;
    addTearDown(() async {
      VideoPlayerPlatform.instance = previousPlatform;
      await platform.disposeStreams();
    });
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(home: RentalHomePage(api: RentalApi(client: _mockClient()))),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Verified family home'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.byType(PageView).first);
    await tester.pumpAndSettle();

    expect(find.text('1/3'), findsOneWidget);
    await tester.drag(find.byType(PageView).first, const Offset(-250, 0));
    await tester.pumpAndSettle();
    expect(find.text('2/3'), findsOneWidget);
    await tester.drag(find.byType(PageView).first, const Offset(250, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Play property video'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Expand video'), findsOneWidget);
    await tester.tap(find.byTooltip('Expand video'));
    await tester.pumpAndSettle();
    expect(find.text('Verified family home'), findsWidgets);
    expect(find.byTooltip('Close full-screen video'), findsOneWidget);
    await tester.tap(find.byTooltip('Close full-screen video'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('land tab shows published property sale listings', (
    tester,
  ) async {
    final listingRequests = <http.Request>[];
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: RentalHomePage(
          landProperties: true,
          api: RentalApi(
            client: MockClient((request) async {
              listingRequests.add(request);
              return _landListingResponse();
            }),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(listingRequests.single.url.queryParameters['category'], 'land');
    expect(
      listingRequests.single.url.queryParameters['transaction_type'],
      'all',
    );
    expect(find.text('Find land and properties'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Lekki plot'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(find.text('₦9,000,000 asking price'), findsOneWidget);
    expect(find.text('Request Inspection'), findsOneWidget);
    expect(find.byTooltip('Play property video'), findsOneWidget);
    expect(find.text('1/2'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('inspection requests save and open WhatsApp with details', (
    tester,
  ) async {
    final requests = <http.Request>[];
    final whatsappUris = <Uri>[];
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: RentalHomePage(
          api: RentalApi(
            client: MockClient((request) async {
              requests.add(request);
              if (request.url.path == '/api/public/listings/') {
                return _listingResponse();
              }
              if (request.url.path.endsWith('/inspection-requests/')) {
                return http.Response(
                  jsonEncode({
                    'message':
                        'Your inspection request was saved. Review and send it to the landlord.',
                    'whatsapp_number': '+2348099999999',
                  }),
                  201,
                  headers: {'content-type': 'application/json'},
                );
              }
              return http.Response('{}', 404);
            }),
            whatsappLauncher: (uri) async {
              whatsappUris.add(uri);
              return true;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Request Inspection'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Request Inspection'));
    await tester.pumpAndSettle();
    expect(
      find.textContaining('You must tap Send in WhatsApp'),
      findsOneWidget,
    );

    await tester.enterText(find.byType(TextFormField).at(0), 'Guest Example');
    await tester.enterText(
      find.byType(TextFormField).at(1),
      'guest@example.com',
    );
    await tester.enterText(find.byType(TextFormField).at(2), '+2348012345678');
    await tester.tap(find.byIcon(Icons.calendar_today_outlined));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue to WhatsApp'));
    await tester.pumpAndSettle();

    final submission = requests.last;
    expect(submission.method, 'POST');
    expect(submission.headers['X-CSRFToken'], 'csrf-test-token');
    expect(jsonDecode(submission.body)['guest_name'], 'Guest Example');
    expect(
      jsonDecode(submission.body)['preferred_date'],
      matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')),
    );
    expect(whatsappUris, hasLength(1));
    expect(whatsappUris.single.host, 'wa.me');
    expect(whatsappUris.single.path, '/2348099999999');
    expect(
      whatsappUris.single.queryParameters['text'],
      contains('Property: Verified family home'),
    );
    expect(
      whatsappUris.single.queryParameters['text'],
      contains('Preferred inspection date:'),
    );
    expect(
      whatsappUris.single.queryParameters['text'],
      contains('Customer email: guest@example.com'),
    );
    expect(
      whatsappUris.single.queryParameters['text'],
      isNot(contains('https://')),
    );
    expect(find.textContaining('inspection request was saved'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

MockClient _mockClient() => MockClient((request) async {
  if (request.url.path == '/api/public/listings/') return _listingResponse();
  return http.Response('{}', 404);
});

http.Response _listingResponse() => http.Response(
  jsonEncode({
    'csrf_token': 'csrf-test-token',
    'cities': ['Lagos'],
    'listing_count': 1,
    'listings': [
      {
        'id': 'listing-1',
        'slug': 'verified-family-home',
        'title': 'Verified family home',
        'description': 'A verified home.',
        'address': '12 Test Street',
        'city': 'Lagos',
        'state': 'Lagos',
        'property_type': 'House',
        'bedrooms': 3,
        'bathrooms': 2,
        'annual_rent': 1200000,
        'monthly_rent': 100000,
        'video_url': 'https://storage.example/house.mp4',
        'photos': [
          {'image': 'https://storage.example/house-front.jpg'},
          {'image': 'https://storage.example/house-kitchen.jpg'},
        ],
      },
    ],
  }),
  200,
  headers: {'content-type': 'application/json'},
);

http.Response _landListingResponse() => http.Response(
  jsonEncode({
    'csrf_token': 'csrf-test-token',
    'cities': ['Lagos'],
    'listing_count': 1,
    'listings': [
      {
        'id': 'land-1',
        'slug': 'lekki-land',
        'title': 'Lekki plot',
        'description': 'Verified residential land.',
        'address': 'Lekki Phase 1',
        'city': 'Lagos',
        'state': 'Lagos',
        'category': 'land',
        'transaction_type': 'sale',
        'property_type': 'Residential land',
        'bedrooms': 0,
        'bathrooms': 0,
        'annual_rent': 0,
        'sale_price': 9000000,
        'video_url': 'https://storage.example/land.mp4',
        'photos': [
          {'image': 'https://storage.example/land-boundary.jpg'},
        ],
      },
    ],
  }),
  200,
  headers: {'content-type': 'application/json'},
);
