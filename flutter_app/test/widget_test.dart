import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rooms_rental_web/main.dart';

void main() {
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

  testWidgets('viewing requests submit renter details through the API', (
    tester,
  ) async {
    final requests = <http.Request>[];
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
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Request a viewing'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Request a viewing'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).at(0), 'Guest Example');
    await tester.enterText(
      find.byType(TextFormField).at(1),
      'guest@example.com',
    );
    await tester.enterText(find.byType(TextFormField).at(2), '+2348012345678');
    await tester.tap(find.text('Send viewing request'));
    await tester.pumpAndSettle();

    final submission = requests.last;
    expect(submission.method, 'POST');
    expect(submission.headers['X-CSRFToken'], 'csrf-test-token');
    expect(jsonDecode(submission.body)['guest_name'], 'Guest Example');
    expect(
      find.textContaining('Your viewing request has been sent'),
      findsOneWidget,
    );
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
        'photos': [],
      },
    ],
  }),
  200,
  headers: {'content-type': 'application/json'},
);
