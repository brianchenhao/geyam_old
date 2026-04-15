import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../widgets/sales_chart.dart';
import '../widgets/theme_toggle.dart';
import 'login_screen.dart';
import 'product_upload_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? summary;
  List<dynamic> sales = [];
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
        ApiService.getSalesSummary(),
        ApiService.getSales(),
        ApiService.getForecast(),
      ]);
      setState(() {
        summary = results[0] as Map<String, dynamic>;
        sales = results[1] as List<dynamic>;
        forecast = (results[2] as List<dynamic>)
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
      setState(() => askAnswer = result['answer'] as String? ??
          result['error'] as String? ??
          'No answer');
    } catch (e) {
      setState(() => askAnswer = 'Error: $e');
    } finally {
      if (mounted) setState(() => asking = false);
    }
  }

  void _logout() {
    AuthService.clear();
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('GEYAM Dashboard · ${AuthService.username ?? "manager"}'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: loading ? null : _refresh,
          ),
          IconButton(
            tooltip: 'Train new product',
            icon: const Icon(Icons.video_call),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ProductUploadScreen()),
            ),
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
                      _summaryCards(),
                      const SizedBox(height: 24),
                      _section('Forecast (predicted next 7 days)',
                          SizedBox(height: 240, child: SalesChart(forecast: forecast))),
                      const SizedBox(height: 24),
                      _section('Recent sales', _salesTable()),
                      const SizedBox(height: 24),
                      _section('Ask the AI', _askBox()),
                    ],
                  ),
                ),
    );
  }

  Widget _summaryCards() {
    final s = summary ?? {};
    final topItems = (s['top_selling_items'] as List?) ?? [];
    final topName =
        topItems.isEmpty ? '—' : (topItems.first['name'] as String);
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth > 700;
        final cards = [
          _summaryCard('Total revenue',
              'RM ${(s['total_revenue'] as num? ?? 0).toStringAsFixed(2)}'),
          _summaryCard('Transactions', '${s['total_transactions'] ?? 0}'),
          _summaryCard('Top seller', topName),
        ];
        if (wide) {
          return Row(children: [
            for (final c in cards) ...[Expanded(child: c), const SizedBox(width: 12)],
          ]..removeLast());
        }
        return Column(
          children: [
            for (final c in cards) ...[c, const SizedBox(height: 12)],
          ]..removeLast(),
        );
      },
    );
  }

  Widget _summaryCard(String label, String value) {
    return Card(
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
  }

  Widget _section(String title, Widget child) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }

  Widget _salesTable() {
    if (sales.isEmpty) return const Text('No sales yet.');
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('ID')),
          DataColumn(label: Text('When')),
          DataColumn(label: Text('Items')),
          DataColumn(label: Text('Total')),
        ],
        rows: [
          for (final tx in sales)
            DataRow(cells: [
              DataCell(Text('${tx['id']}')),
              DataCell(Text(_formatDate(tx['created_at'] as String?))),
              DataCell(Text('${(tx['items'] as List).length}')),
              DataCell(Text('RM ${(tx['total'] as num).toStringAsFixed(2)}')),
            ]),
        ],
      ),
    );
  }

  String _formatDate(String? iso) {
    if (iso == null) return '—';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }

  Widget _askBox() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: askCtrl,
          decoration: const InputDecoration(
            hintText: 'e.g. Should I restock vanhouten?',
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
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
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
