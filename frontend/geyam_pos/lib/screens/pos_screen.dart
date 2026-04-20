import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/confidence_badge.dart';
import '../widgets/section_card.dart';

class PosScreen extends StatefulWidget {
  const PosScreen({super.key});

  @override
  State<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends State<PosScreen> {
  final _picker = ImagePicker();
  Uint8List? _lastImage;
  List<dynamic> _detected = [];
  final List<Map<String, dynamic>> _cart = [];
  String? _error;
  bool _busy = false;

  Future<void> _snap() async {
    final x = await _picker.pickImage(source: ImageSource.camera, imageQuality: 80);
    if (x == null) return;
    final bytes = await x.readAsBytes();
    setState(() { _lastImage = bytes; _busy = true; _error = null; });
    try {
      final r = await ApiService.uploadBytes(
        '/detect', bytes: bytes, filename: 'snap.jpg', contentType: 'image/jpeg',
      );
      setState(() => _detected = r['items']);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _add(Map<String, dynamic> item) {
    setState(() {
      final existing = _cart.indexWhere((x) => x['menu_item_id'] == item['menu_item_id']);
      if (existing >= 0) {
        _cart[existing]['quantity'] = (_cart[existing]['quantity'] ?? 1) + 1;
      } else {
        _cart.add({
          'menu_item_id': item['menu_item_id'],
          'name': item['name'],
          'price': item['price'],
          'quantity': 1,
          'source': item['source'],
          'confidence': item['confidence'],
        });
      }
    });
  }

  Future<void> _checkout() async {
    if (_cart.isEmpty) return;
    try {
      final tx = await ApiService.post('/transaction', body: {
        'items': [
          for (final c in _cart)
            {
              'menu_item_id': c['menu_item_id'],
              'quantity': c['quantity'],
              'source': c['source'] ?? 'manual',
              'confidence': c['confidence'],
            }
        ],
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Created ${tx['tx_number']}')));
      setState(() => _cart.clear());
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('POS'),
        actions: [
          IconButton(icon: const Icon(Icons.logout), onPressed: () {
            ApiService.clearAuth();
            Navigator.of(context).popUntil((r) => r.isFirst);
          }),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Expanded(flex: 2, child: _cameraPanel()),
            const SizedBox(width: 16),
            Expanded(flex: 1, child: _cartPanel()),
          ],
        ),
      ),
    );
  }

  Widget _cameraPanel() => SectionCard(
    title: 'Scan',
    trailing: _busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : null,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 220,
          child: _lastImage == null
            ? const Center(child: Text('Tap Snap to scan a tray'))
            : Image.memory(_lastImage!, fit: BoxFit.cover),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(onPressed: _snap, icon: const Icon(Icons.camera_alt), label: const Text('Snap')),
        const SizedBox(height: 16),
        if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
        if (_detected.isEmpty && !_busy) const Text('No detections yet'),
        for (final d in _detected) ListTile(
          title: Text(d['name'] ?? d['label'] ?? '?'),
          subtitle: Text('RM ${d['price'] ?? 0}'),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ConfidenceBadge(
                confidence: (d['confidence'] ?? 0.0).toDouble(),
                needsConfirm: d['needs_confirm'] ?? false,
                source: d['source'],
              ),
              const SizedBox(width: 8),
              IconButton(icon: const Icon(Icons.add), onPressed: () => _add(d as Map<String, dynamic>)),
            ],
          ),
        ),
      ],
    ),
  );

  Widget _cartPanel() {
    final total = _cart.fold<double>(
        0, (t, c) => t + ((c['price'] ?? 0).toDouble() * (c['quantity'] ?? 1)));
    return SectionCard(
      title: 'Cart',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_cart.isEmpty) const Text('Empty'),
          for (final c in _cart) Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              Expanded(child: Text(c['name'])),
              Text('x${c['quantity']}'),
              const SizedBox(width: 12),
              Text('RM ${((c['price'] ?? 0).toDouble() * (c['quantity'] ?? 1)).toStringAsFixed(2)}'),
            ]),
          ),
          const Divider(),
          Row(children: [
            const Text('TOTAL', style: TextStyle(fontWeight: FontWeight.w700)),
            const Spacer(),
            Text('RM ${total.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700)),
          ]),
          const SizedBox(height: 12),
          FilledButton(onPressed: _cart.isEmpty ? null : _checkout, child: const Text('Checkout')),
        ],
      ),
    );
  }
}
