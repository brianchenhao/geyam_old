import 'package:flutter/material.dart';

import '../widgets/section_card.dart';

/// Detailed cart review screen. Lets the cashier adjust quantities or remove
/// lines before returning to POS. Takes the cart list as an argument and
/// returns the edited list via Navigator.pop.
class CartDetailScreen extends StatefulWidget {
  final List<Map<String, dynamic>> cart;

  const CartDetailScreen({super.key, required this.cart});

  @override
  State<CartDetailScreen> createState() => _CartDetailScreenState();
}

class _CartDetailScreenState extends State<CartDetailScreen> {
  late final List<Map<String, dynamic>> _cart;

  @override
  void initState() {
    super.initState();
    _cart = [for (final c in widget.cart) Map<String, dynamic>.from(c)];
  }

  double get _total => _cart.fold<double>(
      0,
      (t, c) =>
          t + ((c['price'] ?? 0).toDouble() * (c['quantity'] ?? 1)));

  void _setQty(int index, int qty) {
    setState(() {
      if (qty <= 0) {
        _cart.removeAt(index);
      } else {
        _cart[index]['quantity'] = qty;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Cart'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(_cart),
            child: const Text('Done'),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: SectionCard(
          title: 'Lines',
          trailing: Text('RM ${_total.toStringAsFixed(2)}',
              style: const TextStyle(fontWeight: FontWeight.w700)),
          child: _cart.isEmpty
              ? const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: Text('Cart is empty')),
                )
              : Column(
                  children: [
                    for (var i = 0; i < _cart.length; i++)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Text(_cart[i]['name'] ?? '?',
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodyLarge),
                                  Text(
                                    'RM ${_cart[i]['price']}'
                                    '${_cart[i]['source'] != null ? "  ·  ${_cart[i]['source']}" : ''}',
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.remove_circle_outline),
                              onPressed: () => _setQty(
                                  i, (_cart[i]['quantity'] ?? 1) - 1),
                            ),
                            SizedBox(
                              width: 28,
                              child: Text('${_cart[i]['quantity'] ?? 1}',
                                  textAlign: TextAlign.center),
                            ),
                            IconButton(
                              icon: const Icon(Icons.add_circle_outline),
                              onPressed: () => _setQty(
                                  i, (_cart[i]['quantity'] ?? 1) + 1),
                            ),
                            const SizedBox(width: 8),
                            SizedBox(
                              width: 80,
                              child: Text(
                                'RM ${(((_cart[i]['price'] ?? 0).toDouble()) * (_cart[i]['quantity'] ?? 1)).toStringAsFixed(2)}',
                                textAlign: TextAlign.right,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600),
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () => _setQty(i, 0),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
        ),
      ),
    );
  }
}
