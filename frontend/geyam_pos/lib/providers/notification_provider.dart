import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as ws_status;

import '../config/api_config.dart';

class AppNotification {
  final String type;
  final String message;
  final Map<String, dynamic> raw;
  final DateTime at;
  AppNotification({required this.type, required this.message, required this.raw, required this.at});
}

class NotificationProvider extends ChangeNotifier {
  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  final List<AppNotification> _items = [];
  bool _connected = false;

  List<AppNotification> get items => List.unmodifiable(_items);
  bool get connected => _connected;

  void connect(String jwt) {
    disconnect();
    final base = ApiConfig.baseUrl.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://');
    final uri = Uri.parse('$base/ws?token=$jwt');
    try {
      _channel = WebSocketChannel.connect(uri);
      _connected = true;
      notifyListeners();
      _sub = _channel!.stream.listen(
        _onMessage,
        onError: (_) => _markDisconnected(),
        onDone: _markDisconnected,
      );
    } catch (_) {
      _markDisconnected();
    }
  }

  static const _protocolTypes = {'hello', 'ack'};

  void _onMessage(dynamic raw) {
    try {
      final data = raw is String ? jsonDecode(raw) : raw;
      if (data is! Map) return;
      final type = (data['type'] ?? 'info').toString();
      if (_protocolTypes.contains(type)) return;
      final msg = _formatMessage(type, Map<String, dynamic>.from(data));
      _items.insert(0, AppNotification(
        type: type, message: msg,
        raw: Map<String, dynamic>.from(data), at: DateTime.now(),
      ));
      if (_items.length > 50) _items.removeLast();
      notifyListeners();
    } catch (_) {/* ignore malformed */}
  }

  String _formatMessage(String type, Map<String, dynamic> d) {
    switch (type) {
      case 'tx_paid':
        return 'Payment received: ${d['tx_number']} — RM ${d['total']}';
      case 'tx_autovoid':
        return 'Auto-voided stale tx ${d['tx_number']}';
      case 'low_conf':
        return 'Low-confidence detection on ${d['item'] ?? 'item'}';
      default:
        return type;
    }
  }

  void _markDisconnected() {
    _connected = false;
    notifyListeners();
  }

  void clear() {
    _items.clear();
    notifyListeners();
  }

  void disconnect() {
    _sub?.cancel();
    _sub = null;
    try { _channel?.sink.close(ws_status.normalClosure); } catch (_) {}
    _channel = null;
    if (_connected) _markDisconnected();
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
