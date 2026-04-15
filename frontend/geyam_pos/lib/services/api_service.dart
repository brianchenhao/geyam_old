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

class ApiService {
  static Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${ApiConfig.baseUrl}$path').replace(queryParameters: query);

  static Map<String, dynamic> _decode(http.Response resp) {
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static List<dynamic> _decodeList(http.Response resp) {
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body) as List<dynamic>;
  }

  // ---------- auth ----------
  static Future<Map<String, dynamic>> login(
      String username, String password) async {
    final resp = await http.post(
      _uri('/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );
    return _decode(resp);
  }

  // ---------- menu ----------
  static Future<List<dynamic>> getMenu() async {
    final resp = await http.get(_uri('/menu'));
    return _decodeList(resp);
  }

  // ---------- detect (POS scan) ----------
  // conf=0.005 because the current 2-class model has very low confidences;
  // tune up once more classes are trained.
  static Future<List<dynamic>> detect(XFile image,
      {double conf = 0.005}) async {
    final req = http.MultipartRequest('POST', _uri('/detect', {'conf': '$conf'}));
    final bytes = await image.readAsBytes();
    req.files.add(http.MultipartFile.fromBytes(
      'image',
      bytes,
      filename: image.name,
      contentType: _mediaTypeFor(image.name, 'image', 'jpeg'),
    ));
    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw ApiException(streamed.statusCode, body);
    }
    final decoded = jsonDecode(body) as Map<String, dynamic>;
    if (decoded.containsKey('error')) {
      throw ApiException(200, decoded['error'] as String);
    }
    return decoded['detections'] as List<dynamic>;
  }

  // ---------- transaction ----------
  static Future<Map<String, dynamic>> createTransaction({
    int? staffId,
    required List<Map<String, dynamic>> items,
  }) async {
    final resp = await http.post(
      _uri('/transaction'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'staff_id': staffId, 'items': items}),
    );
    return _decode(resp);
  }

  // ---------- sales ----------
  static Future<List<dynamic>> getSales({int limit = 50}) async {
    final resp = await http.get(_uri('/sales', {'limit': '$limit'}));
    return _decodeList(resp);
  }

  static Future<Map<String, dynamic>> getSalesSummary() async {
    final resp = await http.get(_uri('/sales/summary'));
    return _decode(resp);
  }

  // ---------- forecast ----------
  static Future<List<dynamic>> getForecast() async {
    final resp = await http.get(_uri('/forecast'));
    return _decodeList(resp);
  }

  // ---------- ask LLM ----------
  static Future<Map<String, dynamic>> ask(String question) async {
    final resp = await http.post(
      _uri('/ask'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'question': question}),
    );
    return _decode(resp);
  }

  // ---------- training upload ----------
  static Future<Map<String, dynamic>> trainVideo({
    required String name,
    required double price,
    required XFile video,
  }) async {
    final req = http.MultipartRequest('POST', _uri('/train/video'));
    req.fields['name'] = name;
    req.fields['price'] = price.toString();
    final bytes = await video.readAsBytes();
    req.files.add(http.MultipartFile.fromBytes(
      'video',
      bytes,
      filename: video.name,
      contentType: _mediaTypeFor(video.name, 'video', 'mp4'),
    ));
    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw ApiException(streamed.statusCode, body);
    }
    return jsonDecode(body) as Map<String, dynamic>;
  }

  // ---------- model status ----------
  static Future<Map<String, dynamic>> getModelStatus() async {
    final resp = await http.get(_uri('/model/status'));
    return _decode(resp);
  }
}
