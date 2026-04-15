/// Holds the currently-logged-in user. In-memory only — does not survive app
/// restart. Good enough for the MVP; revisit when sessions/JWT land.
class AuthService {
  static int? userId;
  static String? username;
  static String? role;

  static bool get isLoggedIn => userId != null;
  static bool get isManager => role == 'manager';
  static bool get isStaff => role == 'staff';

  static void setUser(Map<String, dynamic> user) {
    userId = user['user_id'] as int?;
    username = user['username'] as String?;
    role = user['role'] as String?;
  }

  static void clear() {
    userId = null;
    username = null;
    role = null;
  }
}
