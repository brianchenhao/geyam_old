/// Central route-name constants for Phase 13. Wire the actual Widget map in
/// main.dart as each screen ships — using constants here prevents typos.
class Routes {
  static const landing = '/';
  static const login = '/login';
  static const signup = '/signup';
  static const tenantPicker = '/tenant-picker';

  static const pos = '/pos';
  static const menuPicker = '/menu-picker';
  static const cartDetail = '/cart-detail';

  static const dashboard = '/dashboard';
  static const transactionsList = '/transactions';
  static const transactionDetail = '/transactions/detail';

  static const menuManager = '/menu-manager';
  static const csvPreview = '/menu-manager/csv-preview';
  static const training = '/training';

  static const inventory = '/inventory';

  static const staffManager = '/staff';
  static const settings = '/settings';
  static const auditLog = '/audit-log';
  static const reports = '/reports';
}
