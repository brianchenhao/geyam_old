import 'package:flutter/foundation.dart';

import '../services/api_service.dart';

/// Local cache of /subscriptions/me. The banner watches this provider; the
/// billing screen calls [refresh] on display and after returning from the
/// Stripe Checkout / Portal flows.
class BillingProvider extends ChangeNotifier {
  String _plan = 'free';
  String _status = 'active';
  DateTime? _currentPeriodEnd;
  DateTime? _pastDueSince;
  DateTime? _suspendedAt;
  bool _hasStripeCustomer = false;
  bool _loading = false;
  String? _error;

  String get plan => _plan;
  String get status => _status;
  DateTime? get currentPeriodEnd => _currentPeriodEnd;
  DateTime? get pastDueSince => _pastDueSince;
  DateTime? get suspendedAt => _suspendedAt;
  bool get hasStripeCustomer => _hasStripeCustomer;
  bool get loading => _loading;
  String? get error => _error;

  bool get isSuspended => _status == 'suspended';
  bool get isPastDue => _status == 'past_due';
  bool get needsAttention => isSuspended || isPastDue;

  Future<void> refresh() async {
    if (ApiService.token == null || ApiService.role != 'owner') {
      _reset();
      return;
    }
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final res = await ApiService.get('/subscriptions/me');
      if (res is Map) {
        _plan = (res['plan'] ?? 'free').toString();
        _status = (res['status'] ?? 'active').toString();
        _currentPeriodEnd = _parseDate(res['current_period_end']);
        _pastDueSince = _parseDate(res['past_due_since']);
        _suspendedAt = _parseDate(res['suspended_at']);
        _hasStripeCustomer = res['has_stripe_customer'] == true;
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  void _reset() {
    _plan = 'free';
    _status = 'active';
    _currentPeriodEnd = null;
    _pastDueSince = null;
    _suspendedAt = null;
    _hasStripeCustomer = false;
    notifyListeners();
  }

  DateTime? _parseDate(dynamic v) {
    if (v is String && v.isNotEmpty) {
      try {
        return DateTime.parse(v);
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  Future<String?> startCheckout(String plan) async {
    final res = await ApiService.post('/subscriptions/checkout', body: {'plan': plan});
    return (res is Map) ? res['checkout_url']?.toString() : null;
  }

  Future<String?> openPortal() async {
    final res = await ApiService.post('/subscriptions/portal');
    return (res is Map) ? res['portal_url']?.toString() : null;
  }
}
