import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/ask_chat_bubble.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/gradient_kpi_card.dart';
import '../widgets/notification_bell.dart';
import '../widgets/section_card.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _data;
  Map<String, dynamic>? _charts;
  String _range = 'today';
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final results = await Future.wait([
        ApiService.get('/dashboard', query: {'range': _range}),
        ApiService.get('/dashboard/charts', query: {'range': _range}),
      ]);
      setState(() {
        _data = results[0];
        _charts = results[1];
        _error = null;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
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
          const NotificationBell(),
          const SizedBox(width: 8),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          RefreshIndicator(
            onRefresh: _refresh,
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(24),
              child: _error != null ? Text(_error!, style: const TextStyle(color: Colors.red))
                                     : _data == null ? const Center(child: CircularProgressIndicator()) : _body(),
            ),
          ),
          const AskChatBubble(),
        ],
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
        LayoutBuilder(builder: (context, constraints) {
          final pie = SectionCard(title: 'Sales by product', child: _salesByProductPie());
          final line = SectionCard(title: 'Sales over time', child: _salesOverTimeLine());
          if (constraints.maxWidth < 800) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [pie, const SizedBox(height: 16), line],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: pie),
              const SizedBox(width: 16),
              Expanded(child: line),
            ],
          );
        }),
        const SizedBox(height: 24),
        LayoutBuilder(builder: (context, constraints) {
          final cardWidth = constraints.maxWidth < 600
              ? (constraints.maxWidth - 16) / 2
              : 220.0;
          return Wrap(
            spacing: 16, runSpacing: 16,
            children: [
              for (int i = 0; i < kpis.length; i++)
                SizedBox(width: cardWidth, child: GradientKpiCard(label: kpis[i].$1, value: kpis[i].$2, gradientIndex: i)),
            ],
          );
        }),
        const SizedBox(height: 24),
        LayoutBuilder(builder: (context, constraints) {
          if (constraints.maxWidth < 600) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SectionCard(title: 'Staff performance', child: _staffTable(d)),
                const SizedBox(height: 16),
                SectionCard(title: 'Recent transactions', child: _recentTable(d)),
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: SectionCard(title: 'Staff performance', child: _staffTable(d))),
              const SizedBox(width: 16),
              Expanded(child: SectionCard(title: 'Recent transactions', child: _recentTable(d))),
            ],
          );
        }),
        const SizedBox(height: 16),
        SectionCard(title: 'Detection source breakdown', child: _sourceBars(d)),
      ],
    );
  }

  static const List<Color> _pieColors = [
    Color(0xFF8B5CF6), // violet
    Color(0xFF22D3EE), // teal
    Color(0xFFF59E0B), // amber
    Color(0xFFEC4899), // pink
    Color(0xFF10B981), // emerald
    Color(0xFF3B82F6), // blue
    Color(0xFF94A3B8), // slate (Other)
  ];

  Widget _salesByProductPie() {
    final items = ((_charts?['item_sales'] as List?) ?? const []).cast<Map>();
    if (items.isEmpty) return const SizedBox(height: 220, child: Center(child: Text('No sales yet')));

    const topN = 6;
    final top = items.take(topN).toList();
    final rest = items.skip(topN).toList();
    final restRevenue = rest.fold<double>(0, (s, r) => s + (r['revenue'] as num).toDouble());

    final slices = <({String name, double revenue, Color color})>[
      for (int i = 0; i < top.length; i++)
        (
          name: (top[i]['name'] ?? '?').toString(),
          revenue: (top[i]['revenue'] as num).toDouble(),
          color: _pieColors[i % (_pieColors.length - 1)],
        ),
      if (restRevenue > 0)
        (name: 'Other', revenue: restRevenue, color: _pieColors.last),
    ];

    final total = slices.fold<double>(0, (s, r) => s + r.revenue);
    if (total == 0) return const SizedBox(height: 220, child: Center(child: Text('No sales yet')));

    return SizedBox(
      height: 260,
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: PieChart(PieChartData(
              sectionsSpace: 2,
              centerSpaceRadius: 40,
              sections: [
                for (final s in slices)
                  PieChartSectionData(
                    value: s.revenue,
                    color: s.color,
                    title: '${(s.revenue / total * 100).toStringAsFixed(0)}%',
                    radius: 70,
                    titleStyle: const TextStyle(
                      color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700),
                  ),
              ],
            )),
          ),
          Expanded(
            flex: 2,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final s in slices)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(children: [
                      Container(width: 12, height: 12, decoration: BoxDecoration(
                        color: s.color, borderRadius: BorderRadius.circular(2))),
                      const SizedBox(width: 8),
                      Expanded(child: Text(s.name,
                        maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12))),
                      const SizedBox(width: 4),
                      Text('RM ${s.revenue.toStringAsFixed(0)}',
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                    ]),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _salesOverTimeLine() {
    final series = ((_charts?['daily_sales'] as List?) ?? const []).cast<Map>();
    if (series.isEmpty) {
      return const SizedBox(height: 220, child: Center(child: Text('No sales yet')));
    }

    final spots = <FlSpot>[
      for (int i = 0; i < series.length; i++)
        FlSpot(i.toDouble(), (series[i]['revenue'] as num).toDouble()),
    ];
    final maxY = spots.map((s) => s.y).fold<double>(0, (a, b) => a > b ? a : b);
    final primary = Theme.of(context).colorScheme.primary;

    final stride = (series.length / 6).ceil().clamp(1, series.length);

    return SizedBox(
      height: 260,
      child: LineChart(LineChartData(
        minY: 0,
        maxY: maxY == 0 ? 1 : maxY * 1.2,
        gridData: FlGridData(show: true, drawVerticalLine: false,
          getDrawingHorizontalLine: (_) => FlLine(
            color: Theme.of(context).dividerColor.withValues(alpha: 0.4), strokeWidth: 0.5)),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(sideTitles: SideTitles(
            showTitles: true, reservedSize: 48,
            getTitlesWidget: (v, _) => Text('RM ${v.toStringAsFixed(0)}',
              style: const TextStyle(fontSize: 10)),
          )),
          bottomTitles: AxisTitles(sideTitles: SideTitles(
            showTitles: true, reservedSize: 28,
            getTitlesWidget: (v, _) {
              final i = v.toInt();
              if (i < 0 || i >= series.length) return const SizedBox.shrink();
              if (i % stride != 0 && i != series.length - 1) return const SizedBox.shrink();
              final iso = (series[i]['date'] ?? '').toString();
              final label = iso.length >= 10 ? iso.substring(5) : iso; // MM-DD
              return Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(label, style: const TextStyle(fontSize: 10)),
              );
            },
          )),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            curveSmoothness: 0.2,
            color: primary,
            barWidth: 3,
            dotData: FlDotData(show: spots.length <= 14),
            belowBarData: BarAreaData(
              show: true,
              color: primary.withValues(alpha: 0.12),
            ),
          ),
        ],
      )),
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
