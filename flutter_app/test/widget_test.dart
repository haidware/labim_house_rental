import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rooms_rental_web/main.dart';

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
      await tester.scrollUntilVisible(
        find.text('Verified family home'),
        500,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(find.text('Verified family home'), findsOneWidget);
      expect(find.text('₦100,000 / approx. month'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

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
                        'Your viewing request has been sent to Rooms. Our team will contact you.',
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
    await tester.tap(find.text('Send Request'));
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
    expect(whatsappUris.single.path, '/2348127499576');
    expect(
      whatsappUris.single.queryParameters['text'],
      contains('Property: Verified family home'),
    );
    expect(
      whatsappUris.single.queryParameters['text'],
      contains('Preferred inspection date:'),
    );
    expect(find.textContaining('Inspection request saved'), findsOneWidget);
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
    'inspection_whatsapp': '+2348127499576',
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
        'photos': [],
      },
    ],
  }),
  200,
  headers: {'content-type': 'application/json'},
);

http.Response _landListingResponse() => http.Response(
  jsonEncode({
    'csrf_token': 'csrf-test-token',
    'inspection_whatsapp': '+2348127499576',
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
        'photos': [],
      },
    ],
  }),
  200,
  headers: {'content-type': 'application/json'},
);
