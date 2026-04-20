import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/gradient_kpi_card.dart';
import '../widgets/section_card.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _data;
  String _range = 'today';
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final d = await ApiService.get('/dashboard', query: {'range': _range});
      setState(() { _data = d; _error = null; });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        actions: [
          for (final r in const ['today', '7d', '30d'])
            TextButton(
              onPressed: () { setState(() => _range = r); _refresh(); },
              child: Text(r, style: TextStyle(
                fontWeight: _range == r ? FontWeight.w700 : FontWeight.w400,
                color: _range == r ? Theme.of(context).colorScheme.primary : null,
              )),
            ),
          const SizedBox(width: 16),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: _error != null ? Text(_error!, style: const TextStyle(color: Colors.red))
                                 : _data == null ? const Center(child: CircularProgressIndicator()) : _body(),
        ),
      ),
    );
  }

  Widget _body() {
    final d = _data!;
    final kpis = [
      ('Revenue', 'RM ${d['revenue']}'),
      ('Transactions', '${d['tx_count']}'),
      ('Avg basket', 'RM ${d['avg_basket']}'),
      ('Top item', (d['top_item'] ?? '—').toString()),
      ('Low stock', '${(d['low_stock'] as List).length}'),
      ('Anomaly z', '${d['anomaly_z']}'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 16, runSpacing: 16,
          children: [
            for (int i = 0; i < kpis.length; i++)
              SizedBox(width: 220, child: GradientKpiCard(label: kpis[i].$1, value: kpis[i].$2, gradientIndex: i)),
          ],
        ),
        const SizedBox(height: 24),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: SectionCard(title: 'Staff performance', child: _staffTable(d))),
            const SizedBox(width: 16),
            Expanded(child: SectionCard(title: 'Recent transactions', child: _recentTable(d))),
          ],
        ),
        const SizedBox(height: 16),
        SectionCard(title: 'Detection source breakdown', child: _sourceBars(d)),
      ],
    );
  }

  Widget _staffTable(Map<String, dynamic> d) {
    final rows = (d['staff_performance'] as List);
    if (rows.isEmpty) return const Text('No sales yet');
    return Column(
      children: [
        for (final s in rows) Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(children: [
            Expanded(flex: 3, child: Text(s['username'] ?? '?')),
            Expanded(child: Text('${s['tx_count']} tx', textAlign: TextAlign.end)),
            Expanded(child: Text('RM ${s['revenue']}', textAlign: TextAlign.end)),
          ]),
        ),
      ],
    );
  }

  Widget _recentTable(Map<String, dynamic> d) {
    final rows = (d['recent_transactions'] as List);
    if (rows.isEmpty) return const Text('No transactions');
    return Column(
      children: [
        for (final t in rows) Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(children: [
            Expanded(flex: 3, child: Text(t['tx_number'])),
            Expanded(child: Text('RM ${t['total']}', textAlign: TextAlign.end)),
          ]),
        ),
      ],
    );
  }

  Widget _sourceBars(Map<String, dynamic> d) {
    final breakdown = (d['source_breakdown'] as Map).cast<String, dynamic>();
    if (breakdown.isEmpty) return const Text('No detections yet');
    final entries = breakdown.entries.toList();
    final maxY = entries.map((e) => (e.value as num).toDouble()).reduce((a, b) => a > b ? a : b);
    return SizedBox(
      height: 200,
      child: BarChart(BarChartData(
        maxY: maxY.toDouble() * 1.2,
        barGroups: [
          for (int i = 0; i < entries.length; i++)
            BarChartGroupData(x: i, barRods: [
              BarChartRodData(
                toY: (entries[i].value as num).toDouble(),
                color: Theme.of(context).colorScheme.primary,
                width: 24,
                borderRadius: BorderRadius.circular(4),
              ),
            ]),
        ],
        titlesData: FlTitlesData(
          leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          bottomTitles: AxisTitles(sideTitles: SideTitles(
            showTitles: true,
            getTitlesWidget: (v, _) => Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(entries[v.toInt()].key, style: const TextStyle(fontSize: 11)),
            ),
          )),
        ),
        gridData: const FlGridData(show: false),
        borderData: FlBorderData(show: false),
      )),
    );
  }
}
