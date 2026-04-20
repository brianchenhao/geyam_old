import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../config/api_config.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiService {
  static String? _token;
  static int? tenantId;
  static String? role;

  static void setAuth({required String token, int? tenantId, String? role}) {
    _token = token;
    ApiService.tenantId = tenantId;
    ApiService.role = role;
  }

  static void clearAuth() {
    _token = null;
    tenantId = null;
    role = null;
  }

  static String? get token => _token;

  static Map<String, String> _headers({bool json = true}) {
    final h = <String, String>{};
    if (json) h['Content-Type'] = 'application/json';
    if (_token != null) h['Authorization'] = 'Bearer $_token';
    return h;
  }

  static Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${ApiConfig.baseUrl}$path').replace(queryParameters: query);

  static Future<dynamic> get(String path, {Map<String, String>? query}) async {
    final r = await http.get(_uri(path, query), headers: _headers(json: false));
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  static Future<dynamic> post(String path, {Object? body}) async {
    final r = await http.post(_uri(path), headers: _headers(),
        body: body is String ? body : jsonEncode(body ?? {}));
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  static Future<dynamic> patch(String path, {Object? body}) async {
    final r = await http.patch(_uri(path), headers: _headers(),
        body: jsonEncode(body ?? {}));
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  static Future<dynamic> delete(String path) async {
    final r = await http.delete(_uri(path), headers: _headers(json: false));
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  /// Multipart file upload. For image/video with a single field named `file`.
  static Future<dynamic> uploadBytes(String path, {
    required Uint8List bytes,
    required String filename,
    required String contentType,
    Map<String, String>? fields,
  }) async {
    final req = http.MultipartRequest('POST', _uri(path));
    if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
    if (fields != null) req.fields.addAll(fields);
    final parts = contentType.split('/');
    req.files.add(http.MultipartFile.fromBytes(
      'file', bytes, filename: filename,
      contentType: MediaType(parts[0], parts.length > 1 ? parts[1] : 'octet-stream'),
    ));
    final streamed = await req.send();
    final r = await http.Response.fromStream(streamed);
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }
}
