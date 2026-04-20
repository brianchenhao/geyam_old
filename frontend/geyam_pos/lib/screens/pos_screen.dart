import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
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
  List<dynamic> menu = [];
  bool scanning = false;
  bool confirming = false;
  String? message;

  double get total => cart.fold(0, (a, b) => a + b.lineTotal);

  @override
  void initState() {
    super.initState();
    _loadMenu();
  }

  Future<void> _loadMenu() async {
    try {
      menu = await ApiService.listMenu();
      if (mounted) setState(() {});
    } catch (_) {}
  }

  Future<void> _scanTray() async {
    setState(() {
      scanning = true;
      message = null;
    });
    try {
      final picker = ImagePicker();
      final image = await picker.pickImage(
        source: ImageSource.camera, imageQuality: 85);
      if (image == null) return;
      final res = await ApiService.detect(image);
      final items = (res['items'] as List?) ?? [];
      final shortlists = (res['shortlists'] as List?) ?? [];
      final notes = (res['notes'] as List?) ?? [];
      if (items.isEmpty && shortlists.isEmpty) {
        setState(() => message =
            'No products detected. ${notes.isNotEmpty ? notes.join(" · ") : "Tap a menu item below."}');
        return;
      }
      setState(() {
        for (final d in items) {
          _addToCart(
            menuItemId: d['menu_item_id'] as int,
            name: d['name'] as String,
            price: (d['price'] as num).toDouble(),
            confidence: (d['confidence'] as num?)?.toDouble(),
            source: d['source'] as String?,
            needsConfirm: d['needs_confirm'] as bool? ?? false,
          );
        }
        message = '${items.length} item(s) added'
            '${shortlists.isNotEmpty ? " · ${shortlists.length} ambiguous (tap menu below)" : ""}';
      });
    } catch (e) {
      setState(() => message = 'Scan failed: $e');
    } finally {
      if (mounted) setState(() => scanning = false);
    }
  }

  void _addToCart({
    required int menuItemId,
    required String name,
    required double price,
    double? confidence,
    String? source,
    bool needsConfirm = false,
  }) {
    final existing = cart.indexWhere((c) => c.menuItemId == menuItemId);
    if (existing >= 0) {
      cart[existing].quantity += 1;
    } else {
      cart.add(CartItem(
        menuItemId: menuItemId, name: name, price: price,
        confidence: confidence, quantity: 1,
      ));
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
        items: cart
            .map((c) => {
                  'menu_item_id': c.menuItemId,
                  'quantity': c.quantity,
                  'source': 'manual',
                })
            .toList(),
      );
      if (!mounted) return;
      setState(() {
        message = 'Sale ${result['tx_number']} saved · '
            'total RM ${(result['total']).toString()} (status=${result['status']})';
        cart.clear();
      });
    } catch (e) {
      setState(() => message = 'Save failed: $e');
    } finally {
      if (mounted) setState(() => confirming = false);
    }
  }

  void _logout() {
    Session.clear();
    Navigator.pushReplacement(
      context, MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('POS · ${Session.role}'),
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
            child: Row(
              children: [
                Expanded(
                  flex: 2,
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
                const VerticalDivider(width: 1),
                Expanded(
                  flex: 3,
                  child: _menuGrid(),
                ),
              ],
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
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    Text('RM ${total.toStringAsFixed(2)}',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  ],
                ),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(
                    child: SizedBox(
                      height: 56,
                      child: ElevatedButton.icon(
                        onPressed: scanning ? null : _scanTray,
                        icon: scanning
                            ? const SizedBox(
                                width: 18, height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2))
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
                        onPressed: (cart.isEmpty || confirming) ? null : _confirmSale,
                        icon: confirming
                            ? const SizedBox(
                                width: 18, height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.check),
                        label: const Text('Confirm sale'),
                      ),
                    ),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _menuGrid() {
    if (menu.isEmpty) {
      return const Center(child: Text('Loading menu...'));
    }
    return GridView.builder(
      padding: const EdgeInsets.all(8),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 180, childAspectRatio: 1.6, mainAxisSpacing: 8, crossAxisSpacing: 8,
      ),
      itemCount: menu.length,
      itemBuilder: (_, i) {
        final m = menu[i] as Map<String, dynamic>;
        final low = (m['stock_qty'] as int) <= (m['reorder_point'] as int);
        return Card(
          child: InkWell(
            onTap: () => setState(() => _addToCart(
                  menuItemId: m['id'] as int,
                  name: m['name'] as String,
                  price: double.tryParse('${m['price']}') ?? 0,
                  source: 'manual',
                )),
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(m['name'] as String,
                      maxLines: 2, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  const Spacer(),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('RM ${m['price']}'),
                      if (low)
                        const Icon(Icons.warning, color: Colors.orange, size: 16),
                    ],
                  ),
                  Text('Stock: ${m['stock_qty']}',
                      style: TextStyle(
                        fontSize: 11,
                        color: low ? Colors.orange : null,
                      )),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
