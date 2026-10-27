import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

const _navy = Color(0xFF153D4C);
const _teal = Color(0xFF17607A);
const _muted = Color(0xFF64777B);
const _line = Color(0xFFDFE8E9);
const _pale = Color(0xFFF0F6F6);
const _gold = Color(0xFFFFC629);
final _naira = NumberFormat.currency(
  locale: 'en_NG',
  symbol: '₦',
  decimalDigits: 0,
);

String get _rentalProxyPrefix =>
    Uri.base.path == '/rentals' || Uri.base.path.startsWith('/rentals/')
    ? '/rentals'
    : '';

void main() {
  final path = Uri.base.path.replaceFirst(RegExp(r'/$'), '');
  runApp(
    RoomsRentalApp(landProperties: path == '/land' || path == '/rentals/land'),
  );
}

class RoomsRentalApp extends StatelessWidget {
  const RoomsRentalApp({super.key, this.landProperties = false});

  final bool landProperties;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: landProperties
          ? 'Rooms | Land and properties'
          : 'Rooms | Homes for rent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: _teal),
        scaffoldBackgroundColor: const Color(0xFFF8FAFB),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          labelStyle: const TextStyle(color: _muted),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: _line),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: _line),
          ),
        ),
      ),
      home: RentalHomePage(landProperties: landProperties),
    );
  }
}

class RentalListing {
  const RentalListing({
    required this.slug,
    required this.title,
    required this.description,
    required this.address,
    required this.city,
    required this.state,
    required this.propertyType,
    required this.bedrooms,
    required this.bathrooms,
    required this.annualRent,
    required this.monthlyRent,
    required this.transactionType,
    required this.salePrice,
    required this.photos,
    required this.videoUrl,
  });

