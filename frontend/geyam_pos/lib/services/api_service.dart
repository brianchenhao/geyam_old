import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mime/mime.dart';

import '../config/api_config.dart';

MediaType _mediaTypeFor(String filename, String fallbackType, String fallbackSubtype) {
  final mime = lookupMimeType(filename);
  if (mime != null) {
    final parts = mime.split('/');
    if (parts.length == 2) return MediaType(parts[0], parts[1]);
  }
  return MediaType(fallbackType, fallbackSubtype);
}

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Holds the JWT minted by /auth/staff/login or /auth/google and the
/// claim-derived role/tenant so UI can gate owner-only screens.
class Session {
  static String? token;
  static int? tenantId;
  static int? userId;
  static String? role;
  static String? tenantHandle;

  static Map<String, String> authHeaders({bool json = true}) => {
        if (token != null) 'Authorization': 'Bearer $token',
        if (json) 'Content-Type': 'application/json',
      };

  static void clear() {
    token = null;
    tenantId = null;
    userId = null;
    role = null;
    tenantHandle = null;
  }
}

class ApiService {
  static Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${ApiConfig.baseUrl}$path').replace(queryParameters: query);

  static dynamic _decode(http.Response r) {
    if (r.statusCode >= 400) {
      throw ApiException(r.statusCode, r.body);
    }
    if (r.body.isEmpty) return null;
    return jsonDecode(r.body);
  }

  // ---------- auth ----------

  static Future<Map<String, dynamic>> staffLogin(
      String tenantHandle, String username, String pin) async {
    final r = await http.post(
      _uri('/auth/staff/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'tenant_handle': tenantHandle,
        'username': username,
        'pin': pin,
      }),
    );
    final m = _decode(r) as Map<String, dynamic>;
    Session.token = m['access_token'] as String;
    Session.tenantId = m['tenant_id'] as int;
    Session.userId = m['user_id'] as int;
    Session.role = m['role'] as String;
    Session.tenantHandle = tenantHandle;
    return m;
  }

  static Future<Map<String, dynamic>> devOwnerLogin(String tenantHandle) async {
    final r = await http.post(
      _uri('/auth/dev/owner'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'tenant_handle': tenantHandle}),
    );
    final m = _decode(r) as Map<String, dynamic>;
    Session.token = m['access_token'] as String;
    Session.tenantId = m['tenant_id'] as int;
    Session.userId = m['user_id'] as int;
    Session.role = m['role'] as String;
    Session.tenantHandle = tenantHandle;
    return m;
  }

  static Future<Map<String, dynamic>> googleLogin(String idToken) async {
    final r = await http.post(
      _uri('/auth/google'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'id_token': idToken}),
    );
    final m = _decode(r) as Map<String, dynamic>;
    Session.token = m['access_token'] as String;
    Session.tenantId = m['tenant_id'] as int;
    Session.userId = m['user_id'] as int;
    Session.role = m['role'] as String;
    return m;
  }

  // ---------- menu ----------

  static Future<List<dynamic>> listMenu() async {
    final r = await http.get(_uri('/menu'), headers: Session.authHeaders(json: false));
    return _decode(r) as List<dynamic>;
  }

  static Future<Map<String, dynamic>> createMenuItem({
    required String name,
    required double price,
    String? category,
    String? barcode,
    int stockQty = 0,
    int reorderPoint = 5,
  }) async {
    final r = await http.post(
      _uri('/menu'),
      headers: Session.authHeaders(),
      body: jsonEncode({
        'name': name,
        'price': price,
        'category': category,
        'barcode': barcode,
        'stock_qty': stockQty,
        'reorder_point': reorderPoint,
      }),
    );
    return _decode(r) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> uploadMenuVideo(int itemId, XFile video) async {
    final req = http.MultipartRequest('POST', _uri('/menu/$itemId/video'));
    req.headers['Authorization'] = 'Bearer ${Session.token}';
    req.files.add(http.MultipartFile.fromBytes(
      'file', await video.readAsBytes(),
      filename: video.name,
      contentType: _mediaTypeFor(video.name, 'video', 'mp4'),
    ));
    final s = await req.send();
    final body = await s.stream.bytesToString();
    if (s.statusCode >= 400) throw ApiException(s.statusCode, body);
    return jsonDecode(body) as Map<String, dynamic>;
  }

  // ---------- detect (POS scan) ----------

  /// Returns {items: [...], shortlists: [...], notes: [...]}
  static Future<Map<String, dynamic>> detect(XFile image) async {
    final req = http.MultipartRequest('POST', _uri('/detect'));
    req.headers['Authorization'] = 'Bearer ${Session.token}';
    req.files.add(http.MultipartFile.fromBytes(
      'file', await image.readAsBytes(),
      filename: image.name,
      contentType: _mediaTypeFor(image.name, 'image', 'jpeg'),
    ));
    final s = await req.send();
    final body = await s.stream.bytesToString();
    if (s.statusCode >= 400) throw ApiException(s.statusCode, body);
    return jsonDecode(body) as Map<String, dynamic>;
  }

  // ---------- transactions ----------

  static Future<Map<String, dynamic>> createTransaction({
    required List<Map<String, dynamic>> items,
    int? customerId,
    String paymentMethod = 'qr',
  }) async {
    final r = await http.post(
      _uri('/transaction'),
      headers: Session.authHeaders(),
      body: jsonEncode({
        'items': items,
        'customer_id': customerId,
        'payment_method': paymentMethod,
      }),
    );
    return _decode(r) as Map<String, dynamic>;
  }

  static Future<List<dynamic>> listTransactions({int limit = 50}) async {
    final r = await http.get(
      _uri('/transaction', {'limit': '$limit'}),
      headers: Session.authHeaders(json: false),
    );
    return _decode(r) as List<dynamic>;
  }

  // ---------- dashboard / forecast / ask ----------

  static Future<Map<String, dynamic>> dashboard() async {
    final r = await http.get(_uri('/dashboard'), headers: Session.authHeaders(json: false));
    return _decode(r) as Map<String, dynamic>;
  }

  static Future<List<dynamic>> forecast() async {
    final r = await http.get(_uri('/forecast'), headers: Session.authHeaders(json: false));
    return _decode(r) as List<dynamic>;
  }

  static Future<Map<String, dynamic>> ask(String question) async {
    final r = await http.post(
      _uri('/ask'),
      headers: Session.authHeaders(),
      body: jsonEncode({'question': question}),
    );
    return _decode(r) as Map<String, dynamic>;
  }

  // ---------- audit ----------

  static Future<Map<String, dynamic>> audit({int limit = 50, int offset = 0}) async {
    final r = await http.get(
      _uri('/audit', {'limit': '$limit', 'offset': '$offset'}),
      headers: Session.authHeaders(json: false),
    );
    return _decode(r) as Map<String, dynamic>;
  }
}
