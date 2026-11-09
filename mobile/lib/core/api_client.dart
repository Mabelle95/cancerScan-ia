import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// L'appareil n'a pas pu joindre le serveur : la saisie continue hors ligne.
class OfflineException implements Exception {
  const OfflineException();
  @override
  String toString() => 'Serveur injoignable';
}

class ApiException implements Exception {
  ApiException(this.status, this.message);
  final int status;
  final String message;
  bool get isUnauthorized => status == 401;
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl, http.Client? client, this.timeout = const Duration(seconds: 20)})
      : _http = client ?? http.Client();

  String baseUrl;
  String? token;
  final http.Client _http;
  final Duration timeout;

  Future<dynamic> _send(String method, String path, {Object? body, Map<String, String>? query}) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: (query?.isEmpty ?? true) ? null : query);
    final headers = {
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
    final http.Response res;
    try {
      final req = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) req.body = jsonEncode(body);
      res = await http.Response.fromStream(await _http.send(req).timeout(timeout));
    } on SocketException {
      throw const OfflineException();
    } on TimeoutException {
      throw const OfflineException();
    } on http.ClientException {
      throw const OfflineException();
    }
    final decoded = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _message(decoded, res.statusCode));
    return decoded;
  }

  static String _message(dynamic body, int status) {
    final detail = body is Map ? body['detail'] : null;
    if (detail is String) return detail;
    if (detail is List) {
      return detail.map((d) => (d is Map ? d['msg'] as String? : null)?.replaceFirst('Value error, ', '') ?? 'Donnée invalide').join(' · ');
    }
    if (status == 401) return 'Session expirée : reconnectez-vous';
    return status >= 500 ? 'Erreur du serveur, réessayez plus tard' : 'Erreur $status';
  }

  Future<Map<String, dynamic>> login(String email, String password) async =>
      (await _send('POST', '/auth/login', body: {'email': email, 'password': password})) as Map<String, dynamic>;

  Future<Map<String, dynamic>> me() async => (await _send('GET', '/auth/me')) as Map<String, dynamic>;

  Future<List<dynamic>> forms() async => (await _send('GET', '/forms')) as List<dynamic>;

  Future<List<dynamic>> searchPatients(String q) async =>
      (await _send('GET', '/patients', query: q.isEmpty ? null : {'q': q})) as List<dynamic>;

  Future<List<dynamic>> patientScreenings(String patientId) async =>
      (await _send('GET', '/patients/$patientId/screenings')) as List<dynamic>;

  Future<Map<String, dynamic>> screening(String id) async =>
      (await _send('GET', '/screenings/$id')) as Map<String, dynamic>;

  Future<Map<String, dynamic>> sync(Map<String, Object?> batch) async =>
      (await _send('POST', '/sync', body: batch)) as Map<String, dynamic>;

  Future<void> reportError(Map<String, Object?> report) async => _send('POST', '/client-errors', body: report);
}