  factory RentalListing.fromJson(Map<String, dynamic> json) => RentalListing(
    slug: json['slug']?.toString() ?? '',
    title: json['title']?.toString() ?? '',
    description: json['description']?.toString() ?? '',
    address: json['address']?.toString() ?? '',
    city: json['city']?.toString() ?? '',
    state: json['state']?.toString() ?? '',
    propertyType: json['property_type']?.toString() ?? '',
    bedrooms: (json['bedrooms'] as num?)?.toInt() ?? 0,
    bathrooms: (json['bathrooms'] as num?)?.toInt() ?? 0,
    annualRent: (json['annual_rent'] as num?)?.toInt() ?? 0,
    monthlyRent: (json['monthly_rent'] as num?)?.toInt() ?? 0,
    transactionType: json['transaction_type']?.toString() ?? 'rent',
    salePrice: (json['sale_price'] as num?)?.toInt() ?? 0,
    photos: (json['photos'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map((photo) => RentalPhoto.fromJson(photo))
        .toList(),
    videoUrl: json['video_url']?.toString() ?? '',
  );

  final String slug;
  final String title;
  final String description;
  final String address;
  final String city;
  final String state;
  final String propertyType;
  final int bedrooms;
  final int bathrooms;
  final int annualRent;
  final int monthlyRent;
  final String transactionType;
  final int salePrice;
  final List<RentalPhoto> photos;
  final String videoUrl;

  String get priceLabel => transactionType == 'sale'
      ? '${_naira.format(salePrice)} asking price'
      : '${_naira.format(monthlyRent)} / approx. month';

  String get location => [
    if (address.isNotEmpty) address,
    city,
    state,
  ].where((value) => value.isNotEmpty).join(', ');
}

class RentalPhoto {
  const RentalPhoto(this.image, this.caption);

  factory RentalPhoto.fromJson(Map<String, dynamic> json) => RentalPhoto(
    json['image']?.toString() ?? '',
    json['caption']?.toString() ?? '',
  );

  final String image;
  final String caption;
}

class RentalApiException implements Exception {
  const RentalApiException(this.message, [this.errors = const {}]);

  final String message;
  final Map<String, String> errors;
}

class RentalApi {
  RentalApi({
    http.Client? client,
    Future<bool> Function(Uri)? whatsappLauncher,
    String? proxyPrefix,
  }) : _client = client ?? http.Client(),
       _whatsappLauncher = whatsappLauncher,
       _proxyPrefix = proxyPrefix ?? _rentalProxyPrefix;

  final http.Client _client;
  final Future<bool> Function(Uri)? _whatsappLauncher;
  final String _proxyPrefix;
  String? _csrfToken;
  String? inspectionWhatsAppNumber;

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.base.resolve('$_proxyPrefix$path').replace(queryParameters: query);

  Future<Map<String, dynamic>> _decode(http.Response response) async {
    final dynamic body;
    try {
      body = jsonDecode(response.body);
    } on FormatException {
      throw const RentalApiException(
        'The rental service returned an invalid response.',
      );
    }
    if (body is! Map<String, dynamic>) {
      throw const RentalApiException(
        'The rental service returned an invalid response.',
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final rawErrors = body['errors'];
      final errors = rawErrors is Map<String, dynamic>
          ? rawErrors.map(
              (key, value) => MapEntry(
                key,
                value is List ? value.join(' ') : value.toString(),
              ),
            )
          : <String, String>{};
      final message =
          body['error']?.toString() ?? 'The request could not be completed.';
      final details = errors.values
          .where((value) => value.isNotEmpty)
          .join(' ');
      throw RentalApiException(
        details.isEmpty ? message : '$message $details',
        errors,
      );
    }
    return body;
  }

  Future<({List<RentalListing> listings, List<String> cities})> loadListings({
    String category = 'home',
    String transactionType = 'rent',
    String location = '',
    String city = '',
    String budget = '',
  }) async {
    final response = await _client.get(
      _uri('/api/public/listings/', {
        'category': category,
        'transaction_type': transactionType,
        if (location.isNotEmpty) 'location': location,
        if (city.isNotEmpty) 'city': city,
        if (budget.isNotEmpty) 'budget': budget,
      }),
    );
    final data = await _decode(response);
    _csrfToken = data['csrf_token']?.toString();
    inspectionWhatsAppNumber = data['inspection_whatsapp']?.toString();
    return (
      listings: (data['listings'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(RentalListing.fromJson)
          .toList(),
      cities: (data['cities'] as List<dynamic>? ?? const [])
          .map((city) => city.toString())
          .toList(),
    );
  }

  Future<void> _ensureCsrfToken() async {
    if (_csrfToken != null) return;
    final response = await _client.get(_uri('/api/public/csrf/'));
    final data = await _decode(response);
    _csrfToken = data['csrf_token']?.toString();
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> data,
  ) async {
    await _ensureCsrfToken();
    final response = await _client.post(
      _uri(path),
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': _csrfToken ?? '',
      },
      body: jsonEncode(data),
    );
    return _decode(response);
  }

  Future<String> requestProperty({
    required String ownerName,
    required String phone,
    required String propertyType,
    required String address,
  }) async {
    final result = await _post('/api/public/property-requests/', {
      'owner_name': ownerName,
      'phone': phone,
      'property_type': propertyType,
      'address': address,
      'terms_accepted': true,
    });
    return result['message']?.toString() ?? 'Your request was received.';
  }

  Future<String> requestInspection({
    required RentalListing listing,
    required String guestName,
    required String email,
    required String phone,
    required String preferredDate,
    required String message,
  }) async {
    final result = await _post(
      '/api/public/listings/${Uri.encodeComponent(listing.slug)}/inspection-requests/',
      {
        'guest_name': guestName,
        'email': email,
        'phone': phone,
        'preferred_date': preferredDate,
        'message': message,
      },
    );
    return result['message']?.toString() ??
        'Your viewing request was sent to Rooms.';
  }

  Uri? inspectionWhatsAppUri({
    required RentalListing listing,
    required String guestName,
    required String phone,
    required DateTime preferredDate,
    required String message,
  }) {
    final recipient = inspectionWhatsAppNumber?.replaceAll(RegExp(r'\D'), '');
    if (recipient == null || recipient.isEmpty) return null;
    final details = [
      'Inspection request',
      'Property: ${listing.title}',
      'Location: ${listing.location}',
      'Listing type: ${listing.transactionType == 'sale' ? 'For sale' : 'For rent'}',
      if (listing.propertyType.isNotEmpty)
        'Property type: ${listing.propertyType}',
      if (listing.bedrooms > 0) 'Bedrooms: ${listing.bedrooms}',
      if (listing.bathrooms > 0) 'Bathrooms: ${listing.bathrooms}',
      if (listing.transactionType == 'sale')
        'Asking price: ${_naira.format(listing.salePrice)}'
      else
        'Rent: ${_naira.format(listing.monthlyRent)} approx. per month',
      'Preferred inspection date: ${DateFormat('EEE, d MMM yyyy').format(preferredDate)}',
      'Customer: $guestName',
      'Customer phone: $phone',
      if (message.isNotEmpty) 'Message: $message',
    ].join('\n');
    return Uri.https('wa.me', '/$recipient', {'text': details});
  }

  Future<bool> launchWhatsApp(Uri uri) =>
      _whatsappLauncher?.call(uri) ??
      launchUrl(uri, webOnlyWindowName: '_blank');

  void dispose() => _client.close();
}

class RentalHomePage extends StatefulWidget {
  const RentalHomePage({super.key, this.api, this.landProperties = false});

  final RentalApi? api;
  final bool landProperties;

  @override
  State<RentalHomePage> createState() => _RentalHomePageState();
}

class _RentalHomePageState extends State<RentalHomePage> {
  final _locationController = TextEditingController();
  final _cityController = TextEditingController();
  late final RentalApi _api;
  List<RentalListing> _listings = const [];
  List<String> _cities = const [];
  String _budget = '';
  String _transactionType = 'all';
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? RentalApi();
    _loadListings();
  }

  @override
  void dispose() {
    _api.dispose();
    _locationController.dispose();
    _cityController.dispose();
    super.dispose();
  }

  Future<void> _loadListings() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await _api.loadListings(
        category: widget.landProperties ? 'land' : 'home',
        transactionType: widget.landProperties ? _transactionType : 'rent',
        location: _locationController.text.trim(),
        city: _cityController.text.trim(),
        budget: _budget,
      );
      if (mounted) {
        setState(() {
          _listings = result.listings;
          _cities = result.cities;
        });
      }
    } on RentalApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'Could not load ${widget.landProperties ? 'properties' : 'homes'}. Please try again shortly.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _showPropertyRequest() async {
    final message = await showDialog<String>(
      context: context,
      builder: (_) => _PropertyRequestDialog(api: _api),
    );
    if (message != null && mounted) _showMessage(message);
  }

  Future<void> _showInspectionRequest(RentalListing listing) async {
    final message = await showDialog<String>(
      context: context,
      builder: (_) => _InspectionDialog(api: _api, listing: listing),
    );
    if (message != null && mounted) _showMessage(message);
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(child: _buildHeader()),
          SliverPersistentHeader(
            pinned: true,
            delegate: _FixedHeaderDelegate(
              height: MediaQuery.sizeOf(context).width < 532 ? 100 : 116,
              child: _buildCategoryBar(),
            ),
          ),
          SliverToBoxAdapter(child: _buildHero()),
          SliverToBoxAdapter(child: _buildResultsHeader()),
          if (_error != null)
            SliverToBoxAdapter(child: _buildError())
          else if (_loading)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_listings.isEmpty)
            SliverToBoxAdapter(child: _buildEmptyState())
          else
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              sliver: SliverLayoutBuilder(
                builder: (context, constraints) {
                  final width = constraints.crossAxisExtent;
                  final columns = width >= 1040
                      ? 3
                      : width >= 680
                      ? 2
                      : 1;
                  return SliverGrid(
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: columns,
                      crossAxisSpacing: 18,
                      mainAxisSpacing: 18,
                      mainAxisExtent: 500,
                    ),
                    delegate: SliverChildBuilderDelegate(
                      (context, index) => _ListingCard(
                        listing: _listings[index],
                        onRequestViewing: () =>
                            _showInspectionRequest(_listings[index]),
                        onWatchVideo: _listings[index].videoUrl.isEmpty
                            ? null
                            : () => _openExternal(
                                _listings[index].videoUrl,
                              ),
                      ),
                      childCount: _listings.length,
                    ),
                  );
                },
              ),
            ),
          SliverToBoxAdapter(child: _buildInfo()),
          SliverToBoxAdapter(child: _buildFooter()),
        ],
      ),
    );
  }

  Widget _buildHeader() => Container(
    decoration: const BoxDecoration(
      color: _navy,
      border: Border(bottom: BorderSide(color: Color(0xFF244F5D))),
    ),
    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1240),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: _gold,
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.home_outlined,
                color: Color(0xFF082A55),
                size: 30,
              ),
            ),
            const SizedBox(width: 12),
            Semantics(
              label: 'Rooms',
              child: ExcludeSemantics(
                child: Text.rich(
                  const TextSpan(
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 27,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -1.1,
                    ),
                    children: [
                      TextSpan(text: 'Rooms'),
                      TextSpan(
                        text: '.',
                        style: TextStyle(color: Color(0xFFE53950)),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const Spacer(),
            Tooltip(
              message: 'Owner sign in',
              child: IconButton(
                onPressed: () => _openInternal('/accounts/login/'),
                icon: const Icon(Icons.lock_outline, size: 19),
                color: const Color(0xFFC1D5D9),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _buildCategoryBar() => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    decoration: const BoxDecoration(
      color: Colors.white,
      border: Border(bottom: BorderSide(color: _line)),
    ),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 850),
        child: Row(
          children: [
            Expanded(
              child: _RoomsCategoryTab(
                label: 'Hotels',
                icon: Icons.bed_outlined,
                onTap: () =>
                    _openExternal('https://labimbooking-production.up.railway.app/'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _RoomsCategoryTab(
                label: 'Apartment',
                icon: Icons.apartment_outlined,
                onTap: () => _openExternal(
                  'https://labimbooking-production.up.railway.app/apartment',
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(left: 8),
                child: _RoomsCategoryTab(
                  label: 'Homes',
                  icon: Icons.home_outlined,
                  selected: !widget.landProperties,
                  onTap: widget.landProperties
                      ? () => _openInternal('/')
                      : null,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _RoomsCategoryTab(
                label: 'Land/Properties',
                icon: Icons.map_outlined,
                selected: widget.landProperties,
                onTap: widget.landProperties
                    ? null
                    : () => _openInternal('/land'),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Future<void> _openExternal(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, webOnlyWindowName: '_self');
    } else if (mounted) {
      _showMessage('Unable to open that page.');
    }
  }

  Future<void> _openInternal(String path) async {
    final uri = Uri.base.resolve('$_rentalProxyPrefix$path');
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, webOnlyWindowName: '_self');
    } else if (mounted) {
      _showMessage('Unable to open that page.');
    }
  }

  Widget _buildHero() => Container(
    color: const Color(0xFFF8FAFB),
    padding: const EdgeInsets.fromLTRB(20, 42, 20, 30),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1100),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.landProperties
                  ? 'Find land and properties'
                  : 'Find your next home',
              style: TextStyle(
                color: _navy,
                fontSize: MediaQuery.sizeOf(context).width < 520 ? 30 : 42,
                height: 1.12,
                fontWeight: FontWeight.w700,
                letterSpacing: MediaQuery.sizeOf(context).width < 520
                    ? -0.7
                    : -1.5,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              widget.landProperties
                  ? 'Explore land and properties for rent or sale, reviewed by Rooms.'
                  : 'Choose from homes available for rent, reviewed by Rooms.',
              style: const TextStyle(color: _muted, fontSize: 17, height: 1.5),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: Colors.white,
                border: Border.all(color: _line),
                borderRadius: BorderRadius.circular(18),
              ),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final compact = constraints.maxWidth < 720;
                  final budgetItems = _budgetOptions();
                  final fields = [
                    TextField(
                      controller: _locationController,
                      decoration: const InputDecoration(
                        labelText: 'Location / area',
                        hintText: 'e.g. Lekki, Ibadan',
                        prefixIcon: Icon(Icons.search),
                      ),
                    ),
                    DropdownButtonFormField<String>(
                      initialValue: _cities.contains(_cityController.text)
                          ? _cityController.text
                          : '',
                      decoration: const InputDecoration(
                        labelText: 'City',
                        prefixIcon: Icon(Icons.location_city_outlined),
                      ),
                      items: [
                        const DropdownMenuItem(
                          value: '',
                          child: Text('Any city'),
                        ),
                        for (final city in _cities)
                          DropdownMenuItem(value: city, child: Text(city)),
                      ],
                      onChanged: (value) => _cityController.text = value ?? '',
                    ),
                    if (widget.landProperties)
                      DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _transactionType,
                        decoration: const InputDecoration(
                          labelText: 'Listing type',
                          prefixIcon: Icon(Icons.sell_outlined),
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: 'all',
                            child: Text('Rent or sale'),
                          ),
                          DropdownMenuItem(
                            value: 'rent',
                            child: Text('For rent'),
                          ),
                          DropdownMenuItem(
                            value: 'sale',
                            child: Text('For sale'),
                          ),
                        ],
                        onChanged: (value) => setState(() {
                          _transactionType = value ?? 'all';
                          _budget = '';
                        }),
                      ),
                    DropdownButtonFormField<String>(
                      isExpanded: true,
                      initialValue: _budget,
                      decoration: InputDecoration(
                        labelText: widget.landProperties
                            ? 'Maximum price'
                            : 'Maximum monthly rent',
                        prefixIcon: Icon(Icons.payments_outlined),
                      ),
                      items: budgetItems,
                      onChanged: (value) =>
                          setState(() => _budget = value ?? ''),
                    ),
                  ];
                  return Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      for (final field in fields)
                        SizedBox(
                          width: compact
                              ? constraints.maxWidth
                              : (constraints.maxWidth - 220) / fields.length,
                          child: field,
                        ),
                      FilledButton.icon(
                        onPressed: _loadListings,
                        icon: const Icon(Icons.search),
                        label: Text(
                          widget.landProperties
                              ? 'Search properties'
                              : 'Search homes',
                        ),
                        style: FilledButton.styleFrom(
                          minimumSize: const Size(180, 56),
                          backgroundColor: _teal,
                        ),
                      ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    ),
  );

  List<DropdownMenuItem<String>> _budgetOptions() {
    if (!widget.landProperties) {
      return const [
        DropdownMenuItem(value: '', child: Text('Any budget')),
        DropdownMenuItem(value: '30000', child: Text('Up to ₦30,000')),
        DropdownMenuItem(value: '50000', child: Text('Up to ₦50,000')),
        DropdownMenuItem(value: '100000', child: Text('Up to ₦100,000')),
        DropdownMenuItem(value: '250000', child: Text('Up to ₦250,000')),
        DropdownMenuItem(value: '500000', child: Text('Up to ₦500,000')),
      ];
    }
    if (_transactionType == 'rent') {
      return const [
        DropdownMenuItem(value: '', child: Text('Any budget')),
        DropdownMenuItem(value: '30000', child: Text('Up to ₦30,000 / month')),
        DropdownMenuItem(value: '50000', child: Text('Up to ₦50,000 / month')),
        DropdownMenuItem(
          value: '100000',
          child: Text('Up to ₦100,000 / month'),
        ),
        DropdownMenuItem(
          value: '250000',
          child: Text('Up to ₦250,000 / month'),
        ),
        DropdownMenuItem(
          value: '500000',
          child: Text('Up to ₦500,000 / month'),
        ),
      ];
    }
    const prices = [
      1000000,
      5000000,
      10000000,
      25000000,
      50000000,
      100000000,
      250000000,
      500000000,
    ];
    return [
      const DropdownMenuItem(value: '', child: Text('Any price')),
      for (final price in prices)
        DropdownMenuItem(
          value: '$price',
          child: Text('Up to ${_naira.format(price)}'),
        ),
    ];
  }

  Widget _buildResultsHeader() => Padding(
    padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1100),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.landProperties
                        ? 'Land and properties'
                        : 'Homes available for rent',
                    style: const TextStyle(
                      color: _navy,
                      fontSize: 25,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    widget.landProperties
                        ? 'Haidware-reviewed properties for rent or sale.'
                        : 'Haidware-reviewed listings. Rent is shown as an approximate monthly equivalent.',
                    style: const TextStyle(color: _muted, fontSize: 13),
                  ),
                ],
              ),
            ),
            if (!_loading)
              Chip(
                label: Text(
                  '${_listings.length} ${widget.landProperties ? 'properties' : 'homes'}',
                ),
                backgroundColor: _pale,
                side: BorderSide.none,
              ),
          ],
        ),
      ),
    ),
  );

  Widget _buildError() => Center(
    child: Container(
      constraints: const BoxConstraints(maxWidth: 700),
      margin: const EdgeInsets.symmetric(horizontal: 20),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF2F0),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: _loadListings, child: const Text('Retry')),
        ],
      ),
    ),
  );

  Widget _buildEmptyState() => Center(
    child: Container(
      constraints: const BoxConstraints(maxWidth: 550),
      margin: const EdgeInsets.fromLTRB(20, 8, 20, 28),
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        border: Border.all(color: _line),
        borderRadius: BorderRadius.circular(18),
        color: Colors.white,
      ),
      child: Column(
        children: [
          const Icon(Icons.home_work_outlined, color: _teal, size: 42),
          const SizedBox(height: 12),
          Text(
            'No reviewed ${widget.landProperties ? 'properties' : 'homes'} match your search yet',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            'Try another location or price. Only published properties are shown here.',
            textAlign: TextAlign.center,
            style: TextStyle(color: _muted, height: 1.5),
          ),
          TextButton(
            onPressed: () {
              _locationController.clear();
              _cityController.clear();
              setState(() => _budget = '');
              _loadListings();
            },
            child: const Text('Clear filters'),
          ),
        ],
      ),
    ),
  );

  Widget _buildInfo() => Container(
    padding: const EdgeInsets.fromLTRB(20, 30, 20, 35),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1100),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final cards = [
              _InfoCard(
                title: widget.landProperties
                    ? 'How Rooms reviews properties'
                    : 'How Rooms works',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _StepText(
                      widget.landProperties
                          ? 'Property owners request a land/property account.'
                          : 'Owners share the address, property type and contact number.',
                    ),
                    _StepText(
                      widget.landProperties
                          ? 'Haidware staff review owner and property details.'
                          : 'Rooms contacts the owner and visits to verify the home.',
                    ),
                    _StepText(
                      widget.landProperties
                          ? 'Approved owners submit land or property listings.'
                          : 'Rooms handles property photos and prepares listing details.',
                    ),
                    _StepText(
                      'The verified listing is reviewed before it is published.',
                    ),
                  ],
                ),
              ),
              _InfoCard(
                title: 'Own a property?',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.landProperties
                          ? 'Land and property listings use the same Rooms review portal. Request an owner account, then submit listings for Haidware staff review.'
                          : 'Send us the property address and your contact details. Rooms will arrange a visit and handle verification, photos and listing setup.',
                      style: TextStyle(color: _muted, height: 1.5),
                    ),
                    const SizedBox(height: 14),
                    FilledButton(
                      onPressed: widget.landProperties
                          ? () => _openInternal(
                              '/accounts/request-owner-account/?owner_type=land',
                            )
                          : _showPropertyRequest,
                      style: FilledButton.styleFrom(backgroundColor: _teal),
                      child: Text(
                        widget.landProperties
                            ? 'Request land/property account'
                            : 'List a home for rent',
                      ),
                    ),
                    TextButton(
                      onPressed: widget.landProperties
                          ? () => _openInternal('/')
                          : () => _openInternal(
                              '/accounts/request-owner-account/?owner_type=land',
                            ),
                      child: Text(
                        widget.landProperties
                            ? 'Browse homes for rent →'
                            : 'List land or property →',
                      ),
                    ),
                  ],
                ),
              ),
            ];
            return Wrap(
              spacing: 18,
              runSpacing: 18,
              children: [
                for (final card in cards)
                  SizedBox(
                    width: constraints.maxWidth < 700
                        ? constraints.maxWidth
                        : (constraints.maxWidth - 18) / 2,
                    child: card,
                  ),
              ],
            );
          },
        ),
      ),
    ),
  );

  Widget _buildFooter() => Container(
    padding: const EdgeInsets.all(22),
    decoration: const BoxDecoration(
      border: Border(top: BorderSide(color: _line)),
    ),
    child: const Text(
      '© Rooms. Home rental made clearer. Only Haidware-reviewed listings are displayed.',
      textAlign: TextAlign.center,
      style: TextStyle(color: _muted, fontSize: 12),
    ),
  );
}

