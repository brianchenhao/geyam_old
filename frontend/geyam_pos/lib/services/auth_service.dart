/// Thin shim that delegates to Session in api_service. Kept as a compatibility
/// layer for screens that still import 'auth_service'.
import 'api_service.dart';

class AuthService {
  static bool get isLoggedIn => Session.token != null;
  static bool get isOwner => Session.role == 'owner';
  static bool get isCashier => Session.role == 'cashier';
  static String? get role => Session.role;
  static int? get userId => Session.userId;

  static void clear() => Session.clear();
}
