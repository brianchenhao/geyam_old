import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/theme_toggle.dart';
import 'audit_screen.dart';
import 'login_screen.dart';
import 'pos_screen.dart';
import 'product_upload_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? dash;
  List<Map<String, dynamic>> forecast = [];
  bool loading = true;
  String? loadError;

  final askCtrl = TextEditingController();
  String? askAnswer;
  bool asking = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      loading = true;
      loadError = null;
    });
    try {
      final results = await Future.wait([
        ApiService.dashboard(),
        ApiService.forecast(),
      ]);
      setState(() {
        dash = results[0] as Map<String, dynamic>;
        forecast = (results[1] as List<dynamic>)
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
      });
    } catch (e) {
      setState(() => loadError = '$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _ask() async {
    final q = askCtrl.text.trim();
    if (q.isEmpty) return;
    setState(() {
      asking = true;
      askAnswer = null;
    });
    try {
      final result = await ApiService.ask(q);
      setState(() => askAnswer = result['answer'] as String? ?? 'No answer');
    } catch (e) {
      setState(() => askAnswer = 'Error: $e');
    } finally {
      if (mounted) setState(() => asking = false);
    }
  }

  void _logout() {
    Session.clear();
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('GEYAM · ${Session.tenantHandle ?? "tenant ${Session.tenantId}"}'),
        actions: [
          IconButton(
            tooltip: 'POS',
            icon: const Icon(Icons.point_of_sale),
            onPressed: () => Navigator.push(context,
                MaterialPageRoute(builder: (_) => const PosScreen())),
          ),
          IconButton(
            tooltip: 'Products',
            icon: const Icon(Icons.video_call),
            onPressed: () => Navigator.push(context,
                MaterialPageRoute(builder: (_) => const ProductUploadScreen())),
          ),
          IconButton(
            tooltip: 'Audit log',
            icon: const Icon(Icons.manage_history),
            onPressed: () => Navigator.push(context,
                MaterialPageRoute(builder: (_) => const AuditScreen())),
          ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: loading ? null : _refresh,
          ),
          const ThemeToggle(),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: _logout,
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : loadError != null
              ? Center(child: Text('Failed to load: $loadError'))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _cards(),
                      const SizedBox(height: 16),
                      _section('Top items (last 7d)', _topItems()),
                      const SizedBox(height: 16),
                      _section('Per-item forecast', _forecastTable()),
                      const SizedBox(height: 16),
                      _section('Ask the AI', _askBox()),
                    ],
                  ),
                ),
    );
  }

  Widget _cards() {
    final d = dash ?? {};
    final cards = [
      _card('Revenue today', 'RM ${d['revenue_today'] ?? 0}'),
      _card('Tx today', '${d['tx_count_today'] ?? 0}'),
      _card('Revenue 7d', 'RM ${d['revenue_7d'] ?? 0}'),
      _card('Low stock', '${d['low_stock_count'] ?? 0}'),
    ];
    return LayoutBuilder(builder: (ctx, cons) {
      final wide = cons.maxWidth > 700;
      if (wide) {
        return Row(children: [
          for (final c in cards) ...[Expanded(child: c), const SizedBox(width: 12)],
        ]..removeLast());
      }
      return Column(children: [
        for (final c in cards) ...[c, const SizedBox(height: 12)],
      ]..removeLast());
    });
  }

  Widget _card(String label, String value) => Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(fontSize: 12)),
              const SizedBox(height: 8),
              Text(value,
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            ],
          ),
        ),
      );

  Widget _section(String title, Widget child) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              child,
            ],
          ),
        ),
      );

  Widget _topItems() {
    final top = (dash?['top_items_7d'] as List?) ?? [];
    if (top.isEmpty) return const Text('No paid sales in the last 7 days.');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final i in top)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              Expanded(child: Text(i['name'] as String)),
              Text('${i['units']} units'),
            ]),
          ),
      ],
    );
  }

  Widget _forecastTable() {
    if (forecast.isEmpty) return const Text('No forecast yet.');
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(columns: const [
        DataColumn(label: Text('Item')),
        DataColumn(label: Text('Daily forecast')),
        DataColumn(label: Text('Reorder point')),
        DataColumn(label: Text('EOQ')),
        DataColumn(label: Text('Anomaly')),
      ], rows: [
        for (final f in forecast)
          DataRow(cells: [
            DataCell(Text(f['name'] as String)),
            DataCell(Text('${f['daily_forecast']}')),
            DataCell(Text('${f['reorder_point']}')),
            DataCell(Text('${f['eoq']}')),
            DataCell(Text(f['is_anomaly'] == true
                ? 'z=${f['anomaly_z']} ⚠'
                : 'z=${f['anomaly_z']}')),
          ]),
      ]),
    );
  }

  Widget _askBox() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: askCtrl,
          decoration: const InputDecoration(
            hintText: 'e.g. What should I restock first?',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (_) => _ask(),
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerRight,
          child: ElevatedButton.icon(
            onPressed: asking ? null : _ask,
            icon: asking
                ? const SizedBox(
                    width: 16, height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.send),
            label: const Text('Ask'),
          ),
        ),
        if (askAnswer != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.black26,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(askAnswer!),
          ),
        ],
      ],
    );
  }
}