class _RoomsCategoryTab extends StatelessWidget {
  const _RoomsCategoryTab({
    required this.label,
    required this.icon,
    this.selected = false,
    this.onTap,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: onTap != null,
    selected: selected,
    child: LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 120;
        return Material(
          color: selected ? const Color(0xFF1B6578) : const Color(0xFFF1F6F6),
          borderRadius: BorderRadius.circular(compact ? 14 : 18),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onTap,
            child: SizedBox(
              height: compact ? 72 : 88,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 8),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      icon,
                      size: compact ? 19 : 23,
                      color: selected ? Colors.white : const Color(0xFF485B60),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      label,
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      style: TextStyle(
                        color: selected
                            ? Colors.white
                            : const Color(0xFF485B60),
                        fontSize: compact ? 10 : 14,
                        height: 1.1,
                        fontWeight: selected
                            ? FontWeight.w600
                            : FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    ),
  );
}

class _FixedHeaderDelegate extends SliverPersistentHeaderDelegate {
  const _FixedHeaderDelegate({required this.height, required this.child});

  final double height;
  final Widget child;

  @override
  double get minExtent => height;

  @override
  double get maxExtent => height;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) => child;

  @override
  bool shouldRebuild(covariant _FixedHeaderDelegate oldDelegate) =>
      oldDelegate.height != height || oldDelegate.child != child;
}

class _ListingCard extends StatelessWidget {
  const _ListingCard({
    required this.listing,
    required this.onRequestViewing,
    required this.onWatchVideo,
  });

