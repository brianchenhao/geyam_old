import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

class ConnectivityProvider extends ChangeNotifier {
  final Connectivity _c = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _online = true;

  bool get isOnline => _online;
  bool get isOffline => !_online;

  ConnectivityProvider() {
    _init();
  }

  Future<void> _init() async {
    final initial = await _c.checkConnectivity();
    _apply(initial);
    _sub = _c.onConnectivityChanged.listen(_apply);
  }

  void _apply(List<ConnectivityResult> results) {
    final online = results.any((r) => r != ConnectivityResult.none);
    if (online != _online) {
      _online = online;
      notifyListeners();
    }
  }

  /// Throw if offline — call at the top of any mutation request.
  void guardMutation() {
    if (!_online) {
      throw const OfflineException();
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}

class OfflineException implements Exception {
  const OfflineException();
  @override
  String toString() => 'You are offline. This action is disabled until connection returns.';
}
