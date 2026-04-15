import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../widgets/cart_widget.dart';
import '../widgets/theme_toggle.dart';
import 'login_screen.dart';

class PosScreen extends StatefulWidget {
  const PosScreen({super.key});

  @override
  State<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends State<PosScreen> {
  final List<CartItem> cart = [];
  bool scanning = false;
  bool confirming = false;
  String? message;

  double get total => cart.fold(0, (a, b) => a + b.lineTotal);

  Future<void> _scanTray() async {
    setState(() {
      scanning = true;
      message = null;
    });
    try {
      final picker = ImagePicker();
      final image = await picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
      );
      if (image == null) return;

      final detections = await ApiService.detect(image);
      if (detections.isEmpty) {
        setState(() => message = 'No products detected.');
        return;
      }
      setState(() {
        for (final d in detections) {
          final id = d['menu_item_id'] as int;
          final existing = cart.indexWhere((c) => c.menuItemId == id);
          if (existing >= 0) {
            cart[existing].quantity += 1;
          } else {
            cart.add(CartItem(
              menuItemId: id,
              name: d['name'] as String,
              price: (d['price'] as num).toDouble(),
              confidence: (d['confidence'] as num?)?.toDouble(),
              quantity: 1,
            ));
          }
        }
        message = '${detections.length} item(s) added';
      });
    } catch (e) {
      setState(() => message = 'Scan failed: $e');
    } finally {
      if (mounted) setState(() => scanning = false);
    }
  }

  Future<void> _confirmSale() async {
    if (cart.isEmpty) return;
    setState(() {
      confirming = true;
      message = null;
    });
    try {
      final result = await ApiService.createTransaction(
        staffId: AuthService.userId,
        items: cart
            .map((c) => {
                  'menu_item_id': c.menuItemId,
                  'quantity': c.quantity,
                  'unit_price': c.price,
                  'confidence': c.confidence,
                })
            .toList(),
      );
      if (!mounted) return;
      setState(() {
        message =
            'Sale #${result['id']} saved · total RM ${(result['total'] as num).toStringAsFixed(2)}';
        cart.clear();
      });
    } catch (e) {
      setState(() => message = 'Save failed: $e');
    } finally {
      if (mounted) setState(() => confirming = false);
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
        title: Text('GEYAM POS · ${AuthService.username ?? "staff"}'),
        actions: [
          const ThemeToggle(),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: _logout,
          ),
        ],
      ),
      body: Column(
        children: [
          if (message != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              color: Colors.black26,
              child: Text(message!, textAlign: TextAlign.center),
            ),
          Expanded(
            child: CartWidget(
              items: cart,
              onRemove: (i) => setState(() => cart.removeAt(i)),
              onQtyChange: (i, delta) {
                setState(() {
                  cart[i].quantity += delta;
                  if (cart[i].quantity <= 0) cart.removeAt(i);
                });
              },
            ),
          ),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: Colors.white24)),
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Total',
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.bold)),
                    Text('RM ${total.toStringAsFixed(2)}',
                        style: const TextStyle(
                            fontSize: 18, fontWeight: FontWeight.bold)),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: SizedBox(
                        height: 56,
                        child: ElevatedButton.icon(
                          onPressed: scanning ? null : _scanTray,
                          icon: scanning
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.camera_alt),
                          label: const Text('Scan tray'),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: SizedBox(
                        height: 56,
                        child: ElevatedButton.icon(
                          onPressed: (cart.isEmpty || confirming)
                              ? null
                              : _confirmSale,
                          icon: confirming
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.check),
                          label: const Text('Confirm sale'),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