  final RentalListing listing;
  final VoidCallback onRequestViewing;
  final VoidCallback? onWatchVideo;

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    clipBehavior: Clip.antiAlias,
    color: Colors.white,
    elevation: 1,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(16),
      side: const BorderSide(color: _line),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 185,
          child: listing.photos.isEmpty
              ? const ColoredBox(
                  color: _pale,
                  child: Icon(Icons.home_outlined, color: _teal, size: 52),
                )
              : PageView.builder(
                  itemCount: listing.photos.length,
                  itemBuilder: (context, index) => Image.network(
                    listing.photos[index].image,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => const ColoredBox(
                      color: _pale,
                      child: Icon(Icons.home_outlined, color: _teal, size: 52),
                    ),
                  ),
                ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 13, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  listing.priceLabel,
                  style: const TextStyle(
                    color: _navy,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  listing.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _navy,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  listing.location,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: _muted, fontSize: 12),
                ),
                const Spacer(),
                Wrap(
                  spacing: 12,
                  children: [
                    if (listing.propertyType.isNotEmpty)
                      Text(listing.propertyType),
                    if (listing.bedrooms > 0) Text('${listing.bedrooms} bed'),
                    if (listing.bathrooms > 0)
                      Text('${listing.bathrooms} bath'),
                  ],
                ),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 5, 14, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (onWatchVideo != null)
                OutlinedButton.icon(
                  onPressed: onWatchVideo,
                  icon: const Icon(Icons.play_circle_outline),
                  label: const Text('Watch property video'),
                ),
              OutlinedButton(
                onPressed: onRequestViewing,
                child: const Text('Request Inspection'),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(minHeight: 220),
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: _line),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            color: _navy,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 12),
        child,
      ],
    ),
  );
}

class _StepText extends StatelessWidget {
  const _StepText(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('•  ', style: TextStyle(color: _teal)),
        Expanded(
          child: Text(text, style: const TextStyle(color: _muted)),
        ),
      ],
    ),
  );
}

class _PropertyRequestDialog extends StatefulWidget {
  const _PropertyRequestDialog({required this.api});

  final RentalApi api;

  @override
  State<_PropertyRequestDialog> createState() => _PropertyRequestDialogState();
}

class _PropertyRequestDialogState extends State<_PropertyRequestDialog> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _address = TextEditingController();
  String _propertyType = 'house';
  bool _termsAccepted = false;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _address.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || !_termsAccepted) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final message = await widget.api.requestProperty(
        ownerName: _name.text.trim(),
        phone: _phone.text.trim(),
        propertyType: _propertyType,
        address: _address.text.trim(),
      );
      if (mounted) Navigator.pop(context, message);
    } on RentalApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error = 'Could not send your request. Please try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('List a home for rent'),
    content: SizedBox(
      width: 520,
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Share the property details. Rooms will contact you to arrange an in-person verification visit.',
                style: TextStyle(color: _muted),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Your name'),
                validator: _required,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'Phone number'),
                validator: _required,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _propertyType,
                decoration: const InputDecoration(
                  labelText: 'Type of property for rent',
                ),
                items: const [
                  DropdownMenuItem(value: 'house', child: Text('House')),
                  DropdownMenuItem(
                    value: 'apartment',
                    child: Text('Apartment / flat'),
                  ),
                  DropdownMenuItem(value: 'duplex', child: Text('Duplex')),
                  DropdownMenuItem(value: 'bungalow', child: Text('Bungalow')),
                  DropdownMenuItem(
                    value: 'room',
                    child: Text('Room / self-contained'),
                  ),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (value) =>
                    setState(() => _propertyType = value ?? 'house'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _address,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Full property address',
                  hintText: 'Street, area, city and state',
                ),
                validator: _required,
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _termsAccepted,
                onChanged: (value) =>
                    setState(() => _termsAccepted = value ?? false),
                title: const Text(
                  'I own or am authorized to represent this property, it is available for rent, and I agree Rooms may contact me and visit to verify it. I understand this does not guarantee publication.',
                  style: TextStyle(fontSize: 12),
                ),
                controlAffinity: ListTileControlAffinity.leading,
              ),
              if (!_termsAccepted && _error == 'Accept the verification terms.')
                const Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Accept the verification terms.',
                    style: TextStyle(color: Colors.red, fontSize: 12),
                  ),
                ),
              if (_error != null && _error != 'Accept the verification terms.')
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    _error!,
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: _submitting ? null : () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _submitting
            ? null
            : () {
                if (!_termsAccepted) {
                  setState(() => _error = 'Accept the verification terms.');
                  return;
                }
                _submit();
              },
        child: Text(_submitting ? 'Sending…' : 'Send request'),
      ),
    ],
  );
}

class _InspectionDialog extends StatefulWidget {
  const _InspectionDialog({required this.api, required this.listing});

  final RentalApi api;
  final RentalListing listing;

  @override
  State<_InspectionDialog> createState() => _InspectionDialogState();
}

class _InspectionDialogState extends State<_InspectionDialog> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _date = TextEditingController();
  final _message = TextEditingController();
  DateTime? _preferredDate;
  Uri? _savedWhatsAppUri;
  bool _requestSaved = false;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _phone.dispose();
    _date.dispose();
    _message.dispose();
    super.dispose();
  }

  Future<void> _selectDate() async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final selected = await showDatePicker(
      context: context,
      initialDate: _preferredDate ?? today,
      firstDate: today,
      lastDate: DateTime(today.year + 2, today.month, today.day),
    );
    if (selected == null || !mounted) return;
    setState(() {
      _preferredDate = selected;
      _date.text = DateFormat('EEE, d MMM yyyy').format(selected);
    });
  }

  Future<void> _openWhatsApp() async {
    final uri = _savedWhatsAppUri;
    if (uri == null) return;
    try {
      final opened = await widget.api.launchWhatsApp(uri);
      if (opened && mounted) {
        Navigator.pop(
          context,
          'Inspection request saved. Review and send the prepared WhatsApp message.',
        );
      } else if (mounted) {
        setState(() => _error = 'WhatsApp did not open. Please try again.');
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _error = 'WhatsApp could not be opened. Please try again.',
        );
      }
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final result = await widget.api.requestInspection(
        listing: widget.listing,
        guestName: _name.text.trim(),
        email: _email.text.trim(),
        phone: _phone.text.trim(),
        preferredDate: DateFormat('yyyy-MM-dd').format(_preferredDate!),
        message: _message.text.trim(),
      );
      _requestSaved = true;
      _savedWhatsAppUri = widget.api.inspectionWhatsAppUri(
        listing: widget.listing,
        guestName: _name.text.trim(),
        phone: _phone.text.trim(),
        preferredDate: _preferredDate!,
        message: _message.text.trim(),
      );
      if (_savedWhatsAppUri == null) {
        if (mounted) {
          setState(
            () => _error =
                '$result The WhatsApp contact number is not configured. Please contact Rooms.',
          );
        }
        return;
      }
      await _openWhatsApp();
    } on RentalApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error = _savedWhatsAppUri == null
              ? 'Could not save your request. Please try again.'
              : 'Your request was saved, but WhatsApp could not be opened. Try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Request Inspection'),
    content: SizedBox(
      width: 520,
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${widget.listing.title} · ${widget.listing.city}, ${widget.listing.state}',
                style: const TextStyle(color: _muted),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Full name'),
                validator: _required,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Email address'),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Enter your email address.';
                  }
                  if (!value.contains('@')) {
                    return 'Enter a valid email address.';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Phone / WhatsApp',
                ),
                validator: _required,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _date,
                readOnly: true,
                onTap: _selectDate,
                decoration: const InputDecoration(
                  labelText: 'Preferred inspection date',
                  hintText: 'Select a date',
                  suffixIcon: Icon(Icons.calendar_today_outlined),
                ),
                validator: (_) => _preferredDate == null
                    ? 'Select an inspection date.'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _message,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Message (optional)',
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: _submitting ? null : () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _submitting
            ? null
            : !_requestSaved
            ? _submit
            : _savedWhatsAppUri == null
            ? null
            : _openWhatsApp,
        child: Text(
          _submitting
              ? 'Sending…'
              : !_requestSaved
              ? 'Send Request'
              : _savedWhatsAppUri == null
              ? 'Request Saved'
              : 'Open WhatsApp',
        ),
      ),
    ],
  );
}

String? _required(String? value) =>
    value == null || value.trim().isEmpty ? 'This field is required.' : null;
